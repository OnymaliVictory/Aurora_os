"""Small, strict input checkers. Anything that arrives from the browser goes through one of these."""
from decimal import Decimal, InvalidOperation

from flask import request

from .money import to_kobo


class BadInput(Exception):
    pass


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BadInput("Something went wrong sending that. Please try again.")
    return data


def text(d, key, label=None, *, max_len=120, required=False, default=""):
    v = d.get(key)
    if v is None or v == "":
        if required:
            raise BadInput(f"{label or key} is required.")
        return default
    if not isinstance(v, (str, int, float)):
        raise BadInput(f"{label or key} is not valid.")
    v = str(v).strip()
    if len(v) > max_len:
        raise BadInput(f"{label or key} is too long (max {max_len} characters).")
    if required and not v:
        raise BadInput(f"{label or key} is required.")
    return v


def number(d, key, label=None, *, minimum=None, maximum=None, required=False, default=0.0, decimals=3):
    v = d.get(key)
    if v is None or v == "":
        if required:
            raise BadInput(f"{label or key} is required.")
        return default
    try:
        n = Decimal(str(v).replace(",", ""))
    except (InvalidOperation, ValueError):
        raise BadInput(f"{label or key} must be a number.")
    if not n.is_finite():
        raise BadInput(f"{label or key} must be a number.")
    if minimum is not None and n < minimum:
        raise BadInput(f"{label or key} cannot be less than {minimum}.")
    if maximum is not None and n > maximum:
        raise BadInput(f"{label or key} cannot be more than {maximum}.")
    return float(round(n, decimals))


def integer(d, key, label=None, *, minimum=None, maximum=None, required=False, default=0):
    n = number(d, key, label, minimum=minimum, maximum=maximum, required=required, default=default, decimals=0)
    return int(n)


def money(d, key, label=None, *, required=False, minimum=0, default=0):
    """Reads naira from the form ('1,250.50') and returns kobo."""
    v = d.get(key)
    if v is None or v == "":
        if required:
            raise BadInput(f"{label or key} is required.")
        return default
    try:
        k = to_kobo(v)
    except (InvalidOperation, ValueError):
        raise BadInput(f"{label or key} must be an amount like 1500 or 1,500.50.")
    if k < minimum * 100:
        raise BadInput(f"{label or key} cannot be less than {minimum}.")
    if k > 10_000_000_000_00:
        raise BadInput(f"{label or key} is too large.")
    return k


def choice(d, key, options, label=None, *, default=None, required=False):
    v = d.get(key, default)
    if v is None or v == "":
        if required:
            raise BadInput(f"{label or key} is required.")
        return default
    if v not in options:
        raise BadInput(f"{label or key} is not valid.")
    return v


def flag(d, key, default=False):
    v = d.get(key, default)
    return 1 if v in (True, 1, "1", "true", "on", "yes") else 0


def date_str(d, key, label=None, *, required=False):
    v = d.get(key)
    if not v:
        if required:
            raise BadInput(f"{label or key} is required.")
        return None
    import datetime
    try:
        datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise BadInput(f"{label or key} must be a date.")
    return str(v)[:10]
