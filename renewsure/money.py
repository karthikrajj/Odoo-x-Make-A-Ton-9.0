"""Integer-paise calculations shared by demo seeds and invoice lines."""

from decimal import ROUND_HALF_UP, Decimal


def calc(price, qty, discount, tax):
    base = price * qty
    disc = min(base, discount)
    net = base - disc
    taxes = (net * tax + 5000) // 10000
    return dict(subtotal=base, discount=disc, tax=taxes, total=net + taxes)


def monthly_value(total, cycle):
    """Normalize one contract to monthly paise using the existing rounding policy."""
    factors = {
        "daily": Decimal(365) / 12,
        "weekly": Decimal(52) / 12,
        "monthly": Decimal(1),
        "yearly": Decimal(1) / 12,
    }
    return int(
        (Decimal(total) * factors[cycle]).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
