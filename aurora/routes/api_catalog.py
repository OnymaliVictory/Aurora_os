"""Products, categories, suppliers and stock actions."""
import csv
import io
import sqlite3

from flask import Blueprint, Response, jsonify, request

from .. import money
from ..db import audit, get_db, one, q, transaction
from ..security import can, current_user, permission_required
from ..services import stock
from ..validate import BadInput, body, choice, date_str, flag, integer, money as money_in, number, text

bp = Blueprint("catalog", __name__)


def _opt(v):
    v = (v or "").strip() if isinstance(v, str) else v
    return v or None


# ------------------------------------------------------------------ categories ------
@bp.get("/api/categories")
@permission_required("pos")
def categories():
    rows = q(get_db(), "SELECT c.*, (SELECT COUNT(*) FROM products p WHERE p.category_id=c.id AND p.deleted_at IS NULL) n "
                       "FROM categories c WHERE is_active=1 ORDER BY name")
    return jsonify([dict(r) for r in rows])


def _cat_fields(d):
    return (text(d, "name", "Category name", max_len=60, required=True),
            text(d, "color", max_len=9, default="#34d399") or "#34d399",
            text(d, "emoji", max_len=4, default="🛒") or "🛒")


@bp.post("/api/categories")
@permission_required("products")
def category_add():
    d = body()
    name, color, emoji = _cat_fields(d)
    db = get_db()
    try:
        with transaction(db):
            cur = db.execute("INSERT INTO categories(name,color,emoji) VALUES (?,?,?)", (name, color, emoji))
            audit(db, current_user(), "create", "Category", cur.lastrowid, f"Added category {name}")
    except sqlite3.IntegrityError:
        raise BadInput("A category with that name already exists.")
    return jsonify(ok=True, id=cur.lastrowid)


@bp.put("/api/categories/<int:cid>")
@permission_required("products")
def category_edit(cid):
    d = body()
    name, color, emoji = _cat_fields(d)
    db = get_db()
    try:
        with transaction(db):
            db.execute("UPDATE categories SET name=?, color=?, emoji=? WHERE id=?", (name, color, emoji, cid))
            audit(db, current_user(), "update", "Category", cid, f"Edited category {name}")
    except sqlite3.IntegrityError:
        raise BadInput("A category with that name already exists.")
    return jsonify(ok=True)


@bp.delete("/api/categories/<int:cid>")
@permission_required("products")
def category_delete(cid):
    db = get_db()
    with transaction(db):
        db.execute("UPDATE products SET category_id=NULL WHERE category_id=?", (cid,))
        db.execute("DELETE FROM categories WHERE id=?", (cid,))
        audit(db, current_user(), "delete", "Category", cid, "Deleted a category")
    return jsonify(ok=True)


# ------------------------------------------------------------------ suppliers -------
@bp.get("/api/suppliers")
@permission_required("suppliers")
def suppliers():
    rows = q(get_db(), "SELECT s.*, (SELECT COUNT(*) FROM products p WHERE p.supplier_id=s.id AND p.deleted_at IS NULL) products, "
                       "(SELECT COALESCE(SUM(total_kobo-paid_kobo),0) FROM purchase_orders o WHERE o.supplier_id=s.id AND o.status IN ('partial','received')) owed_kobo "
                       "FROM suppliers s WHERE is_active=1 ORDER BY name")
    return jsonify([dict(r) for r in rows])


def _sup_fields(d):
    return (text(d, "name", "Supplier name", max_len=80, required=True), text(d, "company", max_len=80),
            text(d, "contact_person", max_len=80), text(d, "phone", max_len=30), text(d, "email", max_len=80),
            text(d, "address", max_len=160), text(d, "payment_terms", max_len=60))


@bp.post("/api/suppliers")
@permission_required("suppliers")
def supplier_add():
    f = _sup_fields(body())
    db = get_db()
    with transaction(db):
        cur = db.execute("INSERT INTO suppliers(name,company,contact_person,phone,email,address,payment_terms) VALUES (?,?,?,?,?,?,?)", f)
        audit(db, current_user(), "create", "Supplier", cur.lastrowid, f"Added supplier {f[0]}")
    return jsonify(ok=True, id=cur.lastrowid)


@bp.put("/api/suppliers/<int:sid>")
@permission_required("suppliers")
def supplier_edit(sid):
    f = _sup_fields(body())
    db = get_db()
    with transaction(db):
        db.execute("UPDATE suppliers SET name=?,company=?,contact_person=?,phone=?,email=?,address=?,payment_terms=? WHERE id=?", f + (sid,))
        audit(db, current_user(), "update", "Supplier", sid, f"Edited supplier {f[0]}")
    return jsonify(ok=True)


