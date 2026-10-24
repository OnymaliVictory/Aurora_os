"""Login, roles, manager PINs and protection against forged requests."""
import hmac
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import abort, g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import paths
from .db import get_db, one

HASH_METHOD = "pbkdf2:sha256:600000"
MAX_FAILS = 5
LOCK_MINUTES = 2

# What each job may do. Anything not listed is refused — even if someone edits the URL.
PERMISSIONS = {
    "cashier": {"pos", "shift", "customers", "customers_edit", "sales_own", "notifications"},
}
PERMISSIONS["manager"] = PERMISSIONS["cashier"] | {
    "products", "stock", "suppliers", "purchases", "stocktake", "reports", "refunds",
    "expenses", "sales_all", "cost_view", "shifts_all", "discount_any", "price_override", "users_view",
}
PERMISSIONS["owner"] = PERMISSIONS["manager"] | {"users", "settings", "backup", "audit", "profit"}


def secret_key() -> str:
    """A random key created on first run and kept in the data folder (never in the code)."""
    f = paths.data_dir() / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
        try:
            f.chmod(0o600)
        except OSError:
            pass
    return f.read_text().strip()


def hash_password(pw: str) -> str:
    return generate_password_hash(pw, method=HASH_METHOD)


def check_password(h: str, pw: str) -> bool:
    try:
        return check_password_hash(h, pw)
    except Exception:
        return False


def valid_password(pw: str):
    if not isinstance(pw, str) or len(pw) < 6:
        return "Password must be at least 6 characters."
    return None


def valid_pin(pin: str):
    if not isinstance(pin, str) or not pin.isdigit() or not (4 <= len(pin) <= 8):
        return "PIN must be 4 to 8 digits."
    return None


def current_user():
    if hasattr(g, "_user"):
        return g._user
    uid = session.get("uid")
    user = None
    if uid:
        row = one(get_db(), "SELECT * FROM users WHERE id=? AND is_active=1", (uid,))
        user = dict(row) if row else None
    g._user = user
    return user


def can(perm: str, user=None) -> bool:
    user = user or current_user()
    return bool(user) and perm in PERMISSIONS.get(user["role"], set())


def _wants_json():
    return request.path.startswith("/api/") or request.is_json or request.headers.get("X-Requested-With") == "fetch"


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            if _wants_json():
                return jsonify(error="Please sign in again."), 401
            return redirect(url_for("pages.login", next=request.path))
        return f(*a, **kw)
    return wrapper


def permission_required(perm):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            user = current_user()
            if not user:
                if _wants_json():
                    return jsonify(error="Please sign in again."), 401
                return redirect(url_for("pages.login", next=request.path))
            if not can(perm, user):
                if _wants_json():
                    return jsonify(error="You do not have permission to do that."), 403
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco


# ---- CSRF: stops a web page in the background from secretly pressing buttons here ------
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def check_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.headers.get("X-CSRF-Token") or request.form.get("_csrf") or ""
    if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
        if _wants_json():
            return jsonify(error="Your session expired. Refresh the page and try again."), 400
        abort(400)


# ---- login throttling ----------------------------------------------------------------
def authenticate(username: str, password: str):
    """Returns (user_row, error_message)."""
    db = get_db()
    row = one(db, "SELECT * FROM users WHERE username=?", (username.strip(),))
    if row and row["locked_until"]:
        if datetime.fromisoformat(row["locked_until"]) > datetime.now():
            return None, f"Too many wrong attempts. Try again in {LOCK_MINUTES} minutes."
    if not row or not row["is_active"] or not check_password(row["password_hash"], password):
        if row:
            fails = row["failed_logins"] + 1
            locked = None
            if fails >= MAX_FAILS:
                locked = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
                fails = 0
            db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (fails, locked, row["id"]))
        return None, "Incorrect username or password."
    db.execute(
        "UPDATE users SET failed_logins=0, locked_until=NULL, last_login_at=datetime('now','localtime') WHERE id=?",
        (row["id"],),
    )
    return dict(row), None


_pin_fails = {"count": 0, "until": None}


def verify_manager_pin(pin: str):
    """A manager or owner types their PIN at the till to approve a refund / big discount.
    Returns the approving user or None. Throttled so nobody can guess PINs at the counter."""
    if _pin_fails["until"] and datetime.now() < _pin_fails["until"]:
        return None
    if not isinstance(pin, str) or not pin:
        return None
    for u in get_db().execute(
        "SELECT * FROM users WHERE is_active=1 AND role IN ('manager','owner') AND pin_hash IS NOT NULL"
    ).fetchall():
        if check_password(u["pin_hash"], pin):
            _pin_fails["count"] = 0
            return dict(u)
    _pin_fails["count"] += 1
    if _pin_fails["count"] >= 5:
        _pin_fails["until"] = datetime.now() + timedelta(minutes=LOCK_MINUTES)
        _pin_fails["count"] = 0
    return None
