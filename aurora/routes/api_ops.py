"""Buying stock, stock-taking, expenses, staff, settings, backups, alerts and the audit trail."""
import sqlite3

from flask import Blueprint, jsonify, request, send_file

from .. import money, paths
from ..db import audit, get_db, get_settings, one, q, set_setting, transaction
from ..security import (can, current_user, hash_password, permission_required, valid_password, valid_pin)
from ..services import backup, demo, stock
from ..validate import BadInput, body, choice, date_str, flag, integer, money as money_in, number, text

bp = Blueprint("ops", __name__)


# ===================================================================== purchases =====
def _po_no(db):
    n = one(db, "SELECT COALESCE(MAX(id),0)+1 n FROM purchase_orders")["n"]
    return f"PO-{n:05d}"


@bp.get("/api/purchases")
@permission_required("purchases")
def po_list():
    rows = q(get_db(), "SELECT o.*, s.name supplier_name, (SELECT COUNT(*) FROM po_items i WHERE i.po_id=o.id) lines "
                       "FROM purchase_orders o LEFT JOIN suppliers s ON s.id=o.supplier_id ORDER BY o.id DESC LIMIT 200")
    return jsonify([dict(r) for r in rows])


@bp.get("/api/purchases/suggest")
@permission_required("purchases")
def po_suggest():
    """Everything that is running low, with a sensible amount to re-order — a one-click starting list."""
    rows = q(get_db(), "SELECT p.id, p.name, p.qty, p.min_stock, p.cost_kobo, p.supplier_id, s.name supplier_name, "
                       "MAX(p.min_stock*3 - p.qty, 1) suggest "
                       "FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id "
                       "WHERE p.deleted_at IS NULL AND p.status='active' AND p.track_stock=1 AND p.qty<=p.min_stock ORDER BY p.name")
    return jsonify([dict(r) for r in rows])


@bp.get("/api/purchases/<int:oid>")
@permission_required("purchases")
def po_get(oid):
    db = get_db()
    o = one(db, "SELECT o.*, s.name supplier_name FROM purchase_orders o LEFT JOIN suppliers s ON s.id=o.supplier_id WHERE o.id=?", (oid,))
    if not o:
        raise BadInput("Order not found.")
    d = dict(o)
    d["items"] = [dict(r) for r in q(db, "SELECT i.*, p.name, p.unit FROM po_items i JOIN products p ON p.id=i.product_id WHERE i.po_id=? ORDER BY i.id", (oid,))]
    return jsonify(d)


@bp.post("/api/purchases")
@permission_required("purchases")
def po_create():
    d = body()
    db, user = get_db(), current_user()
    items = d.get("items")
    if not isinstance(items, list) or not items:
        raise BadInput("Add at least one product to the order.")
    sup = d.get("supplier_id")
    status = choice(d, "status", ("draft", "ordered"), default="draft")
    with transaction(db):
        total = 0
        cur = db.execute("INSERT INTO purchase_orders(po_no,supplier_id,status,expected_on,note,user_id) VALUES (?,?,?,?,?,?)",
                         (_po_no(db), int(sup) if sup else None, status, date_str(d, "expected_on"), text(d, "note", max_len=200), user["id"]))
        oid = cur.lastrowid
        for it in items:
            pid = int(it.get("product_id") or 0)
            if not one(db, "SELECT 1 FROM products WHERE id=? AND deleted_at IS NULL", (pid,)):
                raise BadInput("A product in the order no longer exists.")
            qty = number(it, "qty", "Quantity", minimum=0.001, required=True)
            cost = money_in(it, "cost", "Cost")
            db.execute("INSERT INTO po_items(po_id,product_id,qty_ordered,cost_kobo) VALUES (?,?,?,?)", (oid, pid, qty, cost))
            total += int(round(qty * cost))
        db.execute("UPDATE purchase_orders SET total_kobo=? WHERE id=?", (total, oid))
        audit(db, user, "create", "PurchaseOrder", oid, f"Created purchase order for {money.naira(total)}")
    return jsonify(ok=True, id=oid)


