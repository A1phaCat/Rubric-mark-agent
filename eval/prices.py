"""Provider list prices used to turn token counts into money, in US$ per million tokens.

Each entry is (uncached input, cached input, output), as published when the runs were made.
"""

PRICES = {"minimax-m3.1-flash": (0.15, 0.015, 0.60)}


def price_for(model: str | None) -> tuple[float, float, float] | None:
    name = str(model or "").lower()
    return next((value for key, value in PRICES.items() if name.startswith(key)), None)


def dollars(model: str | None, input_tokens: int, cached_tokens: int, output_tokens: int) -> float | None:
    price = price_for(model)
    if price is None:
        return None
    return ((input_tokens - cached_tokens) * price[0] + cached_tokens * price[1] + output_tokens * price[2]) / 1e6
