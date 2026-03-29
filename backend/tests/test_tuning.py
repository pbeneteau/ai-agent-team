"""Tests for Ticket 17.6 — tunable constants and telemetry analysis.

Covers:
  1. All tunable parameters exist in Settings with correct default values.
  2. Modules read from settings (not hardcoded).
  3. Telemetry analysis script parses events and computes correct stats.
  4. Analysis script produces a formatted markdown report.
"""

from __future__ import annotations

import json

import pytest

from app.config.settings import Settings


# ---------------------------------------------------------------------------
# Settings defaults match documented values
# ---------------------------------------------------------------------------


class TestSettingsDefaults:
    """Verify all tunable parameters exist with the original default values."""

    def test_agent_max_tool_iterations(self) -> None:
        s = Settings()
        assert s.AGENT_MAX_TOOL_ITERATIONS == 15

    def test_agent_default_max_tokens(self) -> None:
        s = Settings()
        assert s.AGENT_DEFAULT_MAX_TOKENS == 8192

    def test_memory_budget_total(self) -> None:
        s = Settings()
        assert s.AGENT_MEMORY_BUDGET_TOTAL == 8_000

    def test_memory_budget_skills(self) -> None:
        s = Settings()
        assert s.AGENT_MEMORY_BUDGET_SKILLS == 6_000

    def test_memory_budget_learnings(self) -> None:
        s = Settings()
        assert s.AGENT_MEMORY_BUDGET_LEARNINGS == 2_000

    def test_memory_budget_breakdown(self) -> None:
        s = Settings()
        assert s.AGENT_MEMORY_BUDGET_SKILLS + s.AGENT_MEMORY_BUDGET_LEARNINGS == s.AGENT_MEMORY_BUDGET_TOTAL

    def test_upstream_token_cap(self) -> None:
        s = Settings()
        assert s.AGENT_UPSTREAM_TOKEN_CAP == 15_000

    def test_slot_max_retries(self) -> None:
        s = Settings()
        assert s.AGENT_SLOT_MAX_RETRIES == 3

    def test_slot_retry_backoff_base(self) -> None:
        s = Settings()
        assert s.AGENT_SLOT_RETRY_BACKOFF_BASE == 2

    def test_max_validation_replans(self) -> None:
        s = Settings()
        assert s.AGENT_MAX_VALIDATION_REPLANS == 1

    def test_context_summarization_threshold(self) -> None:
        s = Settings()
        assert s.AGENT_CONTEXT_SUMMARIZATION_THRESHOLD == 60_000

    def test_summarization_check_interval(self) -> None:
        s = Settings()
        assert s.AGENT_SUMMARIZATION_CHECK_INTERVAL == 3

    def test_code_exec_timeout(self) -> None:
        s = Settings()
        assert s.AGENT_CODE_EXEC_TIMEOUT == 30


# ---------------------------------------------------------------------------
# Modules read from settings (not hardcoded)
# ---------------------------------------------------------------------------