@bp.post("/api/purchases/<int:oid>/status")
@permission_required("purchases")
def po_status(oid):
    d = body()
    new = choice(d, "status", ("ordered", "cancelled"), "Status", required=True)
    db = get_db()
    with transaction(db):
        o = one(db, "SELECT status FROM purchase_orders WHERE id=?", (oid,))
        if not o or o["status"] in ("received", "cancelled"):
            raise BadInput("This order can't be changed any more.")
        if new == "ordered" and o["status"] != "draft":
            raise BadInput("Only a draft can be sent.")
        db.execute("UPDATE purchase_orders SET status=? WHERE id=?", (new, oid))
        audit(db, current_user(), "update", "PurchaseOrder", oid, f"Order marked {new}")
    return jsonify(ok=True)


@bp.post("/api/purchases/<int:oid>/receive")
@permission_required("purchases")
def po_receive(oid):
    """Goods arrive: each line becomes a new batch with its own expiry date. Part deliveries are fine."""
    d = body()
    db, user = get_db(), current_user()
    lines = d.get("lines")
    if not isinstance(lines, list) or not lines:
        raise BadInput("Enter what was delivered.")
    try:
        with transaction(db):
            o = one(db, "SELECT * FROM purchase_orders WHERE id=?", (oid,))
            if not o or o["status"] in ("cancelled", "received", "draft"):
                raise BadInput("This order is not waiting for a delivery.")
            got = 0
            for ln in lines:
                it = one(db, "SELECT * FROM po_items WHERE id=? AND po_id=?", (int(ln.get("item_id") or 0), oid))
                if not it:
                    raise BadInput("A line does not belong to this order.")
                qty = number(ln, "qty", "Delivered quantity", minimum=0, default=0)
                if qty <= 0:
                    continue
                cost = money_in(ln, "cost", "Cost", default=it["cost_kobo"]) if ln.get("cost") not in (None, "") else it["cost_kobo"]
                stock.add_stock(db, it["product_id"], qty, reason="purchase", expiry=date_str(ln, "expiry_date"),
                                cost_kobo=cost, ref_type="purchase", ref_id=oid, user_id=user["id"], po_id=oid, note=o["po_no"])
                # the shelf cost follows the newest delivery
                db.execute("UPDATE products SET cost_kobo=? WHERE id=?", (cost, it["product_id"]))
                db.execute("UPDATE po_items SET qty_received=ROUND(qty_received+?,3), cost_kobo=? WHERE id=?", (qty, cost, it["id"]))
                got += 1
            if not got:
                raise BadInput("Enter a delivered quantity for at least one line.")
            left = one(db, "SELECT COUNT(*) c FROM po_items WHERE po_id=? AND qty_received < qty_ordered - 0.0009", (oid,))["c"]
            total = one(db, "SELECT COALESCE(SUM(ROUND(qty_received*cost_kobo)),0) t FROM po_items WHERE po_id=?", (oid,))["t"]
            db.execute("UPDATE purchase_orders SET status=?, total_kobo=?, received_at=datetime('now','localtime') WHERE id=?",
                       ("received" if left == 0 else "partial", int(total), oid))
            audit(db, user, "receive", "PurchaseOrder", oid, f"Received delivery for {o['po_no']}")
    except stock.StockError as e:
        raise BadInput(str(e))
    return jsonify(ok=True)


@bp.post("/api/purchases/<int:oid>/pay")
@permission_required("purchases")
def po_pay(oid):
    d = body()
    db = get_db()
    amt = money_in(d, "amount", "Amount", required=True)
    with transaction(db):
        o = one(db, "SELECT * FROM purchase_orders WHERE id=?", (oid,))
        if not o:
            raise BadInput("Order not found.")
        if amt <= 0 or o["paid_kobo"] + amt > o["total_kobo"]:
            raise BadInput(f"You still owe {money.naira(o['total_kobo'] - o['paid_kobo'])} on this order.")
        db.execute("UPDATE purchase_orders SET paid_kobo=paid_kobo+? WHERE id=?", (amt, oid))
        audit(db, current_user(), "payment", "PurchaseOrder", oid, f"Paid supplier {money.naira(amt)} on {o['po_no']}")
    return jsonify(ok=True)


