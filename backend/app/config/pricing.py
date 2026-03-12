ANTHROPIC_PRICING_USD_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-opus-4-5": {"input": 5.0, "output": 25.0},
    "_default": {"input": 3.0, "output": 15.0},
}

ANTHROPIC_PRICING_NOTE = (
    "Estimated cost based on published Anthropic pricing (March 2026). "
    "Excludes prompt caching discounts."
)
