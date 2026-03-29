"""Execution telemetry — structured metrics for agent runs, review loops, and compaction.

Ref: Sprint 16, Ticket 16.1 (AD-30).

Emits structured JSON log lines via a dedicated ``telemetry`` logger.  Each
event is a self-contained record that can be ingested by any JSON-aware log
pipeline (ELK, Datadog, CloudWatch, etc.).

Event types:
  - ``agent_run``         — one per ``run_agent()`` call
  - ``review_loop``       — one per review iteration in ``_execute_lead_dag``
  - ``memory_compaction`` — one per ``trigger_compaction()`` call
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field

logger = logging.getLogger("telemetry")


# ---------------------------------------------------------------------------
# Metric dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ExecutionMetrics:
    """Metrics emitted after each ``run_agent()`` call."""

    wave_id: str
    slot_key: str
    agent_id: str
    phase: str
    model: str
    tool_loop_iterations: int
    tool_calls: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_seconds: float = 0.0
    context_tokens_peak: int = 0
    review_decision: str | None = None
    compaction_triggered: bool = False


@dataclass(slots=True)
class ReviewLoopMetrics:
    """Metrics emitted after each review iteration in the execution+review loop."""

    wave_id: str
    iteration_number: int
    consensus_decision: str
    decisions_by_lead: dict[str, str] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


@dataclass(slots=True)
class CompactionMetrics:
    """Metrics emitted after a memory compaction cycle."""

    agent_id: str
    before_tokens: int
    after_tokens: int
    entries_before: int
    entries_after: int
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Emitters
# ---------------------------------------------------------------------------


def emit_execution_metrics(metrics: ExecutionMetrics) -> None:
    """Log a single agent run as a structured JSON event."""
    payload = {"event": "agent_run", **asdict(metrics)}
    logger.info(json.dumps(payload, default=str))


def emit_review_loop_metrics(metrics: ReviewLoopMetrics) -> None:
    """Log a review loop iteration as a structured JSON event."""
    payload = {"event": "review_loop", **asdict(metrics)}
    logger.info(json.dumps(payload, default=str))


def emit_compaction_metrics(metrics: CompactionMetrics) -> None:
    """Log a memory compaction cycle as a structured JSON event."""
    payload = {"event": "memory_compaction", **asdict(metrics)}
    logger.info(json.dumps(payload, default=str))


# ---------------------------------------------------------------------------
# Timer helper
# ---------------------------------------------------------------------------


class Timer:
    """Minimal context-manager timer for measuring elapsed seconds."""

    __slots__ = ("_start", "elapsed")

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *_: object) -> None:
        self.elapsed = round(time.monotonic() - self._start, 3)
