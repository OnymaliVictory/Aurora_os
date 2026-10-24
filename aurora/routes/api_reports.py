"""Dashboard and reports. Revenue is always counted AFTER returns, so refunds and voids never inflate it."""
import csv
import io
from datetime import date, timedelta

from flask import Blueprint, Response, jsonify, request

from ..db import get_db, one, q
from ..security import can, current_user, permission_required
from ..validate import BadInput

bp = Blueprint("reports", __name__)

KEEP = "(i.qty - i.returned_qty) / i.qty"          # share of a line that was NOT returned
REV = f"SUM(i.total_kobo * {KEEP})"
NET = f"SUM((i.total_kobo - i.tax_kobo) * {KEEP})"
COST = "SUM(i.cost_kobo * (i.qty - i.returned_qty))"


def _range():
    a = request.args
    today = date.today()
    try:
        frm = date.fromisoformat(a["from"][:10]) if a.get("from") else today - timedelta(days=29)
        to = date.fromisoformat(a["to"][:10]) if a.get("to") else today
    except ValueError:
        raise BadInput("Dates are not valid.")
    if frm > to:
        frm, to = to, frm
    if (to - frm).days > 800:
        raise BadInput("Please choose a range of under two years.")
    return frm.isoformat(), to.isoformat()


def _days(frm, to):
    d, end, out = date.fromisoformat(frm), date.fromisoformat(to), []
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _series(rows, days, key="d", val="v"):
    m = {r[key]: r[val] or 0 for r in rows}
    return [int(m.get(x, 0)) for x in days]


@bp.get("/api/dashboard")
@permission_required("pos")
def dashboard():
    db = get_db()
    profit_ok, cost_ok = can("profit"), can("cost_view")
    days = _days((date.today() - timedelta(days=6)).isoformat(), date.today().isoformat())
    base = "FROM sale_items i JOIN sales s ON s.id=i.sale_id WHERE date(s.created_at)"
    mine = "" if can("sales_all") else " AND s.cashier_id=%d" % current_user()["id"]
    today = one(db, f"SELECT COALESCE({REV},0) rev, COALESCE({NET},0) net, COALESCE({COST},0) cost {base}=date('now','localtime'){mine}")
    n = one(db, f"SELECT COUNT(*) c FROM sales s WHERE date(created_at)=date('now','localtime') AND status NOT IN ('voided','refunded'){mine}")["c"]
    week = q(db, f"SELECT date(s.created_at) d, {REV} v {base}>=? {mine} GROUP BY d", (days[0],))
    hours = q(db, f"SELECT CAST(strftime('%H',s.created_at) AS INT) h, {REV} v {base}=date('now','localtime'){mine} GROUP BY h")
    hm = {r["h"]: int(r["v"] or 0) for r in hours}
    top = q(db, f"SELECT i.product_id id, i.name, SUM(i.qty-i.returned_qty) qty, {REV} rev {base}=date('now','localtime'){mine} "
                f"GROUP BY i.product_id ORDER BY rev DESC LIMIT 5")
    mix = q(db, "SELECT p.method, SUM(p.amount_kobo) a FROM payments p JOIN sales s ON s.id=p.sale_id "
                f"WHERE date(s.created_at)=date('now','localtime') AND s.status NOT IN ('voided'){mine} GROUP BY p.method")
    out = {
        "today": {"revenue_kobo": int(today["rev"]), "sales": n, "avg_basket_kobo": int(today["rev"] / n) if n else 0},
        "week": {"labels": days, "values": _series(week, days)},
        "hours": {"labels": list(range(6, 23)), "values": [hm.get(h, 0) for h in range(6, 23)]},
        "top": [dict(r) for r in top],
        "mix": {r["method"]: r["a"] for r in mix},
    }
    if profit_ok:
        out["today"]["profit_kobo"] = int(today["net"] - today["cost"])
    if can("products"):
        out["low_stock"] = one(db, "SELECT COUNT(*) c FROM products WHERE deleted_at IS NULL AND status='active' AND track_stock=1 AND qty>0 AND qty<=min_stock")["c"]
        out["out_of_stock"] = one(db, "SELECT COUNT(*) c FROM products WHERE deleted_at IS NULL AND status='active' AND track_stock=1 AND qty<=0")["c"]
        out["expiring"] = one(db, "SELECT COUNT(DISTINCT product_id) c FROM product_lots l JOIN products p ON p.id=l.product_id WHERE p.deleted_at IS NULL AND l.qty>0 AND l.expiry_date IS NOT NULL "
                                  "AND l.expiry_date<=date('now','localtime','+30 days')")["c"]
        out["low_list"] = [dict(r) for r in q(db, "SELECT id,name,qty,min_stock,unit FROM products WHERE deleted_at IS NULL AND status='active' AND track_stock=1 AND qty<=min_stock ORDER BY qty/NULLIF(min_stock,0) LIMIT 6")]
        out["expiry_list"] = [dict(r) for r in q(db, "SELECT p.id,p.name,l.qty,l.expiry_date FROM product_lots l JOIN products p ON p.id=l.product_id WHERE p.deleted_at IS NULL AND l.qty>0 AND l.expiry_date IS NOT NULL "
                                                      "AND l.expiry_date<=date('now','localtime','+30 days') ORDER BY l.expiry_date LIMIT 6")]
    out["owed_kobo"] = one(db, "SELECT COALESCE(SUM(balance_kobo),0) a FROM customers WHERE balance_kobo>0")["a"]
    return jsonify(out)