@bp.delete("/api/suppliers/<int:sid>")
@permission_required("suppliers")
def supplier_delete(sid):
    db = get_db()
    with transaction(db):
        db.execute("UPDATE suppliers SET is_active=0 WHERE id=?", (sid,))
        db.execute("UPDATE products SET supplier_id=NULL WHERE supplier_id=?", (sid,))
        audit(db, current_user(), "delete", "Supplier", sid, "Removed a supplier")
    return jsonify(ok=True)


# ------------------------------------------------------------------ products --------
def product_json(r, show_cost):
    d = dict(r)
    if not show_cost:
        d.pop("cost_kobo", None)
    d["price"] = money.naira(r["price_kobo"])
    return d


LIST_SQL = ("SELECT p.*, c.name category_name, c.color category_color, c.emoji category_emoji, s.name supplier_name, "
            "(SELECT MIN(expiry_date) FROM product_lots l WHERE l.product_id=p.id AND l.qty>0 AND l.expiry_date IS NOT NULL) next_expiry "
            "FROM products p LEFT JOIN categories c ON c.id=p.category_id LEFT JOIN suppliers s ON s.id=p.supplier_id "
            "WHERE p.deleted_at IS NULL")


@bp.get("/api/products")
@permission_required("pos")
def products():
    a = request.args
    sql, args = LIST_SQL, []
    term = (a.get("q") or "").strip()
    if term:
        sql += " AND (p.name LIKE ? OR p.barcode LIKE ? OR p.sku LIKE ? OR p.brand LIKE ?)"
        args += [f"%{term}%"] * 4
    if a.get("category"):
        sql += " AND p.category_id=?"
        args.append(int(a["category"]))
    f = a.get("filter")
    if f == "low":
        sql += " AND p.track_stock=1 AND p.qty>0 AND p.qty<=p.min_stock"
    elif f == "out":
        sql += " AND p.track_stock=1 AND p.qty<=0"
    elif f == "expiry":
        sql += (" AND EXISTS (SELECT 1 FROM product_lots l WHERE l.product_id=p.id AND l.qty>0 AND l.expiry_date IS NOT NULL "
                "AND l.expiry_date <= date('now','localtime','+30 days'))")
    elif f == "inactive":
        sql += " AND p.status='inactive'"
    else:
        sql += " AND p.status='active'" if a.get("active_only") else ""
    sql += " ORDER BY p.name LIMIT ? OFFSET ?"
    limit = min(int(a.get("limit", 200)), 500)
    args += [limit, int(a.get("offset", 0))]
    show = can("cost_view")
    return jsonify([product_json(r, show) for r in q(get_db(), sql, args)])


@bp.get("/api/products/<int:pid>")
@permission_required("products")
def product_get(pid):
    db = get_db()
    r = one(db, LIST_SQL + " AND p.id=?", (pid,))
    if not r:
        raise BadInput("Product not found.")
    d = product_json(r, can("cost_view"))
    d["lots"] = [dict(x) for x in q(db, "SELECT * FROM product_lots WHERE product_id=? AND qty<>0 ORDER BY (expiry_date IS NULL), expiry_date, id", (pid,))]
    d["moves"] = [dict(x) for x in q(db, "SELECT m.*, u.name user_name FROM stock_movements m LEFT JOIN users u ON u.id=m.user_id "
                                         "WHERE product_id=? ORDER BY m.id DESC LIMIT 40", (pid,))]
    return jsonify(d)


def _prod_fields(d, db, pid=None):
    name = text(d, "name", "Product name", max_len=120, required=True)
    barcode = _opt(text(d, "barcode", max_len=40))
    sku = _opt(text(d, "sku", max_len=40))
    for col, val, label in (("barcode", barcode, "barcode"), ("sku", sku, "SKU")):
        if val and one(db, f"SELECT 1 FROM products WHERE {col}=? AND id<>?", (val, pid or 0)):
            raise BadInput(f"Another product already uses that {label}.")
    cat = d.get("category_id")
    sup = d.get("supplier_id")
    return dict(
        name=name, barcode=barcode, sku=sku,
        category_id=int(cat) if cat not in (None, "") else None,
        supplier_id=int(sup) if sup not in (None, "") else None,
        brand=_opt(text(d, "brand", max_len=60)),
        unit=text(d, "unit", max_len=12, default="pcs") or "pcs",
        is_weighed=flag(d, "is_weighed"),
        cost_kobo=money_in(d, "cost", "Cost price"),
        price_kobo=money_in(d, "price", "Selling price", required=True),
        tax_exempt=flag(d, "tax_exempt"),
        min_stock=number(d, "min_stock", "Minimum stock", minimum=0, default=5),
        track_stock=1 if d.get("track_stock", 1) in (True, 1, "1", "true", "on") else 0,
        status=choice(d, "status", ("active", "inactive"), default="active"),
    )