class TestModulesUseSettings:
    def test_memory_budget_from_settings(self) -> None:
        from app.agents.memory import MEMORY_BUDGET_TOTAL, MEMORY_BUDGET_SKILLS, MEMORY_BUDGET_LEARNINGS
        from app.config.settings import settings

        assert MEMORY_BUDGET_TOTAL == settings.AGENT_MEMORY_BUDGET_TOTAL
        assert MEMORY_BUDGET_SKILLS == settings.AGENT_MEMORY_BUDGET_SKILLS
        assert MEMORY_BUDGET_LEARNINGS == settings.AGENT_MEMORY_BUDGET_LEARNINGS

    def test_upstream_cap_from_settings(self) -> None:
        from app.agents.upstream import UPSTREAM_TOKEN_CAP
        from app.config.settings import settings

        assert UPSTREAM_TOKEN_CAP == settings.AGENT_UPSTREAM_TOKEN_CAP

    def test_slot_retries_from_settings(self) -> None:
        from app.agents.orchestrator import _SLOT_MAX_RETRIES, _SLOT_RETRY_BACKOFF_BASE
        from app.config.settings import settings

        assert _SLOT_MAX_RETRIES == settings.AGENT_SLOT_MAX_RETRIES
        assert _SLOT_RETRY_BACKOFF_BASE == settings.AGENT_SLOT_RETRY_BACKOFF_BASE

    def test_validation_replans_from_settings(self) -> None:
        from app.agents.orchestrator import _MAX_VALIDATION_REPLANS
        from app.config.settings import settings

        assert _MAX_VALIDATION_REPLANS == settings.AGENT_MAX_VALIDATION_REPLANS

    def test_summarization_interval_from_settings(self) -> None:
        from app.agents.anthropic_runner import _SUMMARIZATION_CHECK_INTERVAL
        from app.config.settings import settings

        assert _SUMMARIZATION_CHECK_INTERVAL == settings.AGENT_SUMMARIZATION_CHECK_INTERVAL

    def test_code_exec_timeout_from_settings(self) -> None:
        from app.tools.code_exec import _TIMEOUT_SECONDS
        from app.config.settings import settings

        assert _TIMEOUT_SECONDS == settings.AGENT_CODE_EXEC_TIMEOUT


# ---------------------------------------------------------------------------
# Telemetry analysis script
# ---------------------------------------------------------------------------


