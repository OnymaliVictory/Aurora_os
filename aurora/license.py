"""Subscription licence for Aurora OS.

A licence key is a signed text token issued by the Aurora website:

    AUR1.<payload>.<signature>        payload = {"v":1,"id","biz","plan","iat","exp"}

The program only holds the PUBLIC key, so it can CHECK keys (offline, no internet) but can never
make them. `exp` is the last day the subscription works. After that the program pauses: you can still
sign in, export your data and enter a new key, but not sell.

Files live in the data folder (not the database) so restoring an old backup can never bring back an old key:
    license.key   the pasted key
    license.seen  the latest date the program has seen (stops "turn the clock back" tricks)
"""
import base64
import json
from datetime import date, datetime, timedelta

from . import paths

WARN_DAYS = 7
PRICE_URL = "https://aurora-wheat-seven.vercel.app/supermarket.html"   # where "Buy / renew" opens
_PUBKEY_OVERRIDE = None          # tests set this; production reads license_public.txt


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def public_key_b64() -> str:
    if _PUBKEY_OVERRIDE is not None:
        return _PUBKEY_OVERRIDE
    f = paths.app_dir() / "license_public.txt"
    try:
        return f.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def enabled() -> bool:
    """No public key shipped = developer build, no licensing."""
    return bool(public_key_b64())


def verify(token: str):
    """Returns the payload dict if the signature is genuine, else None."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        head, body, sig = token.strip().split(".")
        if head != "AUR1":
            return None
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64()))
        try:
            raw = _b64d(body)                      # the website signs the decoded payload bytes
            key.verify(_b64d(sig), raw)
        except InvalidSignature:
            return None
        p = json.loads(raw)
        if p.get("v") != 1 or not p.get("exp"):
            return None
        date.fromisoformat(p["exp"])
        return p
    except Exception:
        return None


# ---------------------------------------------------------------- stored files
def _file(name):
    return paths.data_dir() / name


def stored_token() -> str:
    try:
        return _file("license.key").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _last_seen() -> date | None:
    try:
        return date.fromisoformat(_file("license.seen").read_text().strip())
    except Exception:
        return None


def effective_today(conn=None) -> date:
    """Real today, but never earlier than the latest day we have already seen or sold on."""
    t = date.today()
    seen = _last_seen()
    if seen and seen > t:
        t = seen
    if conn is not None:
        try:
            r = conn.execute("SELECT max(date(created_at)) d FROM sales").fetchone()
            if r and r["d"]:
                t = max(t, date.fromisoformat(r["d"]))
        except Exception:
            pass
    if t != seen:
        try:
            _file("license.seen").write_text(t.isoformat())
        except OSError:
            pass
    return t


# ---------------------------------------------------------------- state
def status(conn=None) -> dict:
    """{state: off|none|invalid|active|expiring|expired, days_left, business, plan, expires, ok}"""
    if not enabled():
        return {"state": "off", "ok": True, "days_left": None}
    tok = stored_token()
    if not tok:
        return {"state": "none", "ok": False, "days_left": None}
    p = verify(tok)
    if not p:
        return {"state": "invalid", "ok": False, "days_left": None}
    exp = date.fromisoformat(p["exp"])
    left = (exp - effective_today(conn)).days
    state = "expired" if left < 0 else "expiring" if left <= WARN_DAYS else "active"
    return {"state": state, "ok": left >= 0, "days_left": left, "business": p.get("biz", ""), "plan": p.get("plan", ""),
            "expires": exp.isoformat(), "expires_pretty": exp.strftime("%d %B %Y").lstrip("0")}


def activate(token: str, conn=None) -> dict:
    """Store a pasted key after checking it. Raises ValueError with a message the owner can read."""
    token = "".join((token or "").split())
    p = verify(token)
    if not p:
        raise ValueError("That key is not valid. Copy the whole key from your Aurora account, including the part that starts with AUR1.")
    new_exp = date.fromisoformat(p["exp"])
    if (new_exp - effective_today(conn)).days < 0:
        raise ValueError("That key has already ended. Renew on the Aurora website and paste the new key.")
    cur = verify(stored_token()) if stored_token() else None
    if cur and date.fromisoformat(cur["exp"]) >= new_exp:
        raise ValueError("You already have a key that lasts as long or longer than this one.")
    _file("license.key").write_text(token, encoding="utf-8")
    return status(conn)


def banner(conn=None):
    """Small dict for pages to show the countdown, or None when nothing needs saying."""
    s = status(conn)
    if s["state"] == "expiring":
        d = s["days_left"]
        msg = "Your Aurora OS subscription ends today." if d == 0 else "Your Aurora OS subscription ends tomorrow." if d == 1 else f"Your Aurora OS subscription ends in {d} days."
        return {"level": "warn", "message": msg + f" ({s['expires_pretty']})", "days_left": d}
    return None


def remind(conn):
    """Put one 'subscription ending' alert in the Alerts screen per day during the final week."""
    from . import db
    b = banner(conn)
    s = status(conn)
    if b:
        db.notify(conn, "license", "Subscription ending soon", b["message"] + " Renew on the Aurora website and paste the new key under Subscription.", "/license", "license-expiry")
    elif s["state"] == "expired":
        db.notify(conn, "license", "Subscription ended — selling is paused", "Renew on the Aurora website and paste the new key. Your data is safe.", "/license", "license-expired")