@bp.post("/api/products")
@permission_required("products")
def product_add():
    d = body()
    db = get_db()
    f = _prod_fields(d, db)
    opening = number(d, "opening_qty", "Opening stock", minimum=0, default=0)
    expiry = date_str(d, "expiry_date", "Expiry date")
    user = current_user()
    try:
        with transaction(db):
            cols = ",".join(f)
            cur = db.execute(f"INSERT INTO products({cols}) VALUES ({','.join('?' * len(f))})", list(f.values()))
            pid = cur.lastrowid
            if opening > 0:
                stock.add_stock(db, pid, opening, reason="opening", expiry=expiry, user_id=user["id"])
            audit(db, user, "create", "Product", pid, f"Added product {f['name']}")
    except sqlite3.IntegrityError:
        raise BadInput("That barcode or SKU is already used by another product.")
    return jsonify(ok=True, id=pid)


@bp.put("/api/products/<int:pid>")
@permission_required("products")
def product_edit(pid):
    d = body()
    db = get_db()
    if not one(db, "SELECT 1 FROM products WHERE id=? AND deleted_at IS NULL", (pid,)):
        raise BadInput("Product not found.")
    f = _prod_fields(d, db, pid)
    user = current_user()
    old = one(db, "SELECT price_kobo, cost_kobo FROM products WHERE id=?", (pid,))
    if not can("cost_view"):                       # a manager without cost view can't change cost
        f["cost_kobo"] = old["cost_kobo"]
    sets = ",".join(f"{k}=?" for k in f)
    try:
        with transaction(db):
            db.execute(f"UPDATE products SET {sets}, updated_at=datetime('now','localtime') WHERE id=?", list(f.values()) + [pid])
            note = f"Edited product {f['name']}"
            if old["price_kobo"] != f["price_kobo"]:
                note += f" (price {money.naira(old['price_kobo'])} → {money.naira(f['price_kobo'])})"
            audit(db, user, "update", "Product", pid, note)
    except sqlite3.IntegrityError:
        raise BadInput("That barcode or SKU is already used by another product.")
    return jsonify(ok=True)


@bp.delete("/api/products/<int:pid>")
@permission_required("products")
def product_delete(pid):
    db = get_db()
    p = one(db, "SELECT name FROM products WHERE id=? AND deleted_at IS NULL", (pid,))
    if not p:
        raise BadInput("Product not found.")
    with transaction(db):
        # barcode/SKU are freed so they can be reused; sales history keeps the product name
        db.execute("UPDATE products SET deleted_at=datetime('now','localtime'), barcode=NULL, sku=NULL, status='inactive' WHERE id=?", (pid,))
        audit(db, current_user(), "delete", "Product", pid, f"Deleted product {p['name']}")
    return jsonify(ok=True)


@bp.post("/api/products/<int:pid>/stock")
@permission_required("stock")
def product_stock(pid):
    d = body()
    db = get_db()
    p = one(db, "SELECT * FROM products WHERE id=? AND deleted_at IS NULL", (pid,))
    if not p:
        raise BadInput("Product not found.")
    action = choice(d, "action", ("receive", "damage", "expired", "correct"), "Action", required=True)
    user = current_user()
    note = text(d, "note", max_len=160)
    try:
        with transaction(db):
            if action == "receive":
                qty = number(d, "qty", "Quantity", minimum=0.001, required=True)
                cost = money_in(d, "cost", "Cost") if d.get("cost") not in (None, "") else None
                stock.add_stock(db, pid, qty, reason="purchase", expiry=date_str(d, "expiry_date"), cost_kobo=cost,
                                user_id=user["id"], note=note or "Stock received")
                msg = f"Received {qty:g} × {p['name']}"
            elif action in ("damage", "expired"):
                qty = number(d, "qty", "Quantity", minimum=0.001, required=True)
                stock.remove_stock(db, pid, qty, reason=action, user_id=user["id"], note=note,
                                   lot_id=int(d["lot_id"]) if d.get("lot_id") else None)
                msg = f"Wrote off {qty:g} × {p['name']} as {action}"
            else:
                new = number(d, "qty", "Counted quantity", minimum=0, required=True)
                diff = stock.set_stock_level(db, pid, new, reason="correction", user_id=user["id"], note=note or "Manual correction")
                msg = f"Corrected {p['name']} to {new:g} ({diff:+g})"
            audit(db, user, "stock", "Product", pid, msg)
            stock.alert_if_low(db, pid)
    except stock.StockError as e:
        raise BadInput(str(e))
    return jsonify(ok=True, message=msg)