@bp.get("/api/reports/summary")
@permission_required("reports")
def summary():
    db = get_db()
    frm, to = _range()
    days = _days(frm, to)
    base = "FROM sale_items i JOIN sales s ON s.id=i.sale_id WHERE date(s.created_at) BETWEEN ? AND ?"
    A = (frm, to)
    tot = one(db, f"SELECT COALESCE({REV},0) rev, COALESCE({NET},0) net, COALESCE({COST},0) cost, COALESCE(SUM(i.tax_kobo*{KEEP}),0) tax, "
                  f"COALESCE(SUM(i.discount_kobo*{KEEP}),0) disc {base}", A)
    cnt = one(db, "SELECT COUNT(*) c FROM sales WHERE date(created_at) BETWEEN ? AND ? AND status NOT IN ('voided','refunded')", A)["c"]
    refunded = one(db, "SELECT COALESCE(SUM(total_kobo),0) a, COUNT(*) n FROM refunds WHERE date(created_at) BETWEEN ? AND ?", A)
    exp = one(db, "SELECT COALESCE(SUM(amount_kobo),0) a FROM expenses WHERE paid_on BETWEEN ? AND ?", A)["a"]
    daily = q(db, f"SELECT date(s.created_at) d, {REV} v {base} GROUP BY d", A)
    by_cat = q(db, f"SELECT COALESCE(c.name,'Uncategorised') name, COALESCE(c.color,'#94a3b8') color, {REV} rev, {NET}-{COST} profit "
                   f"FROM sale_items i JOIN sales s ON s.id=i.sale_id JOIN products p ON p.id=i.product_id LEFT JOIN categories c ON c.id=p.category_id "
                   f"WHERE date(s.created_at) BETWEEN ? AND ? GROUP BY c.id ORDER BY rev DESC", A)
    by_user = q(db, f"SELECT u.name, COUNT(DISTINCT s.id) n, {REV} rev FROM sale_items i JOIN sales s ON s.id=i.sale_id JOIN users u ON u.id=s.cashier_id "
                    f"WHERE date(s.created_at) BETWEEN ? AND ? GROUP BY u.id ORDER BY rev DESC", A)
    mix = q(db, "SELECT p.method, SUM(p.amount_kobo) a FROM payments p JOIN sales s ON s.id=p.sale_id WHERE date(s.created_at) BETWEEN ? AND ? AND s.status!='voided' GROUP BY p.method", A)
    top = q(db, f"SELECT i.product_id id, i.name, SUM(i.qty-i.returned_qty) qty, {REV} rev, {NET}-{COST} profit {base} GROUP BY i.product_id ORDER BY rev DESC LIMIT 15", A)
    dead = q(db, "SELECT p.id,p.name,p.qty,p.cost_kobo, ROUND(p.qty*p.cost_kobo) tied FROM products p WHERE p.deleted_at IS NULL AND p.qty>0 AND p.status='active' "
                 "AND NOT EXISTS (SELECT 1 FROM sale_items i JOIN sales s ON s.id=i.sale_id WHERE i.product_id=p.id AND date(s.created_at)>=date('now','localtime','-30 days')) "
                 "ORDER BY tied DESC LIMIT 10")
    val = one(db, "SELECT COALESCE(SUM(ROUND(qty*cost_kobo)),0) cost, COALESCE(SUM(ROUND(qty*price_kobo)),0) retail FROM products WHERE deleted_at IS NULL AND qty>0")
    exp_by = q(db, "SELECT category name, SUM(amount_kobo) a FROM expenses WHERE paid_on BETWEEN ? AND ? GROUP BY category ORDER BY a DESC", A)
    out = {
        "from": frm, "to": to,
        "revenue_kobo": int(tot["rev"]), "sales": cnt, "avg_basket_kobo": int(tot["rev"] / cnt) if cnt else 0,
        "tax_kobo": int(tot["tax"]), "discount_kobo": int(tot["disc"]),
        "refunded_kobo": refunded["a"], "refunds": refunded["n"],
        "daily": {"labels": days, "values": _series(daily, days)},
        "by_category": [dict(r) for r in by_cat], "by_cashier": [dict(r) for r in by_user],
        "mix": {r["method"]: r["a"] for r in mix}, "top": [dict(r) for r in top],
    }
    if can("profit"):
        gross = int(tot["net"] - tot["cost"])
        out.update(gross_profit_kobo=gross, expenses_kobo=exp, net_profit_kobo=gross - exp,
                   margin_pct=round(gross * 100 / tot["net"], 1) if tot["net"] else 0, expenses_by=[dict(r) for r in exp_by],
                   dead_stock=[dict(r) for r in dead], stock_cost_kobo=int(val["cost"]), stock_retail_kobo=int(val["retail"]))
    else:
        for r in out["top"] + out["by_category"]:
            r.pop("profit", None)
    return jsonify(out)


@bp.get("/api/reports/sales.csv")
@permission_required("reports")
def sales_csv():
    frm, to = _range()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Receipt", "Date", "Cashier", "Customer", "Status", "Subtotal", "Discount", "VAT", "Total", "Payment methods"])
    for r in q(get_db(), "SELECT s.*, u.name cashier, c.name customer, (SELECT GROUP_CONCAT(DISTINCT method) FROM payments WHERE sale_id=s.id) m "
                         "FROM sales s JOIN users u ON u.id=s.cashier_id LEFT JOIN customers c ON c.id=s.customer_id "
                         "WHERE date(s.created_at) BETWEEN ? AND ? ORDER BY s.id", (frm, to)):
        w.writerow([r["receipt_no"], r["created_at"], r["cashier"], r["customer"] or "", r["status"], f"{r['subtotal_kobo']/100:.2f}",
                    f"{r['discount_kobo']/100:.2f}", f"{r['tax_kobo']/100:.2f}", f"{r['total_kobo']/100:.2f}", r["m"] or ""])
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=aurora-sales-{frm}-to-{to}.csv"})
