"""The till: searching, pricing, taking payment, held baskets, shifts, customers, refunds."""
import json
import sqlite3

from flask import Blueprint, jsonify, request

from .. import money
from ..db import audit, get_db, get_settings, one, q, transaction
from ..security import can, current_user, permission_required, verify_manager_pin
from ..services import sales
from ..services.sales import NeedApproval, SaleError
from ..validate import BadInput, body, choice, integer, money as money_in, number, text

bp = Blueprint("pos", __name__)


def _clean_cart(d):
    items = d.get("items")
    if not isinstance(items, list):
        raise BadInput("The basket is not valid.")
    out = []
    for it in items[:200]:
        if not isinstance(it, dict):
            raise BadInput("The basket is not valid.")
        row = {"product_id": it.get("product_id"), "qty": it.get("qty")}
        if it.get("price_kobo") not in (None, ""):
            row["price_kobo"] = it["price_kobo"]
        if it.get("discount_pct") not in (None, "", 0, "0"):
            row["discount_pct"] = it["discount_pct"]
        out.append(row)
    return out


def _approver(d):
    pin = d.get("pin")
    if not pin:
        return None
    a = verify_manager_pin(str(pin))
    if not a:
        raise BadInput("That manager PIN is not correct.")
    return a


def _priced_json(cart):
    return {
        "lines": [{"product_id": l["product_id"], "name": l["name"], "qty": l["qty"], "unit": l["unit"], "is_weighed": l["product"]["is_weighed"],
                   "unit_price_kobo": l["unit_price_kobo"], "discount_kobo": l["discount_kobo"],
                   "tax_kobo": l["tax_kobo"], "total_kobo": l["total_kobo"]} for l in cart["lines"]],
        **{k: cart[k] for k in ("subtotal_kobo", "discount_kobo", "tax_kobo", "total_kobo", "inclusive", "tax_rate")},
    }


# ----------------------------------------------------------------- product lookup ------
SEL = ("SELECT p.id,p.name,p.barcode,p.sku,p.price_kobo,p.unit,p.is_weighed,p.tax_exempt,p.qty,p.track_stock,p.min_stock,"
       "p.category_id, c.color category_color, c.emoji category_emoji FROM products p "
       "LEFT JOIN categories c ON c.id=p.category_id WHERE p.deleted_at IS NULL AND p.status='active'")


@bp.get("/api/pos/products")
@permission_required("pos")
def pos_products():
    term = (request.args.get("q") or "").strip()
    sql, args = SEL, []
    if term:
        sql += " AND (p.name LIKE ? OR p.barcode LIKE ? OR p.sku LIKE ? OR p.brand LIKE ?)"
        args += [f"%{term}%"] * 4
    if request.args.get("category"):
        sql += " AND p.category_id=?"
        args.append(int(request.args["category"]))
    sql += " ORDER BY p.total_sold DESC, p.name LIMIT 80"
    return jsonify([dict(r) for r in q(get_db(), sql, args)])


@bp.get("/api/pos/barcode/<code>")
@permission_required("pos")
def pos_barcode(code):
    r = one(get_db(), SEL + " AND (p.barcode=? OR p.sku=?)", (code.strip(), code.strip()))
    if not r:
        return jsonify(error="No product has that barcode."), 404
    return jsonify(dict(r))


# ----------------------------------------------------------------------- pricing -------
@bp.post("/api/pos/quote")
@permission_required("pos")
def pos_quote():
    d = body()
    db = get_db()
    try:
        cart = sales.price_cart(db, _clean_cart(d), cart_discount=d.get("cart_discount"), user=current_user(),
                                approved=_approver(d) is not None)
    except NeedApproval as e:
        return jsonify(need_pin=True, reason=e.reason)
    except SaleError as e:
        raise BadInput(str(e))
    return jsonify(_priced_json(cart))


