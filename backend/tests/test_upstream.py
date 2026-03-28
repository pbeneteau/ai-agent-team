"""Unit tests for Ticket 3.5 — upstream context builder.

Verify section:
  1. truncate_middle() on a 20,000-token string returns ~15,000 tokens with the marker.
  2. truncate_middle() on a 10,000-token string returns the string unchanged.
  3. build_upstream_context() assembles correct sections from a mock wave_outputs dict.
  4. Empty depends_on returns None.
  5. Missing slot output is handled gracefully (no crash).
"""

from dataclasses import dataclass

import pytest

from app.agents.memory import count_tokens
from app.agents.upstream import (
    HEAD_RATIO,
    TAIL_RATIO,
    UPSTREAM_TOKEN_CAP,
    WaveOutput,
    build_upstream_context,
    truncate_middle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text(target_tokens: int) -> str:
    """Generate a multi-line string of approximately ``target_tokens`` tokens.

    Uses varied sentences so the output resembles realistic agent output
    and exercises the line-based truncation paths.
    """
    sentences = [
        "The quarterly revenue grew by 15% year-over-year.",
        "Customer acquisition cost decreased to $42 per user.",
        "The design system uses oklch color space for perceptual uniformity.",
        "API latency at p99 is 230ms, well within the 500ms SLA.",
        "The frontend bundle size is 142KB gzipped after tree-shaking.",
        "PostgreSQL handles 3,200 queries per second on the read replica.",
        "The agent completed the research phase in under 90 seconds.",
        "Brand guidelines specify Inter for body text and JetBrains Mono for code.",
        "The competitor analysis covers 12 companies across 3 market segments.",
        "Unit test coverage stands at 87% with all critical paths covered.",
    ]
    lines: list[str] = []
    current_tokens = 0
    idx = 0
    while current_tokens < target_tokens:
        line = sentences[idx % len(sentences)]
        lines.append(line)
        current_tokens += count_tokens(line)
        idx += 1
    return "\n".join(lines)


@dataclass
class _MockWave:
    """Minimal stand-in for DagWave."""

    depends_on: list[str]


def _make_output(
    text: str = "Some upstream output.",
    agent_name: str = "Aria",
    slot_label: str = "Product Specification",
) -> WaveOutput:
    return WaveOutput(text=text, agent_name=agent_name, slot_label=slot_label)


# ---------------------------------------------------------------------------
# Verify 1: truncate_middle() on over-budget text
# ---------------------------------------------------------------------------


class TestTruncateMiddleOverBudget:
    def test_20k_tokens_truncated_to_about_15k(self) -> None:
        """A 20,000-token string should be truncated to ~15,000 tokens."""
        text = _make_text(20_000)
        assert count_tokens(text) >= 20_000

        result = truncate_middle(text, max_tokens=15_000)

        result_tokens = count_tokens(result)
        # Should be close to 15,000 (line-level granularity means not exact)
        assert result_tokens <= 16_000, f"Result too large: {result_tokens}"
        assert result_tokens >= 14_000, f"Result too small: {result_tokens}"

    def test_truncation_marker_present(self) -> None:
        text = _make_text(20_000)
        result = truncate_middle(text, max_tokens=15_000)
        assert "tokens truncated for brevity" in result

    def test_marker_reports_positive_truncated_count(self) -> None:
        text = _make_text(20_000)
        result = truncate_middle(text, max_tokens=15_000)
        # Extract the truncated count from the marker
        import re

        match = re.search(r"\[... (\d+) tokens truncated", result)
        assert match is not None
        truncated = int(match.group(1))
        assert truncated > 0

    def test_head_tail_ratio(self) -> None:
        """Head should be ~47% and tail ~53% of the budget."""
        text = _make_text(30_000)
        result = truncate_middle(text, max_tokens=15_000)

        # Split at the marker to get head and tail
        parts = result.split("[...")
        assert len(parts) == 2
        head = parts[0].rstrip()
        tail_with_marker = parts[1]
        # Extract tail after the marker line
        tail = tail_with_marker.split("...]\n\n", 1)[1] if "...]\n\n" in tail_with_marker else ""

        head_tokens = count_tokens(head)
        tail_tokens = count_tokens(tail)

        # Head should be roughly 47% of 15,000 = ~7,050
        assert head_tokens >= 5_500, f"Head too small: {head_tokens}"
        assert head_tokens <= 8_500, f"Head too large: {head_tokens}"

        # Tail should be roughly 53% of 15,000 = ~7,950
        assert tail_tokens >= 6_500, f"Tail too small: {tail_tokens}"
        assert tail_tokens <= 9_500, f"Tail too large: {tail_tokens}"

    def test_preserves_beginning_content(self) -> None:
        """The start of the original text should be in the result."""
        text = _make_text(20_000)
        first_line = text.split("\n")[0]
        result = truncate_middle(text, max_tokens=15_000)
        assert first_line in result

    def test_preserves_ending_content(self) -> None:
        """The end of the original text should be in the result."""
        text = _make_text(20_000)
        last_line = text.split("\n")[-1]
        result = truncate_middle(text, max_tokens=15_000)
        assert last_line in result

    def test_custom_max_tokens(self) -> None:
        """Truncation respects a custom max_tokens value."""
        text = _make_text(10_000)
        result = truncate_middle(text, max_tokens=5_000)
        assert "tokens truncated for brevity" in result
        assert count_tokens(result) <= 6_000


# ---------------------------------------------------------------------------
# Verify 2: truncate_middle() on under-budget text
# ---------------------------------------------------------------------------


class TestTruncateMiddleUnderBudget:
    def test_10k_tokens_returned_unchanged(self) -> None:
        """A 10,000-token string should be returned unchanged."""
        text = _make_text(10_000)
        result = truncate_middle(text, max_tokens=15_000)
        assert result == text

    def test_exact_budget_returned_unchanged(self) -> None:
        """Text exactly at the budget should not be truncated."""
        text = _make_text(15_000)
        # If it happens to be exactly at 15k, it should pass through
        if count_tokens(text) <= 15_000:
            result = truncate_middle(text, max_tokens=15_000)
            assert result == text
            assert "truncated" not in result

    def test_empty_string(self) -> None:
        result = truncate_middle("", max_tokens=15_000)
        assert result == ""

    def test_short_string(self) -> None:
        result = truncate_middle("Hello world.", max_tokens=15_000)
        assert result == "Hello world."


# ---------------------------------------------------------------------------
# Verify 3: build_upstream_context() assembles correct sections
# ---------------------------------------------------------------------------


class TestBuildUpstreamContext:
    def test_single_dependency(self) -> None:
        wave = _MockWave(depends_on=["product_spec"])
        outputs = {
            "product_spec": _make_output(
                text="Requirements doc content.",
                agent_name="Aria",
                slot_label="Product Specification",
            ),
        }

        result = build_upstream_context(wave, outputs)
        assert result is not None
        assert "## Upstream Output — Aria: Product Specification" in result
        assert "Requirements doc content." in result

    def test_multiple_dependencies(self) -> None:
        wave = _MockWave(depends_on=["product_spec", "design_spec"])
        outputs = {
            "product_spec": _make_output(
                text="Product requirements here.",
                agent_name="Aria",
                slot_label="Product Specification",
            ),
            "design_spec": _make_output(
                text="Design tokens and layout rules.",
                agent_name="Viktor",
                slot_label="Design Specification",
            ),
        }

        result = build_upstream_context(wave, outputs)
        assert result is not None
        assert "## Upstream Output — Aria: Product Specification" in result
        assert "## Upstream Output — Viktor: Design Specification" in result
        assert "Product requirements here." in result
        assert "Design tokens and layout rules." in result
        # Sections separated by ---
        assert "\n\n---\n\n" in result

    def test_sections_in_depends_on_order(self) -> None:
        """Upstream sections appear in the same order as depends_on."""
        wave = _MockWave(depends_on=["design_spec", "product_spec"])
        outputs = {
            "product_spec": _make_output(
                text="Product content.",
                agent_name="Aria",
                slot_label="Product Specification",
            ),
            "design_spec": _make_output(
                text="Design content.",
                agent_name="Viktor",
                slot_label="Design Specification",
            ),
        }

        result = build_upstream_context(wave, outputs)
        assert result is not None
        idx_design = result.index("Design Specification")
        idx_product = result.index("Product Specification")
        assert idx_design < idx_product

    def test_truncation_applied_per_dependency(self) -> None:
        """Each upstream output is individually truncated at 15k tokens."""
        long_text = _make_text(20_000)
        wave = _MockWave(depends_on=["slot_a"])
        outputs = {
            "slot_a": _make_output(
                text=long_text,
                agent_name="Researcher",
                slot_label="Research Output",
            ),
        }

        result = build_upstream_context(wave, outputs)
        assert result is not None
        assert "tokens truncated for brevity" in result


# ---------------------------------------------------------------------------
# Verify 4: empty depends_on returns None
# ---------------------------------------------------------------------------


class TestEmptyDependencies:
    def test_empty_depends_on_returns_none(self) -> None:
        wave = _MockWave(depends_on=[])
        result = build_upstream_context(wave, {})
        assert result is None

    def test_no_depends_on_attribute_returns_none(self) -> None:
        """An object without depends_on should be treated as no dependencies."""

        class _BareWave:
            pass

        wave = _BareWave()
        result = build_upstream_context(wave, {})
        assert result is None


# ---------------------------------------------------------------------------
# Verify 5: missing/failed upstream slot output handled gracefully
# ---------------------------------------------------------------------------


class TestMissingSlotOutput:
    def test_missing_slot_does_not_crash(self) -> None:
        """A slot referenced in depends_on but missing from wave_outputs is skipped."""
        wave = _MockWave(depends_on=["missing_slot"])
        result = build_upstream_context(wave, {})
        assert result is None

    def test_missing_slot_among_valid_slots(self) -> None:
        """Missing slots are skipped; valid slots are still assembled."""
        wave = _MockWave(depends_on=["valid_slot", "missing_slot"])
        outputs = {
            "valid_slot": _make_output(
                text="Valid output.",
                agent_name="Aria",
                slot_label="Valid Slot",
            ),
        }

        result = build_upstream_context(wave, outputs)
        assert result is not None
        assert "Valid output." in result
        assert "missing_slot" not in result

    def test_empty_output_text_is_skipped(self) -> None:
        """A slot with empty text output is skipped."""
        wave = _MockWave(depends_on=["empty_slot"])
        outputs = {
            "empty_slot": _make_output(
                text="",
                agent_name="Aria",
                slot_label="Empty Slot",
            ),
        }

        result = build_upstream_context(wave, outputs)
        assert result is None

    def test_whitespace_only_output_is_skipped(self) -> None:
        """A slot with whitespace-only text is treated as empty."""
        wave = _MockWave(depends_on=["ws_slot"])
        outputs = {
            "ws_slot": _make_output(
                text="   \n\n  ",
                agent_name="Aria",
                slot_label="Whitespace Slot",
            ),
        }

        result = build_upstream_context(wave, outputs)
        assert result is None

    def test_all_slots_missing_returns_none(self) -> None:
        """If all dependencies are missing/empty, returns None."""
        wave = _MockWave(depends_on=["missing_a", "missing_b"])
        result = build_upstream_context(wave, {})
        assert result is None
