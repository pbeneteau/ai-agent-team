"""Unit tests for app.core.cost — pricing computation and budget checks."""

from decimal import Decimal

import pytest

from app.core.cost import (
    PRICING,
    BudgetCheckResult,
    compute_call_cost,
)


# ---------------------------------------------------------------------------
# compute_call_cost
# ---------------------------------------------------------------------------


class TestComputeCallCost:
    def test_sonnet_basic(self) -> None:
        """Ticket 2.2 verify: compute_call_cost(1000, 500, 'sonnet') returns expected value.

        Expected:
          input  = 1000 * 0.003 / 1000 = 0.003
          output =  500 * 0.015 / 1000 = 0.0075
          total  = 0.0105
        """
        result = compute_call_cost(1000, 500, "sonnet")
        assert result == Decimal("0.0105")
        assert isinstance(result, Decimal)

    def test_opus_basic(self) -> None:
        """Opus is 5x sonnet pricing."""
        result = compute_call_cost(1000, 500, "opus")
        # input  = 1000 * 0.015 / 1000 = 0.015
        # output =  500 * 0.075 / 1000 = 0.0375
        # total  = 0.0525
        assert result == Decimal("0.0525")

    def test_haiku_basic(self) -> None:
        result = compute_call_cost(1000, 500, "haiku")
        # input  = 1000 * 0.0008 / 1000 = 0.0008
        # output =  500 * 0.004  / 1000 = 0.002
        # total  = 0.0028
        assert result == Decimal("0.0028")

    def test_zero_tokens(self) -> None:
        assert compute_call_cost(0, 0, "sonnet") == Decimal("0")

    def test_input_only(self) -> None:
        result = compute_call_cost(2000, 0, "sonnet")
        # 2000 * 0.003 / 1000 = 0.006
        assert result == Decimal("0.006")

    def test_output_only(self) -> None:
        result = compute_call_cost(0, 2000, "sonnet")
        # 2000 * 0.015 / 1000 = 0.030
        assert result == Decimal("0.030")

    def test_unknown_model_falls_back_to_opus(self) -> None:
        """Unknown model tier should default to opus (most expensive) for safety."""
        result_unknown = compute_call_cost(1000, 500, "unknown-model-v99")
        result_opus = compute_call_cost(1000, 500, "opus")
        assert result_unknown == result_opus

    def test_returns_decimal_not_float(self) -> None:
        result = compute_call_cost(100, 100, "haiku")
        assert isinstance(result, Decimal)

    def test_large_token_counts(self) -> None:
        """Ensure no overflow or precision issues with large counts."""
        result = compute_call_cost(1_000_000, 500_000, "opus")
        # input  = 1_000_000 * 0.015 / 1000 = 15.0
        # output =   500_000 * 0.075 / 1000 = 37.5
        # total  = 52.5
        assert result == Decimal("52.5")


# ---------------------------------------------------------------------------
# BudgetCheckResult
# ---------------------------------------------------------------------------


class TestBudgetCheckResult:
    def test_allowed(self) -> None:
        r = BudgetCheckResult(allowed=True, remaining=Decimal("3.50"))
        assert r.allowed is True
        assert r.remaining == Decimal("3.50")

    def test_denied(self) -> None:
        r = BudgetCheckResult(allowed=False, remaining=Decimal("0.00"))
        assert r.allowed is False

    def test_immutable(self) -> None:
        r = BudgetCheckResult(allowed=True, remaining=Decimal("1.00"))
        with pytest.raises(AttributeError):
            r.allowed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pricing table sanity
# ---------------------------------------------------------------------------


class TestPricingTable:
    def test_all_tiers_present(self) -> None:
        assert set(PRICING.keys()) == {"sonnet", "opus", "haiku"}

    def test_all_values_are_decimal(self) -> None:
        for tier, rates in PRICING.items():
            assert isinstance(rates["input"], Decimal), f"{tier} input not Decimal"
            assert isinstance(rates["output"], Decimal), f"{tier} output not Decimal"

    def test_opus_most_expensive(self) -> None:
        """Opus should be the most expensive tier (used as fallback)."""
        for key in ("input", "output"):
            assert PRICING["opus"][key] >= PRICING["sonnet"][key]
            assert PRICING["opus"][key] >= PRICING["haiku"][key]