@bp.post("/api/pos/checkout")
@permission_required("pos")
def pos_checkout():
    d = body()
    db = get_db()
    user = current_user()
    pays = d.get("payments")
    if not isinstance(pays, list):
        raise BadInput("Choose how the customer is paying.")
    try:
        sid = sales.create_sale(db, user, items=_clean_cart(d), payments=pays, customer_id=d.get("customer_id") or None,
                                cart_discount=d.get("cart_discount"), note=text(d, "note", max_len=300),
                                approver=_approver(d), held_id=d.get("held_id"))
    except NeedApproval as e:
        return jsonify(need_pin=True, reason=e.reason)
    except SaleError as e:
        raise BadInput(str(e))
    s = one(db, "SELECT receipt_no,total_kobo,change_kobo,points_earned FROM sales WHERE id=?", (sid,))
    return jsonify(ok=True, sale_id=sid, receipt_no=s["receipt_no"], total_kobo=s["total_kobo"],
                   change_kobo=s["change_kobo"], points_earned=s["points_earned"])


# ------------------------------------------------------------------- held baskets ------
@bp.get("/api/pos/held")
@permission_required("pos")
def held_list():
    rows = q(get_db(), "SELECT id,label,cart_json,customer_id,created_at FROM held_sales WHERE user_id=? ORDER BY id DESC", (current_user()["id"],))
    out = []
    for r in rows:
        cart = json.loads(r["cart_json"])
        out.append({"id": r["id"], "label": r["label"], "created_at": r["created_at"], "customer_id": r["customer_id"],
                    "count": len(cart.get("items", [])), "cart": cart})
    return jsonify(out)


@bp.post("/api/pos/held")
@permission_required("pos")
def held_save():
    d = body()
    items = _clean_cart(d)
    if not items:
        raise BadInput("There is nothing to hold.")
    db = get_db()
    payload = json.dumps({"items": items, "cart_discount": d.get("cart_discount")})
    with transaction(db):
        cur = db.execute("INSERT INTO held_sales(user_id,label,cart_json,customer_id) VALUES (?,?,?,?)",
                         (current_user()["id"], text(d, "label", max_len=40) or "Held basket", payload, d.get("customer_id") or None))
    return jsonify(ok=True, id=cur.lastrowid)


@bp.delete("/api/pos/held/<int:hid>")
@permission_required("pos")
def held_delete(hid):
    db = get_db()
    with transaction(db):
        db.execute("DELETE FROM held_sales WHERE id=? AND user_id=?", (hid, current_user()["id"]))
    return jsonify(ok=True)


# ----------------------------------------------------------------------- shifts --------
@bp.get("/api/shift")
@permission_required("shift")
def shift_current():
    db, user = get_db(), current_user()
    sh = sales.open_shift_of(db, user["id"])
    if not sh:
        return jsonify(open=False)
    s = sales.shift_summary(db, sh["id"])
    s["open"] = True
    return jsonify(s)


@bp.post("/api/shift/open")
@permission_required("shift")
def shift_open():
    d = body()
    try:
        sid = sales.open_shift(get_db(), current_user(), money_in(d, "float", "Opening cash", default=0))
    except SaleError as e:
        raise BadInput(str(e))
    return jsonify(ok=True, id=sid)


@bp.post("/api/shift/close")
@permission_required("shift")
def shift_close():
    d = body()
    db, user = get_db(), current_user()
    sh = sales.open_shift_of(db, user["id"])
    if not sh:
        raise BadInput("You have no open shift.")
    try:
        res = sales.close_shift(db, user, sh["id"], money_in(d, "counted", "Counted cash", required=True), text(d, "notes", max_len=200))
    except SaleError as e:
        raise BadInput(str(e))
    return jsonify(ok=True, expected_kobo=res["expected_cash_kobo"], counted_kobo=res["counted_cash_kobo"],
                   difference_kobo=res["difference_kobo"], shift_id=sh["id"])


@bp.post("/api/shift/cash")
@permission_required("shift")
def shift_cash():
    """Cash put in or taken out of the drawer mid-shift (float top-up, paying a supplier, etc.)."""
    d = body()
    db, user = get_db(), current_user()
    sh = sales.open_shift_of(db, user["id"])
    if not sh:
        raise BadInput("Open your shift first.")
    kind = choice(d, "kind", ("in", "out"), "Type", required=True)
    amt = money_in(d, "amount", "Amount", required=True)
    if amt <= 0:
        raise BadInput("Amount must be more than zero.")
    reason = text(d, "reason", "Reason", max_len=120, required=True)
    if kind == "out":
        have = sales.shift_summary(db, sh["id"])["expected_cash_kobo"]
        if amt > have:
            raise BadInput(f"The drawer should only have {money.naira(have)}.")
    with transaction(db):
        db.execute("INSERT INTO cash_movements(shift_id,user_id,kind,amount_kobo,reason) VALUES (?,?,?,?,?)",
                   (sh["id"], user["id"], kind, amt, reason))
        audit(db, user, "cash_" + kind, "Shift", sh["id"], f"Cash {kind}: {money.naira(amt)} — {reason}")
    return jsonify(ok=True)


