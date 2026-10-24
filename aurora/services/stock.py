"""All stock changes go through here, so the numbers can never drift apart:
   product.qty  ==  SUM(product_lots.qty)  ==  the running total in stock_movements."""
from decimal import Decimal

from ..db import notify, get_setting, one


class StockError(Exception):
    pass


def r3(x) -> float:
    return float(round(Decimal(str(x)), 3))


def _bump(conn, product_id, delta):
    conn.execute("UPDATE products SET qty = ROUND(qty + ?, 3), updated_at=datetime('now','localtime') WHERE id=?",
                 (delta, product_id))
    return conn.execute("SELECT qty FROM products WHERE id=?", (product_id,)).fetchone()["qty"]


def _move(conn, product_id, lot_id, delta, after, reason, ref_type, ref_id, user_id, note):
    conn.execute(
        "INSERT INTO stock_movements(product_id,lot_id,qty_change,qty_after,reason,ref_type,ref_id,user_id,note)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (product_id, lot_id, delta, after, reason, ref_type, ref_id, user_id, note),
    )


def add_stock(conn, product_id, qty, *, reason="purchase", expiry=None, cost_kobo=None,
              ref_type=None, ref_id=None, user_id=None, note=None, po_id=None):
    """Put new stock on the shelf as a batch (a 'lot') with its own expiry date."""
    qty = r3(qty)
    if qty <= 0:
        raise StockError("Quantity must be more than zero.")
    prod = one(conn, "SELECT id, cost_kobo FROM products WHERE id=?", (product_id,))
    if not prod:
        raise StockError("Product not found.")
    cost = prod["cost_kobo"] if cost_kobo is None else int(cost_kobo)
    cur = conn.execute(
        "INSERT INTO product_lots(product_id,qty,expiry_date,cost_kobo,note,po_id) VALUES (?,?,?,?,?,?)",
        (product_id, qty, expiry or None, cost, note, po_id),
    )
    after = _bump(conn, product_id, qty)
    _move(conn, product_id, cur.lastrowid, qty, after, reason, ref_type, ref_id, user_id, note)
    return cur.lastrowid


def remove_stock(conn, product_id, qty, *, reason="sale", ref_type=None, ref_id=None, user_id=None,
                 note=None, allow_oversell=False, lot_id=None):
    """Take stock out, oldest-expiry first (FEFO). Returns [(lot_id, qty_taken, cost_kobo), ...]."""
    qty = r3(qty)
    if qty <= 0:
        raise StockError("Quantity must be more than zero.")
    if lot_id:
        lots = conn.execute("SELECT * FROM product_lots WHERE id=? AND product_id=? AND qty>0", (lot_id, product_id)).fetchall()
    else:
        lots = conn.execute(
            "SELECT * FROM product_lots WHERE product_id=? AND qty>0 "
            "ORDER BY (expiry_date IS NULL), expiry_date, received_at, id", (product_id,)).fetchall()
    need, taken = qty, []
    for lot in lots:
        if need <= 0:
            break
        use = r3(min(lot["qty"], need))
        conn.execute("UPDATE product_lots SET qty = ROUND(qty - ?, 3) WHERE id=?", (use, lot["id"]))
        after = _bump(conn, product_id, -use)
        _move(conn, product_id, lot["id"], -use, after, reason, ref_type, ref_id, user_id, note)
        taken.append((lot["id"], use, lot["cost_kobo"]))
        need = r3(need - use)
    if need > 0:
        if not allow_oversell:
            raise StockError("Not enough stock.")
        # The shelf has more than the system knew about: record a negative 'catch-up' batch.
        prod = one(conn, "SELECT cost_kobo FROM products WHERE id=?", (product_id,))
        cur = conn.execute("INSERT INTO product_lots(product_id,qty,cost_kobo,note) VALUES (?,?,?,?)",
                           (product_id, -need, prod["cost_kobo"], "sold beyond recorded stock"))
        after = _bump(conn, product_id, -need)
        _move(conn, product_id, cur.lastrowid, -need, after, reason, ref_type, ref_id, user_id, note or "oversold")
        taken.append((cur.lastrowid, need, prod["cost_kobo"]))
    return taken


def set_stock_level(conn, product_id, new_qty, *, reason="correction", user_id=None, note=None,
                    ref_type=None, ref_id=None):
    """Make the system match a physical count."""
    new_qty = r3(new_qty)
    if new_qty < 0:
        raise StockError("Stock cannot be negative.")
    cur = one(conn, "SELECT qty FROM products WHERE id=?", (product_id,))["qty"]
    diff = r3(new_qty - cur)
    if diff > 0:
        add_stock(conn, product_id, diff, reason=reason, user_id=user_id, note=note, ref_type=ref_type, ref_id=ref_id)
    elif diff < 0:
        # corrections remove from the oldest batches; also clean up negative catch-up lots
        remove_stock(conn, product_id, -diff, reason=reason, user_id=user_id, note=note, ref_type=ref_type,
                     ref_id=ref_id, allow_oversell=True)
    return diff


def alert_if_low(conn, product_id):
    p = one(conn, "SELECT id,name,qty,min_stock,track_stock FROM products WHERE id=?", (product_id,))
    if not p or not p["track_stock"]:
        return
    if p["qty"] <= 0:
        notify(conn, "out_of_stock", "Out of stock", f"{p['name']} is finished.", "/products?filter=out",
               dedupe_key=f"oos:{p['id']}")
    elif p["qty"] <= p["min_stock"]:
        notify(conn, "low_stock", "Running low", f"{p['name']}: only {p['qty']:g} left (minimum {p['min_stock']:g}).",
               "/products?filter=low", dedupe_key=f"low:{p['id']}")


def scan_expiry(conn):
    """Raise notifications for batches that have expired or will soon."""
    days = int(get_setting(conn, "expiry_warning_days", 30))
    rows = conn.execute(
        "SELECT p.id, p.name, l.expiry_date, l.qty FROM product_lots l JOIN products p ON p.id=l.product_id "
        "WHERE l.qty>0 AND l.expiry_date IS NOT NULL AND p.deleted_at IS NULL AND l.expiry_date <= date('now','localtime',?)",
        (f"+{days} days",)).fetchall()
    for r in rows:
        expired = r["expiry_date"] <= conn.execute("SELECT date('now','localtime')").fetchone()[0]
        notify(conn, "expired" if expired else "expiring",
               "Expired stock" if expired else "Expiring soon",
               f"{r['name']}: {r['qty']:g} units {'expired on' if expired else 'expire on'} {r['expiry_date']}.",
               "/products?filter=expiry", dedupe_key=f"exp:{r['id']}:{r['expiry_date']}")