# ===================================================================== stock-take ====
@bp.get("/api/stocktakes")
@permission_required("stocktake")
def st_list():
    rows = q(get_db(), "SELECT t.*, (SELECT COUNT(*) FROM stocktake_items i WHERE i.stocktake_id=t.id) lines, "
                       "(SELECT COUNT(*) FROM stocktake_items i WHERE i.stocktake_id=t.id AND counted_qty IS NOT NULL) counted "
                       "FROM stocktakes t ORDER BY id DESC LIMIT 50")
    return jsonify([dict(r) for r in rows])


@bp.post("/api/stocktakes")
@permission_required("stocktake")
def st_create():
    d = body()
    db, user = get_db(), current_user()
    name = text(d, "name", max_len=60) or "Stock count"
    sql, args = "SELECT id, qty FROM products WHERE deleted_at IS NULL AND track_stock=1", []
    if d.get("category_id"):
        sql += " AND category_id=?"
        args.append(int(d["category_id"]))
    prods = q(db, sql, args)
    if not prods:
        raise BadInput("There are no products to count.")
    with transaction(db):
        cur = db.execute("INSERT INTO stocktakes(name,user_id) VALUES (?,?)", (name, user["id"]))
        db.executemany("INSERT INTO stocktake_items(stocktake_id,product_id,expected_qty) VALUES (?,?,?)",
                       [(cur.lastrowid, p["id"], p["qty"]) for p in prods])
        audit(db, user, "create", "Stocktake", cur.lastrowid, f"Started stock count '{name}' ({len(prods)} products)")
    return jsonify(ok=True, id=cur.lastrowid)


@bp.get("/api/stocktakes/<int:tid>")
@permission_required("stocktake")
def st_get(tid):
    db = get_db()
    t = one(db, "SELECT * FROM stocktakes WHERE id=?", (tid,))
    if not t:
        raise BadInput("Stock count not found.")
    d = dict(t)
    d["items"] = [dict(r) for r in q(db, "SELECT i.*, p.name, p.barcode, p.unit, p.cost_kobo FROM stocktake_items i JOIN products p ON p.id=i.product_id "
                                         "WHERE i.stocktake_id=? ORDER BY p.name", (tid,))]
    if not can("cost_view"):
        for i in d["items"]:
            i.pop("cost_kobo", None)
    return jsonify(d)


@bp.put("/api/stocktakes/<int:tid>/count")
@permission_required("stocktake")
def st_count(tid):
    d = body()
    db = get_db()
    t = one(db, "SELECT status FROM stocktakes WHERE id=?", (tid,))
    if not t or t["status"] != "open":
        raise BadInput("This count is closed.")
    val = d.get("counted")
    counted = None if val in (None, "") else number(d, "counted", "Counted quantity", minimum=0)
    with transaction(db):
        db.execute("UPDATE stocktake_items SET counted_qty=? WHERE stocktake_id=? AND product_id=?", (counted, tid, int(d.get("product_id") or 0)))
    return jsonify(ok=True)