@bp.get("/api/shifts")
@permission_required("shift")
def shifts_list():
    db, user = get_db(), current_user()
    sql = ("SELECT s.*, u.name user_name FROM shifts s JOIN users u ON u.id=s.user_id")
    args = []
    if not can("shifts_all"):
        sql += " WHERE s.user_id=?"
        args.append(user["id"])
    rows = q(db, sql + " ORDER BY s.id DESC LIMIT 60", args)
    out = []
    for r in rows:
        d = dict(r)
        sm = one(db, "SELECT COUNT(*) n, COALESCE(SUM(total_kobo),0) t FROM sales WHERE shift_id=? AND status!='voided'", (r["id"],))
        d["sales_count"], d["sales_total_kobo"] = sm["n"], sm["t"]
        out.append(d)
    return jsonify(out)


# --------------------------------------------------------------------- customers -------
@bp.get("/api/customers")
@permission_required("customers")
def customers():
    term = (request.args.get("q") or "").strip()
    sql, args = "SELECT * FROM customers WHERE is_active=1", []
    if term:
        sql += " AND (name LIKE ? OR phone LIKE ?)"
        args += [f"%{term}%"] * 2
    if request.args.get("owing"):
        sql += " AND balance_kobo>0"
    rows = q(get_db(), sql + " ORDER BY name LIMIT 300", args)
    return jsonify([dict(r) for r in rows])


def _cust_fields(d):
    phone = text(d, "phone", max_len=20) or None
    return (text(d, "name", "Name", max_len=80, required=True), phone, text(d, "email", max_len=80) or None,
            text(d, "address", max_len=160) or None, text(d, "notes", max_len=200) or None)


@bp.post("/api/customers")
@permission_required("customers_edit")
def customer_add():
    d = body()
    f = _cust_fields(d)
    limit = money_in(d, "credit_limit", "Credit limit") if can("price_override") else 0
    db = get_db()
    try:
        with transaction(db):
            cur = db.execute("INSERT INTO customers(name,phone,email,address,notes,credit_limit_kobo) VALUES (?,?,?,?,?,?)", f + (limit,))
            audit(db, current_user(), "create", "Customer", cur.lastrowid, f"Added customer {f[0]}")
    except sqlite3.IntegrityError:
        raise BadInput("A customer with that phone number already exists.")
    return jsonify(ok=True, id=cur.lastrowid)


@bp.put("/api/customers/<int:cid>")
@permission_required("customers_edit")
def customer_edit(cid):
    d = body()
    f = _cust_fields(d)
    db = get_db()
    try:
        with transaction(db):
            db.execute("UPDATE customers SET name=?,phone=?,email=?,address=?,notes=? WHERE id=?", f + (cid,))
            if can("price_override") and "credit_limit" in d:
                db.execute("UPDATE customers SET credit_limit_kobo=? WHERE id=?", (money_in(d, "credit_limit", "Credit limit"), cid))
            audit(db, current_user(), "update", "Customer", cid, f"Edited customer {f[0]}")
    except sqlite3.IntegrityError:
        raise BadInput("A customer with that phone number already exists.")
    return jsonify(ok=True)


@bp.get("/api/customers/<int:cid>")
@permission_required("customers")
def customer_get(cid):
    db = get_db()
    c = one(db, "SELECT * FROM customers WHERE id=?", (cid,))
    if not c:
        raise BadInput("Customer not found.")
    d = dict(c)
    d["sales"] = [dict(r) for r in q(db, "SELECT id,receipt_no,total_kobo,status,created_at FROM sales WHERE customer_id=? ORDER BY id DESC LIMIT 20", (cid,))]
    d["payments"] = [dict(r) for r in q(db, "SELECT amount_kobo,method,note,created_at FROM customer_payments WHERE customer_id=? ORDER BY id DESC LIMIT 20", (cid,))]
    return jsonify(d)


