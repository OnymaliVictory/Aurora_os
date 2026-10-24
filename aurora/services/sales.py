"""The heart of the till: pricing a basket, taking payment, refunds and cash-up.

IMPORTANT: prices, discounts, VAT and totals are all worked out HERE on the server from the
product list. The browser only says "2 of product 14" — it can never decide what something costs.
(The old Laravel version trusted the prices the browser sent.)
"""
import json
from decimal import Decimal

from .. import money
from ..db import audit, get_setting, get_settings, one, transaction
from . import stock


class SaleError(Exception):
    """A problem the cashier should read, e.g. 'Not enough stock for Milo'."""


class NeedApproval(Exception):
    """The action needs a manager PIN (big discount, price change, refund)."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


METHODS = ("cash", "card", "transfer", "credit", "points")


# ---------------------------------------------------------------- pricing a basket ----
def price_cart(conn, items, *, cart_discount=None, user=None, approved=False, settings=None):
    """Return the fully priced basket.  items = [{product_id, qty, price_kobo?, discount_pct?}]"""
    s = settings or get_settings(conn)
    rate = Decimal(s["tax_rate"] or "0")
    inclusive = s["prices_include_tax"] == "1"
    cap = Decimal(s["cashier_max_discount_pct"] or "0")
    can_override = bool(user) and user["role"] in ("manager", "owner")
    can_discount = can_override
    if not items:
        raise SaleError("The basket is empty.")

    lines = []
    for it in items:
        try:
            pid = int(it["product_id"])
            qty = stock.r3(it["qty"])
        except (KeyError, TypeError, ValueError):
            raise SaleError("A line in the basket is not valid.")
        p = one(conn, "SELECT * FROM products WHERE id=? AND deleted_at IS NULL", (pid,))
        if not p or p["status"] != "active":
            raise SaleError("A product in the basket is no longer on sale.")
        if qty <= 0:
            raise SaleError(f"Quantity for {p['name']} must be more than zero.")
        if not p["is_weighed"] and qty != int(qty):
            raise SaleError(f"{p['name']} is sold in whole units.")
        price = p["price_kobo"]
        if it.get("price_kobo") not in (None, "") and int(it["price_kobo"]) != price:
            if not (can_override or approved):
                raise NeedApproval(f"Changing the price of {p['name']}")
            price = int(it["price_kobo"])
            if price < 0:
                raise SaleError("Price cannot be negative.")
        dpct = Decimal(str(it.get("discount_pct") or 0))
        if dpct < 0 or dpct > 100:
            raise SaleError("Discount must be between 0 and 100%.")
        if dpct > cap and not (can_discount or approved):
            raise NeedApproval(f"A {dpct:g}% discount on {p['name']}")
        gross = money.line_total(price, qty)
        disc = money.pct_of(gross, dpct)
        lines.append({"product": p, "product_id": pid, "name": p["name"], "qty": qty, "unit_price_kobo": price,
                      "cost_kobo": p["cost_kobo"], "gross": gross, "line_disc": disc, "extra_disc": 0,
                      "exempt": bool(p["tax_exempt"]), "unit": p["unit"], "emoji": None})

    # basket-wide discount, shared out across the lines in proportion to their value
    gross_after_lines = sum(l["gross"] - l["line_disc"] for l in lines)
    cart_disc = 0
    if cart_discount and cart_discount.get("value") not in (None, "", 0, "0"):
        kind = cart_discount.get("type")
        if kind == "pct":
            v = Decimal(str(cart_discount["value"]))
            if v < 0 or v > 100:
                raise SaleError("Discount must be between 0 and 100%.")
            if v > cap and not (can_discount or approved):
                raise NeedApproval(f"A {v:g}% discount on the whole basket")
            cart_disc = money.pct_of(gross_after_lines, v)
        elif kind == "amount":
            cart_disc = int(cart_discount["value"])
            if cart_disc < 0 or cart_disc > gross_after_lines:
                raise SaleError("That discount is more than the basket.")
            pct_equiv = Decimal(cart_disc) * 100 / Decimal(max(gross_after_lines, 1))
            if pct_equiv > cap and not (can_discount or approved):
                raise NeedApproval(f"A discount of {money.naira(cart_disc)}")
        else:
            raise SaleError("Unknown discount type.")
    if cart_disc and gross_after_lines:
        left = cart_disc
        for i, l in enumerate(lines):
            base = l["gross"] - l["line_disc"]
            share = left if i == len(lines) - 1 else int(Decimal(cart_disc) * base / gross_after_lines)
            share = min(share, base)
            l["extra_disc"] = share
            left -= share

    sub = disc = tax = total = 0
    for l in lines:
        net = l["gross"] - l["line_disc"] - l["extra_disc"]
        if l["exempt"] or rate == 0:
            t = 0
            lt = net
        elif inclusive:
            t = int((Decimal(net) * rate / (100 + rate)).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))
            lt = net
        else:
            t = money.pct_of(net, rate)
            lt = net + t
        l.update(discount_kobo=l["line_disc"] + l["extra_disc"], tax_kobo=t, total_kobo=lt)
        sub += l["gross"]
        disc += l["discount_kobo"]
        tax += t
        total += lt
    return {"lines": lines, "subtotal_kobo": sub, "discount_kobo": disc, "tax_kobo": tax, "total_kobo": total,
            "inclusive": inclusive, "tax_rate": float(rate)}


# --------------------------------------------------------------------- shifts ----------
def open_shift_of(conn, user_id):
    return one(conn, "SELECT * FROM shifts WHERE user_id=? AND status='open' ORDER BY id DESC", (user_id,))


def any_open_shift(conn):
    return one(conn, "SELECT * FROM shifts WHERE status='open' ORDER BY id DESC")


def open_shift(conn, user, float_kobo):
    if open_shift_of(conn, user["id"]):
        raise SaleError("You already have a shift open.")
    if float_kobo < 0:
        raise SaleError("Opening cash cannot be negative.")
    with transaction(conn):
        cur = conn.execute("INSERT INTO shifts(user_id,opening_float_kobo) VALUES (?,?)", (user["id"], float_kobo))
        audit(conn, user, "shift_open", "Shift", cur.lastrowid, f"Opened shift with {money.naira(float_kobo)} in the drawer")
    return cur.lastrowid


def shift_summary(conn, shift_id):
    sh = one(conn, "SELECT * FROM shifts WHERE id=?", (shift_id,))
    by = {m: 0 for m in METHODS}
    for r in conn.execute(
        "SELECT p.method, SUM(p.amount_kobo) a FROM payments p JOIN sales s ON s.id=p.sale_id "
        "WHERE s.shift_id=? GROUP BY p.method", (shift_id,)):
        by[r["method"]] = r["a"] or 0
    # voids and refunds are subtracted below, so every payment is counted here
    refunds = {"cash": 0, "other": 0}
    for r in conn.execute("SELECT method, SUM(total_kobo) a FROM refunds WHERE shift_id=? GROUP BY method", (shift_id,)):
        refunds["cash" if r["method"] == "cash" else "other"] += r["a"] or 0
    cash_in = one(conn, "SELECT COALESCE(SUM(amount_kobo),0) a FROM cash_movements WHERE shift_id=? AND kind='in'", (shift_id,))["a"]
    cash_out = one(conn, "SELECT COALESCE(SUM(amount_kobo),0) a FROM cash_movements WHERE shift_id=? AND kind='out'", (shift_id,))["a"]
    debt_cash = one(conn, "SELECT COALESCE(SUM(amount_kobo),0) a FROM customer_payments WHERE shift_id=? AND method='cash'", (shift_id,))["a"]
    sales = one(conn, "SELECT COUNT(*) n, COALESCE(SUM(total_kobo),0) t FROM sales WHERE shift_id=? AND status!='voided'", (shift_id,))
    expected = sh["opening_float_kobo"] + by["cash"] + debt_cash + cash_in - cash_out - refunds["cash"]
    return {"shift": dict(sh), "by_method": by, "refunds": refunds, "cash_in": cash_in, "cash_out": cash_out,
            "debt_cash": debt_cash, "sales_count": sales["n"], "sales_total_kobo": sales["t"],
            "expected_cash_kobo": expected}


def close_shift(conn, user, shift_id, counted_kobo, notes=""):
    sh = one(conn, "SELECT * FROM shifts WHERE id=?", (shift_id,))
    if not sh or sh["status"] != "open":
        raise SaleError("That shift is not open.")
    if sh["user_id"] != user["id"] and user["role"] == "cashier":
        raise SaleError("You can only close your own shift.")
    if counted_kobo < 0:
        raise SaleError("Counted cash cannot be negative.")
    with transaction(conn):
        summ = shift_summary(conn, shift_id)
        exp = summ["expected_cash_kobo"]
        diff = counted_kobo - exp
        conn.execute(
            "UPDATE shifts SET status='closed', closed_at=datetime('now','localtime'), counted_cash_kobo=?, "
            "expected_cash_kobo=?, difference_kobo=?, notes=? WHERE id=?", (counted_kobo, exp, diff, notes, shift_id))
        audit(conn, user, "shift_close", "Shift", shift_id,
              f"Closed shift: expected {money.naira(exp)}, counted {money.naira(counted_kobo)}, "
              f"{'short' if diff < 0 else 'over'} {money.naira(abs(diff))}" if diff else
              f"Closed shift: cash matched exactly ({money.naira(exp)})")
        if diff:
            from ..db import notify
            notify(conn, "cash_difference", "Cash difference at shift close",
                   f"{user['name']}: {'short' if diff < 0 else 'over'} by {money.naira(abs(diff))}.", "/shifts",
                   dedupe_key=f"shift:{shift_id}")
    return {**summ, "counted_cash_kobo": counted_kobo, "difference_kobo": diff}


# ------------------------------------------------------------------- the sale ----------
def _receipt_no(conn):
    row = one(conn, "SELECT date('now','localtime') d")
    d = row["d"].replace("-", "")[2:]
    n = one(conn, "SELECT COUNT(*) c FROM sales WHERE receipt_no LIKE ?", (f"AUR-{d}-%",))["c"] + 1
    while one(conn, "SELECT 1 FROM sales WHERE receipt_no=?", (f"AUR-{d}-{n:04d}",)):
        n += 1
    return f"AUR-{d}-{n:04d}"


def create_sale(conn, user, *, items, payments, customer_id=None, cart_discount=None, note="", approver=None,
                held_id=None):
    s = get_settings(conn)
    approved = approver is not None
    if s["require_shift"] == "1":
        shift = open_shift_of(conn, user["id"])
        if not shift:
            raise SaleError("Open your shift first (Cash → Open shift) before selling.")
        shift_id = shift["id"]
    else:
        sh = open_shift_of(conn, user["id"])
        shift_id = sh["id"] if sh else None

    with transaction(conn):
        cart = price_cart(conn, items, cart_discount=cart_discount, user=user, approved=approved, settings=s)
        total = cart["total_kobo"]

        customer = None
        if customer_id:
            customer = one(conn, "SELECT * FROM customers WHERE id=? AND is_active=1", (int(customer_id),))
            if not customer:
                raise SaleError("That customer was not found.")

        # ---- payments ----
        pays, tendered_cash = [], 0
        for p in payments or []:
            m = p.get("method")
            try:
                amt = int(p.get("amount_kobo") or 0)
            except (TypeError, ValueError):
                raise SaleError("A payment amount is not valid.")
            if m not in METHODS:
                raise SaleError("Unknown payment method.")
            if amt <= 0:
                continue
            pays.append({"method": m, "amount_kobo": amt, "reference": (p.get("reference") or "")[:60]})
        paid = sum(p["amount_kobo"] for p in pays)
        if paid < total:
            raise SaleError(f"Payment is short by {money.naira(total - paid)}.")
        change = paid - total
        cash_total = sum(p["amount_kobo"] for p in pays if p["method"] == "cash")
        if change > cash_total:
            raise SaleError("Only cash can be overpaid (so change can be given).")
        if change:
            for p in pays:                      # take the change out of the cash payment
                if p["method"] == "cash":
                    take = min(change, p["amount_kobo"])
                    p["amount_kobo"] -= take
                    change -= take
                    if not change:
                        break
            change = paid - total
        pays = [p for p in pays if p["amount_kobo"] > 0]

        credit_amt = sum(p["amount_kobo"] for p in pays if p["method"] == "credit")
        points_amt = sum(p["amount_kobo"] for p in pays if p["method"] == "points")
        if credit_amt or points_amt:
            if not customer:
                raise SaleError("Choose a customer to sell on credit or use points.")
        if credit_amt:
            if customer["balance_kobo"] + credit_amt > customer["credit_limit_kobo"]:
                room = max(0, customer["credit_limit_kobo"] - customer["balance_kobo"])
                raise SaleError(f"{customer['name']} can only owe {money.naira(room)} more (credit limit "
                                f"{money.naira(customer['credit_limit_kobo'])}).")
        points_used = 0
        if points_amt:
            per = Decimal(s["loyalty_naira_per_point"] or "1") * 100        # kobo per point
            points_used = int((Decimal(points_amt) / per).to_integral_value(rounding="ROUND_CEILING"))
            if points_used > customer["loyalty_points"]:
                raise SaleError(f"{customer['name']} only has {customer['loyalty_points']} points.")

        # ---- stock ----
        allow_over = s["allow_oversell"] == "1"
        short = []
        for l in cart["lines"]:
            p = l["product"]
            if p["track_stock"] and not allow_over:
                have = one(conn, "SELECT qty FROM products WHERE id=?", (p["id"],))["qty"]
                need = sum(x["qty"] for x in cart["lines"] if x["product_id"] == p["id"])
                if need > have:
                    short.append(f"{p['name']} (only {have:g} left)")
        if short:
            raise SaleError("Not enough stock for: " + ", ".join(sorted(set(short))))

        points_earned = 0
        if customer:
            points_earned = int(Decimal(total) / 100 * Decimal(s["loyalty_points_per_naira"] or "0"))
        rno = _receipt_no(conn)
        cur = conn.execute(
            "INSERT INTO sales(receipt_no,shift_id,cashier_id,customer_id,subtotal_kobo,discount_kobo,tax_kobo,"
            "total_kobo,paid_kobo,change_kobo,points_earned,note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rno, shift_id, user["id"], customer["id"] if customer else None, cart["subtotal_kobo"],
             cart["discount_kobo"], cart["tax_kobo"], total, total, change, points_earned, (note or "")[:300]))
        sale_id = cur.lastrowid
        for pm in pays:
            conn.execute("INSERT INTO payments(sale_id,method,amount_kobo,reference) VALUES (?,?,?,?)",
                         (sale_id, pm["method"], pm["amount_kobo"], pm["reference"]))
        for l in cart["lines"]:
            p = l["product"]
            used_cost = None
            if p["track_stock"]:
                taken = stock.remove_stock(conn, p["id"], l["qty"], reason="sale", ref_type="sale", ref_id=sale_id,
                                           user_id=user["id"], allow_oversell=allow_over)
                tot_q = sum(q for _, q, _ in taken) or 1
                used_cost = int(sum(q * c for _, q, c in taken) / tot_q)
            conn.execute(
                "INSERT INTO sale_items(sale_id,product_id,name,unit_price_kobo,cost_kobo,qty,discount_kobo,tax_kobo,total_kobo)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (sale_id, p["id"], l["name"], l["unit_price_kobo"], used_cost if used_cost is not None else p["cost_kobo"],
                 l["qty"], l["discount_kobo"], l["tax_kobo"], l["total_kobo"]))
            conn.execute("UPDATE products SET total_sold = ROUND(total_sold + ?,3) WHERE id=?", (l["qty"], p["id"]))
            stock.alert_if_low(conn, p["id"])

        if customer:
            conn.execute(
                "UPDATE customers SET total_spent_kobo = total_spent_kobo + ?, orders_count = orders_count + 1, "
                "loyalty_points = loyalty_points + ? - ?, balance_kobo = balance_kobo + ? WHERE id=?",
                (total, points_earned, points_used, credit_amt, customer["id"]))
        if held_id:
            conn.execute("DELETE FROM held_sales WHERE id=? AND user_id=?", (int(held_id), user["id"]))
        audit(conn, user, "sale", "Sale", sale_id, f"Sale {rno} — {money.naira(total)}" +
              (f" (approved by {approver['name']})" if approver else ""))
    return sale_id


def sale_detail(conn, sale_id):
    sale = one(conn, "SELECT s.*, u.name cashier_name, c.name customer_name, c.phone customer_phone, "
                     "c.loyalty_points customer_points "
                     "FROM sales s JOIN users u ON u.id=s.cashier_id LEFT JOIN customers c ON c.id=s.customer_id "
                     "WHERE s.id=?", (sale_id,))
    if not sale:
        return None
    d = dict(sale)
    d["items"] = [dict(r) for r in conn.execute("SELECT * FROM sale_items WHERE sale_id=? ORDER BY id", (sale_id,))]
    d["payments"] = [dict(r) for r in conn.execute("SELECT * FROM payments WHERE sale_id=? ORDER BY id", (sale_id,))]
    d["refunds"] = [dict(r) for r in conn.execute(
        "SELECT r.*, u.name user_name FROM refunds r JOIN users u ON u.id=r.user_id WHERE r.sale_id=? ORDER BY r.id", (sale_id,))]
    return d


# ------------------------------------------------------------- refunds & voids ---------
def refund_sale(conn, user, sale_id, lines, method, reason, approver, *, void=False):
    """lines = [{sale_item_id, qty, restock}].  A void is simply 'refund everything, today'."""
    if approver is None:
        raise NeedApproval("Refunding a sale")
    with transaction(conn):
        sale = one(conn, "SELECT * FROM sales WHERE id=?", (sale_id,))
        if not sale:
            raise SaleError("Sale not found.")
        if sale["status"] in ("voided", "refunded"):
            raise SaleError("This sale has already been fully " + sale["status"] + ".")
        items = {r["id"]: r for r in conn.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,))}
        if void:
            lines = [{"sale_item_id": i, "qty": it["qty"] - it["returned_qty"], "restock": True}
                     for i, it in items.items() if it["qty"] - it["returned_qty"] > 0]
        if not lines:
            raise SaleError("Choose at least one item to refund.")
        if method not in ("cash", "card", "transfer", "account"):
            raise SaleError("Choose how the money is returned.")
        shift = open_shift_of(conn, user["id"])
        total_ref = 0
        cur = conn.execute("INSERT INTO refunds(sale_id,user_id,approved_by,shift_id,total_kobo,method,reason) "
                           "VALUES (?,?,?,?,0,?,?)",
                           (sale_id, user["id"], approver["id"], shift["id"] if shift else None, method, (reason or "")[:200]))
        rid = cur.lastrowid
        for ln in lines:
            it = items.get(int(ln["sale_item_id"]))
            if not it:
                raise SaleError("An item does not belong to this sale.")
            qty = stock.r3(ln["qty"])
            left = stock.r3(it["qty"] - it["returned_qty"])
            if qty <= 0 or qty > left:
                raise SaleError(f"You can only return up to {left:g} of {it['name']}.")
            amount = it["total_kobo"] if qty == left and it["returned_qty"] == 0 else \
                int((Decimal(it["total_kobo"]) * Decimal(str(qty)) / Decimal(str(it["qty"]))).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))
            if qty == left and it["returned_qty"] > 0:             # last bit: refund exactly what is left
                paid_back = one(conn, "SELECT COALESCE(SUM(amount_kobo),0) a FROM refund_items WHERE sale_item_id=?", (it["id"],))["a"]
                amount = it["total_kobo"] - paid_back
            restock = 1 if ln.get("restock", True) else 0
            conn.execute("INSERT INTO refund_items(refund_id,sale_item_id,qty,amount_kobo,restock) VALUES (?,?,?,?,?)",
                         (rid, it["id"], qty, amount, restock))
            conn.execute("UPDATE sale_items SET returned_qty = ROUND(returned_qty + ?,3) WHERE id=?", (qty, it["id"]))
            total_ref += amount
            p = one(conn, "SELECT track_stock FROM products WHERE id=?", (it["product_id"],))
            if restock and p and p["track_stock"]:
                stock.add_stock(conn, it["product_id"], qty, reason="refund", cost_kobo=it["cost_kobo"],
                                ref_type="refund", ref_id=rid, user_id=user["id"], note=reason)
            conn.execute("UPDATE products SET total_sold = MAX(0, ROUND(total_sold - ?,3)) WHERE id=?", (qty, it["product_id"]))
        conn.execute("UPDATE refunds SET total_kobo=? WHERE id=?", (total_ref, rid))

        remaining = one(conn, "SELECT COUNT(*) c FROM sale_items WHERE sale_id=? AND qty - returned_qty > 0.0009", (sale_id,))["c"]
        status = ("voided" if void else "refunded") if remaining == 0 else "partially_refunded"
        conn.execute("UPDATE sales SET status=?, void_reason=?, voided_by=? WHERE id=?",
                     (status, (reason or "")[:200] if void else sale["void_reason"], user["id"] if void else sale["voided_by"], sale_id))
        if sale["customer_id"]:
            ratio = Decimal(total_ref) / Decimal(max(sale["total_kobo"], 1))
            pts = int(Decimal(sale["points_earned"]) * ratio)
            conn.execute(
                "UPDATE customers SET total_spent_kobo = MAX(0,total_spent_kobo - ?), loyalty_points = MAX(0,loyalty_points - ?), "
                "balance_kobo = balance_kobo - ?, orders_count = orders_count - ? WHERE id=?",
                (total_ref, pts, total_ref if method == "account" else 0, 1 if remaining == 0 else 0, sale["customer_id"]))
        audit(conn, user, "void" if void else "refund", "Sale", sale_id,
              f"{'Voided' if void else 'Refunded'} {money.naira(total_ref)} on {sale['receipt_no']} ({method}); "
              f"approved by {approver['name']}. Reason: {reason or '—'}")
    return rid, total_ref
