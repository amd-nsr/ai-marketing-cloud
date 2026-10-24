"""Conversion between major units (what people and our policies use) and the minor units
Meta's Marketing API expects for budgets.

Most currencies use 100 minor units; the ones below have offset 1 per Meta's currency
documentation (reviewed 2026-10-23; re-check before relying on a new currency).
"""

from decimal import ROUND_HALF_UP, Decimal

OFFSET_1_CURRENCIES = frozenset(
    {"CLP", "COP", "CRC", "HUF", "ISK", "IDR", "JPY", "KRW", "PYG", "TWD", "VND"}
)


def offset(currency: str) -> int:
    return 1 if currency.upper() in OFFSET_1_CURRENCIES else 100


def to_minor(amount: Decimal, currency: str) -> int:
    return int((amount * offset(currency)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def from_minor(value: int | str | None, currency: str) -> Decimal | None:
    if value in (None, ""):
        return None
    return (Decimal(str(value)) / offset(currency)).quantize(Decimal("0.01"))
