"""Screens (HTML pages), first-run setup, sign in / out and the printable receipt."""
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for, abort

from ..db import audit, get_db, get_settings, one, set_setting, transaction
from ..security import (authenticate, can, csrf_token, current_user, hash_password, login_required,
                        permission_required, valid_password, valid_pin)
from ..services import demo, sales
from ..validate import BadInput, body, text

bp = Blueprint("pages", __name__)

# (endpoint, url, label, icon, permission, group)
NAV = [
    ("dashboard", "/", "Dashboard", "layout-dashboard", "pos", "Sell"),
    ("pos", "/pos", "Point of sale", "shopping-cart", "pos", "Sell"),
    ("sales", "/sales", "Sales & refunds", "receipt", "sales_own", "Sell"),
    ("shifts", "/shifts", "Cash drawer", "wallet", "shift", "Sell"),
    ("customers", "/customers", "Customers", "users", "customers", "Sell"),
    ("products", "/products", "Products", "package", "products", "Stock"),
    ("purchases", "/purchases", "Purchases", "truck", "purchases", "Stock"),
    ("stocktake", "/stocktake", "Stock count", "clipboard-check", "stocktake", "Stock"),
    ("suppliers", "/suppliers", "Suppliers", "boxes", "suppliers", "Stock"),
    ("expenses", "/expenses", "Expenses", "hand-coins", "expenses", "Money"),
    ("reports", "/reports", "Reports", "chart-column", "reports", "Money"),
    ("notifications", "/notifications", "Alerts", "bell", "notifications", "Admin"),
    ("users", "/users", "Staff", "shield-check", "users_view", "Admin"),
    ("audit", "/audit", "Activity log", "history", "audit", "Admin"),
    ("settings", "/settings", "Settings", "settings", "settings", "Admin"),
]


def _needs_setup():
    return one(get_db(), "SELECT 1 FROM users LIMIT 1") is None


def render_page(key, **kw):
    title = next((n[2] for n in NAV if n[0] == key), key.title())
    return render_template(f"{key}.html", page=key, title=title, nav=[n for n in NAV if can(n[4])], **kw)


def _make_page(key, perm):
    @permission_required(perm)
    def view():
        if _needs_setup():
            return redirect(url_for("pages.setup"))
        return render_page(key)
    view.__name__ = key
    return view


for _key, _url, _label, _icon, _perm, _grp in NAV:
    bp.add_url_rule(_url, _key, _make_page(_key, _perm))


# ------------------------------------------------------------------ setup wizard -----
@bp.get("/setup")
def setup():
    if not _needs_setup():
        return redirect(url_for("pages.login"))
    return render_template("setup.html", title="Welcome")


@bp.post("/api/setup")
def setup_save():
    db = get_db()
    if not _needs_setup():
        raise BadInput("Aurora OS is already set up.")
    d = body()
    store = text(d, "store_name", "Shop name", max_len=80, required=True)
    name = text(d, "name", "Your name", max_len=60, required=True)
    username = text(d, "username", "Username", max_len=30, required=True)
    if not username.replace("_", "").replace(".", "").isalnum():
        raise BadInput("Username can only use letters, numbers, dot and underscore.")
    pw = str(d.get("password") or "")
    err = valid_password(pw) or valid_pin(str(d.get("pin") or ""))
    if err:
        raise BadInput(err)
    with transaction(db):
        cur = db.execute("INSERT INTO users(name,username,password_hash,pin_hash,role) VALUES (?,?,?,?, 'owner')",
                         (name, username, hash_password(pw), hash_password(str(d["pin"]))))
        set_setting(db, "store_name", store)
        for k in ("store_address", "store_phone"):
            set_setting(db, k, text(d, k, max_len=160))
        set_setting(db, "setup_done", "1")
        if d.get("load_demo"):
            demo.load(db, cur.lastrowid)
        audit(db, {"id": cur.lastrowid, "name": name}, "setup", "Settings", None, f"Aurora OS set up for {store}")
    session.clear()
    session["uid"] = cur.lastrowid
    csrf_token()
    return jsonify(ok=True)


# ------------------------------------------------------------------- sign in / out ---
@bp.get("/login")
def login():
    if _needs_setup():
        return redirect(url_for("pages.setup"))
    if current_user():
        return redirect(url_for("pages.dashboard"))
    return render_template("login.html", title="Sign in")


@bp.post("/api/login")
def login_post():
    d = body()
    db = get_db()
    with transaction(db):
        user, err = authenticate(str(d.get("username") or ""), str(d.get("password") or ""))
        if user:
            audit(db, user, "login", "User", user["id"], f"{user['name']} signed in")
    if err:
        return jsonify(error=err), 401
    session.clear()
    session["uid"] = user["id"]
    csrf_token()
    nxt = d.get("next") or ""
    home = "/pos" if user["role"] == "cashier" else "/"
    return jsonify(ok=True, next=nxt if nxt.startswith("/") and not nxt.startswith("//") else home)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("pages.login"))


@bp.get("/api/me")
@login_required
def me():
    u = current_user()
    return jsonify(id=u["id"], name=u["name"], role=u["role"])


# ----------------------------------------------------------------------- receipt -----
@bp.get("/receipt/<int:sid>")
@permission_required("sales_own")
def receipt(sid):
    db = get_db()
    d = sales.sale_detail(db, sid)
    if not d or (not can("sales_all") and d["cashier_id"] != current_user()["id"]):
        abort(404)
    return render_template("receipt.html", s=d, cfg=get_settings(db), title=d["receipt_no"])