@bp.post("/api/stocktakes/<int:tid>/apply")
@permission_required("stocktake")
def st_apply(tid):
    db, user = get_db(), current_user()
    with transaction(db):
        t = one(db, "SELECT * FROM stocktakes WHERE id=?", (tid,))
        if not t or t["status"] != "open":
            raise BadInput("This count is already closed.")
        changed, lost = 0, 0
        for it in q(db, "SELECT i.*, p.qty now, p.cost_kobo FROM stocktake_items i JOIN products p ON p.id=i.product_id "
                        "WHERE stocktake_id=? AND counted_qty IS NOT NULL", (tid,)):
            # sales made while counting are kept: we apply the difference found, not an overwrite
            diff = round(it["counted_qty"] - it["expected_qty"], 3)
            if abs(diff) < 0.0005:
                continue
            target = max(0, round(it["now"] + diff, 3))
            stock.set_stock_level(db, it["product_id"], target, reason="stocktake", user_id=user["id"],
                                  note=t["name"], ref_type="stocktake", ref_id=tid)
            changed += 1
            if diff < 0:
                lost += int(-diff * it["cost_kobo"])
            stock.alert_if_low(db, it["product_id"])
        db.execute("UPDATE stocktakes SET status='applied', applied_at=datetime('now','localtime') WHERE id=?", (tid,))
        audit(db, user, "stocktake", "Stocktake", tid, f"Applied stock count '{t['name']}': {changed} products adjusted, "
                                                      f"shrinkage worth {money.naira(lost)}")
    return jsonify(ok=True, changed=changed, shrinkage_kobo=lost)


@bp.post("/api/stocktakes/<int:tid>/cancel")
@permission_required("stocktake")
def st_cancel(tid):
    db = get_db()
    with transaction(db):
        db.execute("UPDATE stocktakes SET status='cancelled' WHERE id=? AND status='open'", (tid,))
    return jsonify(ok=True)


# ===================================================================== expenses ======
@bp.get("/api/expenses")
@permission_required("expenses")
def expenses():
    a = request.args
    sql, args = "SELECT e.*, u.name user_name FROM expenses e LEFT JOIN users u ON u.id=e.user_id WHERE 1=1", []
    if a.get("from"):
        sql += " AND paid_on>=?"
        args.append(a["from"][:10])
    if a.get("to"):
        sql += " AND paid_on<=?"
        args.append(a["to"][:10])
    rows = q(get_db(), sql + " ORDER BY paid_on DESC, id DESC LIMIT 500", args)
    return jsonify([dict(r) for r in rows])


@bp.post("/api/expenses")
@permission_required("expenses")
def expense_add():
    d = body()
    db, user = get_db(), current_user()
    amt = money_in(d, "amount", "Amount", required=True)
    if amt <= 0:
        raise BadInput("Amount must be more than zero.")
    cat = text(d, "category", "Category", max_len=40, required=True)
    with transaction(db):
        cur = db.execute("INSERT INTO expenses(category,amount_kobo,note,paid_on,user_id) VALUES (?,?,?,COALESCE(?,date('now','localtime')),?)",
                         (cat, amt, text(d, "note", max_len=160), date_str(d, "paid_on"), user["id"]))
        audit(db, user, "create", "Expense", cur.lastrowid, f"Expense {cat}: {money.naira(amt)}")
    return jsonify(ok=True)


@bp.delete("/api/expenses/<int:eid>")
@permission_required("expenses")
def expense_delete(eid):
    db = get_db()
    with transaction(db):
        db.execute("DELETE FROM expenses WHERE id=?", (eid,))
        audit(db, current_user(), "delete", "Expense", eid, "Deleted an expense")
    return jsonify(ok=True)


# ======================================================================= staff =======
@bp.get("/api/users")
@permission_required("users_view")
def users():
    rows = q(get_db(), "SELECT id,name,username,role,phone,is_active,last_login_at,created_at,(pin_hash IS NOT NULL) has_pin FROM users ORDER BY role, name")
    return jsonify([dict(r) for r in rows])


def _user_common(d, db, uid=None):
    name = text(d, "name", "Name", max_len=60, required=True)
    username = text(d, "username", "Username", max_len=30, required=True)
    if not username.replace("_", "").replace(".", "").isalnum():
        raise BadInput("Username can only use letters, numbers, dot and underscore.")
    if one(db, "SELECT 1 FROM users WHERE username=? AND id<>?", (username, uid or 0)):
        raise BadInput("That username is taken.")
    return name, username, choice(d, "role", ("owner", "manager", "cashier"), "Role", required=True), text(d, "phone", max_len=20) or None