# ---------------------------------------------------------------- CSV in / out ------
CSV_COLS = ["name", "barcode", "sku", "category", "brand", "unit", "cost", "price", "tax_exempt", "min_stock", "qty", "expiry_date"]


@bp.get("/api/products/export.csv")
@permission_required("products")
def products_export():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_COLS)
    for r in q(get_db(), LIST_SQL + " ORDER BY p.name"):
        w.writerow([_safe(r["name"]), r["barcode"] or "", r["sku"] or "", r["category_name"] or "", r["brand"] or "", r["unit"],
                    f"{r['cost_kobo'] / 100:.2f}", f"{r['price_kobo'] / 100:.2f}", r["tax_exempt"], f"{r['min_stock']:g}",
                    f"{r['qty']:g}", r["next_expiry"] or ""])
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=aurora-products.csv"})


def _safe(v):
    """Stops a spreadsheet from running a cell that starts with = + - @ as a formula."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


@bp.post("/api/products/import")
@permission_required("products")
def products_import():
    d = body()
    raw = d.get("csv")
    if not isinstance(raw, str) or not raw.strip():
        raise BadInput("Choose a CSV file first.")
    raw = raw.lstrip("﻿")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        raise BadInput("The file has no rows.")
    if len(rows) > 5000:
        raise BadInput("Please import at most 5,000 products at a time.")
    db, user = get_db(), current_user()
    added = updated = 0
    problems = []
    with transaction(db):
        for n, r in enumerate(rows, start=2):
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
            name = r.get("name")
            if not name:
                problems.append(f"Row {n}: no name — skipped.")
                continue
            try:
                price = money.to_kobo(r.get("price") or "0")
                cost = money.to_kobo(r.get("cost") or "0")
                mn = float(r.get("min_stock") or 5)
                qty = float(r.get("qty") or 0)
            except Exception:
                problems.append(f"Row {n} ({name}): a number is not valid — skipped.")
                continue
            if price <= 0:
                problems.append(f"Row {n} ({name}): price missing — skipped.")
                continue
            cat_id = None
            if r.get("category"):
                c = one(db, "SELECT id FROM categories WHERE name=?", (r["category"],))
                if not c:
                    c = db.execute("INSERT INTO categories(name) VALUES (?)", (r["category"],))
                    cat_id = c.lastrowid
                else:
                    cat_id = c["id"]
            barcode, sku = r.get("barcode") or None, r.get("sku") or None
            existing = one(db, "SELECT id FROM products WHERE deleted_at IS NULL AND ((? IS NOT NULL AND barcode=?) OR (? IS NOT NULL AND sku=?))",
                           (barcode, barcode, sku, sku))
            exempt = 1 if r.get("tax_exempt", "").lower() in ("1", "yes", "true", "y") else 0
            if existing:
                db.execute("UPDATE products SET name=?, category_id=COALESCE(?,category_id), brand=?, cost_kobo=?, price_kobo=?, "
                           "tax_exempt=?, min_stock=?, updated_at=datetime('now','localtime') WHERE id=?",
                           (name, cat_id, r.get("brand") or None, cost, price, exempt, mn, existing["id"]))
                updated += 1
            else:
                cur = db.execute("INSERT INTO products(name,barcode,sku,category_id,brand,unit,cost_kobo,price_kobo,tax_exempt,min_stock,is_weighed) "
                                 "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 (name, barcode, sku, cat_id, r.get("brand") or None, r.get("unit") or "pcs", cost, price, exempt, mn,
                                  1 if (r.get("unit") or "").lower() == "kg" else 0))
                if qty > 0:
                    exp = r.get("expiry_date") or None
                    stock.add_stock(db, cur.lastrowid, qty, reason="opening", expiry=exp, user_id=user["id"])
                added += 1
        audit(db, user, "import", "Product", None, f"Imported products: {added} added, {updated} updated")
    return jsonify(ok=True, added=added, updated=updated, problems=problems[:30])
