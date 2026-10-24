"""Money helpers. All amounts inside the app are integer kobo."""
from decimal import Decimal, ROUND_HALF_UP


def to_kobo(value) -> int:
    """'1,250.50' / 1250.5 / '₦1250' -> 125050. Raises ValueError on rubbish."""
    if value is None or value == "":
        return 0
    if isinstance(value, int) and not isinstance(value, bool):
        return value * 100
    s = str(value).replace(",", "").replace("₦", "").strip()
    return int((Decimal(s) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def naira(kobo, symbol="₦") -> str:
    kobo = int(kobo or 0)
    sign = "-" if kobo < 0 else ""
    kobo = abs(kobo)
    whole, frac = divmod(kobo, 100)
    return f"{sign}{symbol}{whole:,}" + (f".{frac:02d}" if frac else "")


def pct_of(kobo: int, pct) -> int:
    """pct% of an amount, rounded to the nearest kobo."""
    return int((Decimal(kobo) * Decimal(str(pct)) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def line_total(unit_price_kobo: int, qty) -> int:
    """price × quantity, correctly rounded (quantity may be 1.250 kg)."""
    return int((Decimal(unit_price_kobo) * Decimal(str(qty))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