def _pin_hash(d):
    pin = d.get("pin")
    if pin in (None, ""):
        return None
    err = valid_pin(str(pin))
    if err:
        raise BadInput(err)
    return hash_password(str(pin))


@bp.post("/api/users")
@permission_required("users")
def user_add():
    d = body()
    db, me = get_db(), current_user()
    name, username, role, phone = _user_common(d, db)
    pw = str(d.get("password") or "")
    err = valid_password(pw)
    if err:
        raise BadInput(err)
    pin = _pin_hash(d)
    if role in ("manager", "owner") and not pin:
        raise BadInput("Managers need a 4–6 digit PIN to approve refunds and discounts.")
    with transaction(db):
        cur = db.execute("INSERT INTO users(name,username,password_hash,pin_hash,role,phone) VALUES (?,?,?,?,?,?)",
                         (name, username, hash_password(pw), pin if role != "cashier" else None, role, phone))
        audit(db, me, "create", "User", cur.lastrowid, f"Added {role} {name}")
    return jsonify(ok=True, id=cur.lastrowid)


@bp.put("/api/users/<int:uid>")
@permission_required("users")
def user_edit(uid):
    d = body()
    db, me = get_db(), current_user()
    target = one(db, "SELECT * FROM users WHERE id=?", (uid,))
    if not target:
        raise BadInput("User not found.")
    name, username, role, phone = _user_common(d, db, uid)
    active = flag(d, "is_active", True)
    if uid == me["id"] and (role != "owner" or not active):
        raise BadInput("You can't remove your own owner access.")
    if target["role"] == "owner" and (role != "owner" or not active):
        if one(db, "SELECT COUNT(*) c FROM users WHERE role='owner' AND is_active=1 AND id<>?", (uid,))["c"] == 0:
            raise BadInput("There must always be at least one active owner.")
    sets, args = ["name=?", "username=?", "role=?", "phone=?", "is_active=?"], [name, username, role, phone, active]
    pw = d.get("password")
    if pw:
        err = valid_password(str(pw))
        if err:
            raise BadInput(err)
        sets += ["password_hash=?", "failed_logins=0", "locked_until=NULL"]
        args.append(hash_password(str(pw)))
    pin = _pin_hash(d)
    if pin:
        sets.append("pin_hash=?")
        args.append(pin)
    if role == "cashier":
        sets.append("pin_hash=NULL")
    elif not pin and not target["pin_hash"]:
        raise BadInput("Managers need a 4–6 digit PIN.")
    with transaction(db):
        db.execute(f"UPDATE users SET {','.join(sets)} WHERE id=?", args + [uid])
        audit(db, me, "update", "User", uid, f"Edited {name} ({role}{', deactivated' if not active else ''})")
    return jsonify(ok=True)


# ===================================================================== settings ======
TEXT_SETTINGS = {"store_name": 80, "store_address": 160, "store_phone": 30, "store_email": 80,
                 "currency_symbol": 3, "receipt_footer": 160, "backup_folder": 200}
FLAGS = ("prices_include_tax", "allow_oversell", "require_shift", "auto_backup")


@bp.get("/api/settings")
@permission_required("settings")
def settings_get():
    return jsonify(get_settings(get_db()))


