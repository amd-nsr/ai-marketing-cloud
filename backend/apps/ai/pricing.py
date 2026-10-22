"""Cost estimates from configured list prices (USD per million tokens).

These are estimates for budgeting and quotas, never invoice amounts.
"""

from decimal import Decimal

from django.conf import settings

from .providers.base import Usage

_MILLION = Decimal(1_000_000)


def estimate_cost(model: str, usage: Usage) -> Decimal:
    prices: dict[str, float] | None = settings.AI_MODEL_PRICING.get(model)
    if prices is None:
        return Decimal(0)
    total = (
        Decimal(usage.input_tokens) * Decimal(str(prices["input"]))
        + Decimal(usage.output_tokens) * Decimal(str(prices["output"]))
        + Decimal(usage.cache_read_tokens) * Decimal(str(prices.get("cache_read", 0)))
        + Decimal(usage.cache_write_tokens) * Decimal(str(prices.get("cache_write", 0)))
    )
    return (total / _MILLION).quantize(Decimal("0.000001"))