class TestTelemetryAnalysis:
    def _make_agent_run_line(self, **overrides: object) -> str:
        data = {
            "event": "agent_run",
            "wave_id": "wave-1",
            "slot_key": "backend_impl",
            "agent_id": "agent-1",
            "phase": "execution",
            "model": "claude-sonnet-4-20250514",
            "tool_loop_iterations": 4,
            "tool_calls": ["file_write", "file_read", "file_write"],
            "input_tokens": 3000,
            "output_tokens": 1500,
            "elapsed_seconds": 8.5,
            "context_tokens_peak": 2800,
        }
        data.update(overrides)
        return json.dumps(data)

    def _make_review_line(self, **overrides: object) -> str:
        data = {
            "event": "review_loop",
            "wave_id": "wave-1",
            "iteration_number": 1,
            "consensus_decision": "APPROVE",
            "decisions_by_lead": {"Tech Lead": "APPROVE"},
            "elapsed_seconds": 25.0,
        }
        data.update(overrides)
        return json.dumps(data)

    def _make_compaction_line(self, **overrides: object) -> str:
        data = {
            "event": "memory_compaction",
            "agent_id": "agent-1",
            "before_tokens": 9000,
            "after_tokens": 5500,
            "entries_before": 12,
            "entries_after": 4,
            "elapsed_seconds": 2.0,
        }
        data.update(overrides)
        return json.dumps(data)

    def _make_summarization_line(self, **overrides: object) -> str:
        data = {
            "event": "context_summarization",
            "before_tokens": 70000,
            "after_tokens": 15000,
            "iteration": 6,
            "reduction_pct": 78.6,
        }
        data.update(overrides)
        return json.dumps(data)

    def test_parse_agent_run_events(self) -> None:
        from scripts.analyze_telemetry import parse_telemetry

        lines = [
            self._make_agent_run_line(tool_loop_iterations=3),
            self._make_agent_run_line(tool_loop_iterations=7),
            self._make_agent_run_line(tool_loop_iterations=5),
        ]
        report = parse_telemetry(lines)

        assert report.tool_iterations.count == 3
        assert report.tool_iterations.min == 3
        assert report.tool_iterations.max == 7
        assert report.total_events == 3

    def test_parse_review_events(self) -> None:
        from scripts.analyze_telemetry import parse_telemetry

        lines = [
            self._make_review_line(consensus_decision="APPROVE"),
            self._make_review_line(consensus_decision="REVISE"),
            self._make_review_line(consensus_decision="APPROVE"),
        ]
        report = parse_telemetry(lines)

        assert report.review_decisions["APPROVE"] == 2
        assert report.review_decisions["REVISE"] == 1

    def test_parse_compaction_events(self) -> None:
        from scripts.analyze_telemetry import parse_telemetry

        lines = [self._make_compaction_line()]
        report = parse_telemetry(lines)

        assert report.compaction_count == 1
        assert report.compaction_before.mean == 9000
        assert report.compaction_after.mean == 5500

    def test_parse_summarization_events(self) -> None:
        from scripts.analyze_telemetry import parse_telemetry

        lines = [self._make_summarization_line()]
        report = parse_telemetry(lines)

        assert report.summarization_count == 1
        assert report.summarization_before.mean == 70000

    def test_parse_mixed_events(self) -> None:
        from scripts.analyze_telemetry import parse_telemetry

        lines = [
            self._make_agent_run_line(),
            self._make_review_line(),
            self._make_compaction_line(),
            self._make_summarization_line(),
            "not a json line",
            "",
        ]
        report = parse_telemetry(lines)

        assert report.total_events == 4
        assert report.tool_iterations.count == 1
        assert report.review_iterations.count == 1
        assert report.compaction_count == 1
        assert report.summarization_count == 1

    def test_parse_empty_input(self) -> None:
        from scripts.analyze_telemetry import parse_telemetry

        report = parse_telemetry([])
        assert report.total_events == 0
        assert report.tool_iterations.count == 0

    def test_parse_handles_prefixed_log_lines(self) -> None:
        """Log lines may have timestamp/logger prefixes before the JSON."""
        from scripts.analyze_telemetry import parse_telemetry

        line = f'2026-03-29 10:00:00 INFO telemetry {self._make_agent_run_line()}'
        report = parse_telemetry([line])
        assert report.total_events == 1

    def test_format_report_produces_markdown(self) -> None:
        from scripts.analyze_telemetry import format_report, parse_telemetry

        lines = [
            self._make_agent_run_line(tool_loop_iterations=3),
            self._make_agent_run_line(tool_loop_iterations=5),
            self._make_review_line(consensus_decision="APPROVE"),
        ]
        report = parse_telemetry(lines)
        markdown = format_report(report)

        assert "# Telemetry Analysis Report" in markdown
        assert "Tool Loop Iterations" in markdown
        assert "Parameter Summary" in markdown
        assert "AGENT_MAX_TOOL_ITERATIONS" in markdown

    def test_format_report_empty_data(self) -> None:
        from scripts.analyze_telemetry import format_report, parse_telemetry

        report = parse_telemetry([])
        markdown = format_report(report)

        assert "No agent_run events found" in markdown

    def test_distribution_percentiles(self) -> None:
        from scripts.analyze_telemetry import Distribution

        d = Distribution()
        for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
            d.add(v)

        assert d.p50 == 5.5
        assert d.min == 1
        assert d.max == 10
        assert d.mean == 5.5

    def test_distribution_single_value(self) -> None:
        from scripts.analyze_telemetry import Distribution

        d = Distribution()
        d.add(42)
        assert d.p50 == 42
        assert d.p95 == 42

    def test_distribution_empty(self) -> None:
        from scripts.analyze_telemetry import Distribution

        d = Distribution()
        assert d.p50 == 0.0
        assert d.count == 0
        assert d.mean == 0.0

    def test_runs_by_phase_counted(self) -> None:
        from scripts.analyze_telemetry import parse_telemetry

        lines = [
            self._make_agent_run_line(phase="planning"),
            self._make_agent_run_line(phase="planning"),
            self._make_agent_run_line(phase="execution"),
            self._make_agent_run_line(phase="review"),
        ]
        report = parse_telemetry(lines)

        assert report.runs_by_phase["planning"] == 2
        assert report.runs_by_phase["execution"] == 1
        assert report.runs_by_phase["review"] == 1