@bp.put("/api/settings")
@permission_required("settings")
def settings_put():
    d = body()
    db = get_db()
    with transaction(db):
        for k, n in TEXT_SETTINGS.items():
            if k in d:
                set_setting(db, k, text(d, k, k.replace("_", " ").title(), max_len=n))
        for k in FLAGS:
            if k in d:
                set_setting(db, k, flag(d, k))
        if "tax_rate" in d:
            set_setting(db, "tax_rate", number(d, "tax_rate", "VAT rate", minimum=0, maximum=100, decimals=2))
        if "cashier_max_discount_pct" in d:
            set_setting(db, "cashier_max_discount_pct", number(d, "cashier_max_discount_pct", "Cashier discount limit", minimum=0, maximum=100, decimals=1))
        if "expiry_warning_days" in d:
            set_setting(db, "expiry_warning_days", integer(d, "expiry_warning_days", "Expiry warning days", minimum=1, maximum=365))
        if "backup_keep" in d:
            set_setting(db, "backup_keep", integer(d, "backup_keep", "Backups to keep", minimum=1, maximum=365))
        if "receipt_width_mm" in d:
            set_setting(db, "receipt_width_mm", choice(d, "receipt_width_mm", ("58", "80"), "Receipt width", default="80"))
        if "loyalty_points_per_naira" in d:
            set_setting(db, "loyalty_points_per_naira", number(d, "loyalty_points_per_naira", "Points earned", minimum=0, maximum=10, decimals=4))
        if "loyalty_naira_per_point" in d:
            set_setting(db, "loyalty_naira_per_point", number(d, "loyalty_naira_per_point", "Point value", minimum=0, maximum=1000, decimals=2))
        audit(db, current_user(), "update", "Settings", None, "Changed shop settings")
    return jsonify(ok=True)


# ===================================================================== backups =======
@bp.get("/api/backups")
@permission_required("backup")
def backups():
    return jsonify(backup.list_backups())


@bp.post("/api/backups")
@permission_required("backup")
def backup_make():
    f = backup.make_backup("manual")
    audit_db = get_db()
    with transaction(audit_db):
        audit(audit_db, current_user(), "backup", "Backup", None, f"Made backup {f.name}")
    return jsonify(ok=True, name=f.name)


@bp.get("/api/backups/<name>/download")
@permission_required("backup")
def backup_download(name):
    p = paths.backup_dir() / name.replace("/", "").replace("\\", "")
    if not p.exists() or not p.name.startswith(backup.PREFIX):
        raise BadInput("Backup not found.")
    return send_file(p, as_attachment=True, download_name=p.name)


@bp.post("/api/backups/<name>/restore")
@permission_required("backup")
def backup_restore(name):
    d = body()
    if d.get("confirm") != "RESTORE":
        raise BadInput("Type RESTORE to confirm.")
    try:
        backup.restore_backup(name)
    except (FileNotFoundError, ValueError) as e:
        raise BadInput(str(e))
    return jsonify(ok=True, message="Restored. Please sign in again.")


@bp.post("/api/demo")
@permission_required("settings")
def load_demo():
    db = get_db()
    with transaction(db):
        demo.load(db, current_user()["id"])
        audit(db, current_user(), "demo", "Settings", None, "Loaded sample products")
    return jsonify(ok=True)


# ================================================================= notifications =====
@bp.get("/api/notifications")
@permission_required("notifications")
def notifications():
    db = get_db()
    rows = q(db, "SELECT * FROM notifications ORDER BY is_read, id DESC LIMIT 100")
    unread = one(db, "SELECT COUNT(*) c FROM notifications WHERE is_read=0")["c"]
    return jsonify(unread=unread, items=[dict(r) for r in rows])


@bp.get("/api/notifications/count")
@permission_required("notifications")
def notif_count():
    return jsonify(unread=one(get_db(), "SELECT COUNT(*) c FROM notifications WHERE is_read=0")["c"])


@bp.post("/api/notifications/read")
@permission_required("notifications")
def notif_read():
    d = body()
    db = get_db()
    with transaction(db):
        if d.get("id"):
            db.execute("UPDATE notifications SET is_read=1 WHERE id=?", (int(d["id"]),))
        else:
            db.execute("UPDATE notifications SET is_read=1")
    return jsonify(ok=True)


# ======================================================================= audit =======
@bp.get("/api/audit")
@permission_required("audit")
def audit_list():
    a = request.args
    sql, args = "SELECT * FROM audit_logs WHERE 1=1", []
    if a.get("q"):
        sql += " AND (description LIKE ? OR user_name LIKE ?)"
        args += [f"%{a['q'].strip()}%"] * 2
    if a.get("action"):
        sql += " AND action=?"
        args.append(a["action"])
    return jsonify([dict(r) for r in q(get_db(), sql + " ORDER BY id DESC LIMIT 300", args)])
