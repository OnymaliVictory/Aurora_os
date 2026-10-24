"""SQLite access: one connection per request, safe settings, automatic upgrades."""
import sqlite3
from contextlib import contextmanager

from flask import g

from . import paths
from .schema import MIGRATIONS

DEFAULT_SETTINGS = {
    "store_name": "My Supermarket",
    "store_address": "",
    "store_phone": "",
    "store_email": "",
    "currency_symbol": "₦",
    "tax_rate": "7.5",                  # VAT %, Nigeria's rate
    "prices_include_tax": "1",          # shelf prices already include VAT
    "receipt_footer": "Thank you for shopping with us!",
    "receipt_width_mm": "80",
    "low_stock_default": "5",
    "expiry_warning_days": "30",
    "allow_oversell": "0",              # 1 = let the till sell more than the system thinks it has
    "cashier_max_discount_pct": "5",    # biggest % discount a cashier may give without a manager PIN
    "loyalty_points_per_naira": "0.01", # 1 point for every ₦100 spent
    "loyalty_naira_per_point": "1",     # each point is worth ₦1 when redeemed
    "require_shift": "1",               # cashiers must open a shift before selling
    "auto_backup": "1",
    "backup_keep": "14",
    "backup_folder": "",                # optional second location, e.g. a USB drive (E:\\AuroraBackup)
    "setup_done": "0",
}


def connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or paths.db_path()), timeout=15, isolation_level=None)  # we manage transactions
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")        # survives power cuts far better than the default
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in MIGRATIONS:
        if version > current:
            conn.execute("BEGIN")
            try:
                for stmt in _split(sql):
                    conn.execute(stmt)
                conn.execute(f"PRAGMA user_version = {int(version)}")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (k, v))


def _split(sql: str):
    """Split a migration into statements (our SQL has no semicolons inside strings)."""
    return [s.strip() for s in sql.split(";") if s.strip()]


def init_db(path=None) -> None:
    conn = connect(path)
    try:
        migrate(conn)
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def transaction(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE takes the write lock up front, so two tills can never both
    sell the last tin. Everything inside commits together or not at all."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


# ---- tiny helpers -------------------------------------------------------------------
def q(conn, sql, args=()):
    return conn.execute(sql, args).fetchall()


def one(conn, sql, args=()):
    return conn.execute(sql, args).fetchone()


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return DEFAULT_SETTINGS.get(key, default)
    return row["value"]


def get_settings(conn) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for r in conn.execute("SELECT key,value FROM settings"):
        out[r["key"]] = r["value"]
    return out


def set_setting(conn, key, value) -> None:
    conn.execute(
        "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, "" if value is None else str(value)),
    )


def audit(conn, user, action, entity=None, entity_id=None, description=""):
    conn.execute(
        "INSERT INTO audit_logs(user_id,user_name,action,entity,entity_id,description) VALUES (?,?,?,?,?,?)",
        (user["id"] if user else None, user["name"] if user else "System", action, entity, entity_id, description),
    )


def notify(conn, kind, title, message="", link=None, dedupe_key=None):
    """One notification per event: a low-stock alert for the same product appears once a day."""
    if dedupe_key:
        exists = conn.execute(
            "SELECT 1 FROM notifications WHERE dedupe_key=? AND date(created_at)=date('now','localtime')",
            (dedupe_key,),
        ).fetchone()
        if exists:
            return
    conn.execute(
        "INSERT INTO notifications(kind,title,message,link,dedupe_key) VALUES (?,?,?,?,?)",
        (kind, title, message, link, dedupe_key),
    )