@bp.post("/api/customers/<int:cid>/pay")
@permission_required("customers_edit")
def customer_pay(cid):
    """A customer pays off some of what they owe."""
    d = body()
    db, user = get_db(), current_user()
    amt = money_in(d, "amount", "Amount", required=True)
    method = choice(d, "method", ("cash", "card", "transfer"), "Method", default="cash")
    if amt <= 0:
        raise BadInput("Amount must be more than zero.")
    with transaction(db):
        c = one(db, "SELECT * FROM customers WHERE id=?", (cid,))
        if not c:
            raise BadInput("Customer not found.")
        if amt > c["balance_kobo"]:
            raise BadInput(f"{c['name']} only owes {money.naira(c['balance_kobo'])}.")
        sh = sales.open_shift_of(db, user["id"])
        if method == "cash" and not sh and get_settings(db)["require_shift"] == "1":
            raise BadInput("Open your shift first so the cash is counted.")
        db.execute("INSERT INTO customer_payments(customer_id,shift_id,user_id,amount_kobo,method,note) VALUES (?,?,?,?,?,?)",
                   (cid, sh["id"] if sh else None, user["id"], amt, method, text(d, "note", max_len=120)))
        db.execute("UPDATE customers SET balance_kobo=balance_kobo-? WHERE id=?", (amt, cid))
        audit(db, user, "debt_payment", "Customer", cid, f"{c['name']} paid {money.naira(amt)} ({method}) toward their balance")
    return jsonify(ok=True)


# ----------------------------------------------------------------------- sales ---------
@bp.get("/api/sales")
@permission_required("sales_own")
def sales_list():
    a = request.args
    sql = ("SELECT s.id,s.receipt_no,s.total_kobo,s.status,s.created_at,s.discount_kobo,u.name cashier_name,c.name customer_name, "
           "(SELECT GROUP_CONCAT(DISTINCT method) FROM payments WHERE sale_id=s.id) methods "
           "FROM sales s JOIN users u ON u.id=s.cashier_id LEFT JOIN customers c ON c.id=s.customer_id WHERE 1=1")
    args = []
    if not can("sales_all"):
        sql += " AND s.cashier_id=?"
        args.append(current_user()["id"])
    if a.get("q"):
        sql += " AND (s.receipt_no LIKE ? OR c.name LIKE ?)"
        args += [f"%{a['q'].strip()}%"] * 2
    if a.get("from"):
        sql += " AND date(s.created_at)>=?"
        args.append(a["from"][:10])
    if a.get("to"):
        sql += " AND date(s.created_at)<=?"
        args.append(a["to"][:10])
    if a.get("status"):
        sql += " AND s.status=?"
        args.append(a["status"])
    return jsonify([dict(r) for r in q(get_db(), sql + " ORDER BY s.id DESC LIMIT 200", args)])


@bp.get("/api/sales/<int:sid>")
@permission_required("sales_own")
def sale_get(sid):
    d = sales.sale_detail(get_db(), sid)
    if not d or (not can("sales_all") and d["cashier_id"] != current_user()["id"]):
        raise BadInput("Sale not found.")
    if not can("cost_view"):
        for it in d["items"]:
            it.pop("cost_kobo", None)
    d["settings"] = {k: v for k, v in get_settings(get_db()).items() if k.startswith("store_") or k.startswith("receipt_") or k == "currency_symbol"}
    return jsonify(d)


@bp.post("/api/sales/<int:sid>/refund")
@permission_required("sales_own")
def sale_refund(sid):
    d = body()
    db, user = get_db(), current_user()
    approver = _approver(d)
    if approver is None and can("refunds"):          # managers approve their own refunds
        approver = user
    if approver is None:
        return jsonify(need_pin=True, reason="Refunding a sale")
    void = bool(d.get("void"))
    lines = d.get("lines") or []
    if not isinstance(lines, list):
        raise BadInput("Choose the items to refund.")
    try:
        rid, total = sales.refund_sale(db, user, sid, lines, choice(d, "method", ("cash", "card", "transfer", "account"), "Refund method", required=True),
                                       text(d, "reason", "Reason", max_len=200, required=True), approver, void=void)
    except SaleError as e:
        raise BadInput(str(e))
    return jsonify(ok=True, refund_id=rid, total_kobo=total)
