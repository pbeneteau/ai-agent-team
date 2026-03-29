#!/usr/bin/env python3
"""Telemetry analysis script — parse structured JSON logs and produce a tuning report.

Ref: Ticket 17.6 (AD-30).

Reads telemetry log lines (from stdin or a file) and computes statistics
for every tunable parameter.  Outputs a markdown report with current values,
observed P50/P95/max, and tuning recommendations.

Usage:
    # From log file
    python scripts/analyze_telemetry.py telemetry.log

    # From stdin (e.g., grep from combined logs)
    grep '"event":' app.log | python scripts/analyze_telemetry.py

    # From Docker logs
    docker compose logs worker 2>&1 | grep telemetry | python scripts/analyze_telemetry.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Distribution:
    """Collects numeric values and computes percentile statistics."""

    values: list[float] = field(default_factory=list)

    def add(self, value: float) -> None:
        self.values.append(value)

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def p50(self) -> float:
        return self._percentile(50)

    @property
    def p95(self) -> float:
        return self._percentile(95)

    @property
    def max(self) -> float:
        return max(self.values) if self.values else 0.0

    @property
    def min(self) -> float:
        return min(self.values) if self.values else 0.0

    @property
    def mean(self) -> float:
        return sum(self.values) / len(self.values) if self.values else 0.0

    def _percentile(self, pct: int) -> float:
        if not self.values:
            return 0.0
        sorted_vals = sorted(self.values)
        idx = (pct / 100) * (len(sorted_vals) - 1)
        lower = int(math.floor(idx))
        upper = int(math.ceil(idx))
        if lower == upper:
            return sorted_vals[lower]
        frac = idx - lower
        return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac


@dataclass
class TelemetryReport:
    """Aggregated telemetry data across all events."""

    # agent_run events
    tool_iterations: Distribution = field(default_factory=Distribution)
    input_tokens: Distribution = field(default_factory=Distribution)
    output_tokens: Distribution = field(default_factory=Distribution)
    context_tokens_peak: Distribution = field(default_factory=Distribution)
    elapsed_seconds: Distribution = field(default_factory=Distribution)
    tool_call_counts: Distribution = field(default_factory=Distribution)
    runs_by_phase: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    runs_by_model: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # review_loop events
    review_decisions: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    review_iterations: Distribution = field(default_factory=Distribution)
    review_elapsed: Distribution = field(default_factory=Distribution)

    # memory_compaction events
    compaction_count: int = 0
    compaction_before: Distribution = field(default_factory=Distribution)
    compaction_after: Distribution = field(default_factory=Distribution)
    compaction_reduction_pct: Distribution = field(default_factory=Distribution)

    # context_summarization events
    summarization_count: int = 0
    summarization_before: Distribution = field(default_factory=Distribution)
    summarization_after: Distribution = field(default_factory=Distribution)
    summarization_reduction_pct: Distribution = field(default_factory=Distribution)

    total_events: int = 0


def parse_telemetry(lines: list[str]) -> TelemetryReport:
    """Parse telemetry log lines and build an aggregated report."""
    report = TelemetryReport()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Extract JSON from log line — may be prefixed with logger metadata
        json_start = line.find("{")
        if json_start == -1:
            continue

        try:
            data = json.loads(line[json_start:])
        except json.JSONDecodeError:
            continue

        event = data.get("event")
        if not event:
            continue

        report.total_events += 1

        if event == "agent_run":
            report.tool_iterations.add(data.get("tool_loop_iterations", 0))
            report.input_tokens.add(data.get("input_tokens", 0))
            report.output_tokens.add(data.get("output_tokens", 0))
            report.context_tokens_peak.add(data.get("context_tokens_peak", 0))
            report.elapsed_seconds.add(data.get("elapsed_seconds", 0))
            report.tool_call_counts.add(len(data.get("tool_calls", [])))
            report.runs_by_phase[data.get("phase", "unknown")] += 1
            report.runs_by_model[data.get("model", "unknown")] += 1

        elif event == "review_loop":
            decision = data.get("consensus_decision", "unknown")
            report.review_decisions[decision] += 1
            report.review_iterations.add(data.get("iteration_number", 0))
            report.review_elapsed.add(data.get("elapsed_seconds", 0))

        elif event == "memory_compaction":
            report.compaction_count += 1
            before = data.get("before_tokens", 0)
            after = data.get("after_tokens", 0)
            report.compaction_before.add(before)
            report.compaction_after.add(after)
            if before > 0:
                report.compaction_reduction_pct.add(
                    round((1 - after / before) * 100, 1)
                )

        elif event == "context_summarization":
            report.summarization_count += 1
            before = data.get("before_tokens", 0)
            after = data.get("after_tokens", 0)
            report.summarization_before.add(before)
            report.summarization_after.add(after)
            if before > 0:
                report.summarization_reduction_pct.add(
                    round((1 - after / before) * 100, 1)
                )

    return report


def format_report(report: TelemetryReport) -> str:
    """Format the telemetry report as markdown."""
    lines: list[str] = []
    lines.append("# Telemetry Analysis Report")
    lines.append("")
    lines.append(f"**Total events parsed:** {report.total_events}")
    lines.append(f"**Agent runs:** {report.tool_iterations.count}")
    lines.append(f"**Review loops:** {report.review_iterations.count}")
    lines.append(f"**Compactions:** {report.compaction_count}")
    lines.append(f"**Context summarizations:** {report.summarization_count}")
    lines.append("")

    if report.tool_iterations.count == 0:
        lines.append("*No agent_run events found. Run some artifacts first.*")
        return "\n".join(lines)

    # --- Tool loop iterations ---
    lines.append("## 1. Tool Loop Iterations")
    lines.append(f"- **Current limit:** `AGENT_MAX_TOOL_ITERATIONS = 15`")
    lines.append(f"- **P50:** {report.tool_iterations.p50:.0f}")
    lines.append(f"- **P95:** {report.tool_iterations.p95:.0f}")
    lines.append(f"- **Max:** {report.tool_iterations.max:.0f}")
    p95 = report.tool_iterations.p95
    if p95 < 8:
        lines.append(f"- **Recommendation:** Lower to {int(p95) + 2} (P95 + 2 headroom)")
    elif p95 > 12:
        lines.append(f"- **Recommendation:** Raise to {int(p95) + 3} (P95 + 3 headroom)")
    else:
        lines.append("- **Recommendation:** Keep at 15 (well-calibrated)")
    lines.append("")

    # --- Context tokens peak ---
    lines.append("## 2. Context Token Peaks")
    lines.append(f"- **Current summarization threshold:** `AGENT_CONTEXT_SUMMARIZATION_THRESHOLD = 60000`")
    lines.append(f"- **P50:** {report.context_tokens_peak.p50:,.0f}")
    lines.append(f"- **P95:** {report.context_tokens_peak.p95:,.0f}")
    lines.append(f"- **Max:** {report.context_tokens_peak.max:,.0f}")
    if report.context_tokens_peak.max < 40_000:
        lines.append("- **Recommendation:** Threshold never approached — consider lowering to 40K")
    elif report.summarization_count > 0:
        lines.append(f"- **Summarization triggered {report.summarization_count}x** — threshold is effective")
    else:
        lines.append("- **Recommendation:** Keep at 60K (headroom exists)")
    lines.append("")

    # --- Memory budget ---
    lines.append("## 3. Memory Compaction")
    lines.append(f"- **Current budget:** `AGENT_MEMORY_BUDGET_TOTAL = 8000`")
    lines.append(f"- **Compactions triggered:** {report.compaction_count}")
    if report.compaction_count > 0:
        lines.append(f"- **Avg reduction:** {report.compaction_reduction_pct.mean:.0f}%")
        lines.append(f"- **Before tokens (P50):** {report.compaction_before.p50:,.0f}")
        lines.append(f"- **After tokens (P50):** {report.compaction_after.p50:,.0f}")
        if report.compaction_reduction_pct.mean < 20:
            lines.append("- **Recommendation:** Compaction barely reduces — consider raising budget")
    else:
        lines.append("- **Recommendation:** No compactions = budget is generous enough (or agents are new)")
    lines.append("")

    # --- Review loop ---
    lines.append("## 4. Review Decisions")
    lines.append(f"- **Current max_iterations:** template-specific (default 3)")
    total_reviews = sum(report.review_decisions.values())
    if total_reviews > 0:
        for decision, count in sorted(report.review_decisions.items()):
            pct = count / total_reviews * 100
            lines.append(f"- **{decision}:** {count} ({pct:.0f}%)")
        if report.review_decisions.get("APPROVE", 0) / max(total_reviews, 1) > 0.8:
            lines.append("- **Recommendation:** >80% first-pass approval — consider reducing max_iterations")
        if report.review_decisions.get("REVISE", 0) / max(total_reviews, 1) > 0.5:
            lines.append("- **Recommendation:** >50% revisions — grading criteria may be too strict or delegation too vague")
    else:
        lines.append("- *No review events recorded*")
    lines.append("")

    # --- Runs by phase ---
    lines.append("## 5. Runs by Phase")
    for phase, count in sorted(report.runs_by_phase.items()):
        lines.append(f"- **{phase}:** {count}")
    lines.append("")

    # --- Cost proxy ---
    lines.append("## 6. Token Usage (Cost Proxy)")
    lines.append(f"- **Input tokens (P50):** {report.input_tokens.p50:,.0f}")
    lines.append(f"- **Input tokens (P95):** {report.input_tokens.p95:,.0f}")
    lines.append(f"- **Output tokens (P50):** {report.output_tokens.p50:,.0f}")
    lines.append(f"- **Output tokens (P95):** {report.output_tokens.p95:,.0f}")
    lines.append(f"- **Elapsed seconds (P50):** {report.elapsed_seconds.p50:.1f}")
    lines.append(f"- **Elapsed seconds (P95):** {report.elapsed_seconds.p95:.1f}")
    lines.append("")

    # --- Context summarization ---
    if report.summarization_count > 0:
        lines.append("## 7. Context Summarization")
        lines.append(f"- **Times triggered:** {report.summarization_count}")
        lines.append(f"- **Avg reduction:** {report.summarization_reduction_pct.mean:.0f}%")
        lines.append(f"- **Before tokens (mean):** {report.summarization_before.mean:,.0f}")
        lines.append(f"- **After tokens (mean):** {report.summarization_after.mean:,.0f}")
        lines.append("")

    # --- Tuning parameter summary ---
    lines.append("## Parameter Summary")
    lines.append("")
    lines.append("| Parameter | Current | Observed P95 | Recommendation |")
    lines.append("|---|---|---|---|")
    lines.append(f"| `AGENT_MAX_TOOL_ITERATIONS` | 15 | {report.tool_iterations.p95:.0f} | {'Keep' if 6 <= p95 <= 12 else 'Tune'} |")
    lines.append(f"| `AGENT_CONTEXT_SUMMARIZATION_THRESHOLD` | 60000 | {report.context_tokens_peak.p95:,.0f} peak | {'Keep' if report.context_tokens_peak.p95 < 50_000 else 'Review'} |")
    lines.append(f"| `AGENT_MEMORY_BUDGET_TOTAL` | 8000 | {report.compaction_count} compactions | {'Keep' if report.compaction_count < 5 else 'Review'} |")
    approve_rate = report.review_decisions.get("APPROVE", 0) / max(total_reviews, 1) * 100 if total_reviews > 0 else 0
    lines.append(f"| `max_iterations` (review) | 3 | {approve_rate:.0f}% first-approve | {'Lower' if approve_rate > 80 else 'Keep'} |")
    lines.append(f"| `AGENT_SLOT_MAX_RETRIES` | 3 | — | Keep (no retry telemetry yet) |")
    lines.append(f"| `AGENT_CODE_EXEC_TIMEOUT` | 30 | — | Keep (no timeout telemetry yet) |")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Entry point: read from file arg or stdin, parse, print report."""
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        lines = path.read_text().splitlines()
    else:
        lines = sys.stdin.read().splitlines()

    if not lines:
        print("No input lines. Provide a telemetry log file or pipe lines to stdin.")
        sys.exit(1)

    report = parse_telemetry(lines)
    print(format_report(report))


if __name__ == "__main__":
    main()
