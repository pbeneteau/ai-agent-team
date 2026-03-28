"""Upstream context builder — assembles cross-functional context for downstream agents.

Ref: TDD-03 Section 8 (upstream context flow — core mechanism, token cap, truncation).
     TDD-03 Section 8.1 (context assembly — iterating depends_on, concatenating with headers).
     TDD-03 Section 8.2 (middle-out truncation — 47/53 split, line-aware cuts).
     TDD-03 Section 13 (end-to-end flow — where build_upstream_context is called).

Lifecycle: orchestrator completes wave → stores outputs in wave_outputs dict →
           next wave's agents call build_upstream_context → result injected at
           prompt position 6 via prompt_builder.build_user_message().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import tiktoken

from app.agents.memory import count_tokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (TDD-03 Section 8.2)
# ---------------------------------------------------------------------------

UPSTREAM_TOKEN_CAP: int = 15_000
HEAD_RATIO: float = 0.47
TAIL_RATIO: float = 0.53

# Same cl100k_base encoding used by memory.count_tokens — needed here for
# token-level encode/decode when line-based truncation can't find clean cuts.
_encoder: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")


# ---------------------------------------------------------------------------
# Data types (TDD-03 Section 8.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WaveOutput:
    """Output from a completed slot in the DAG.

    Stored in the orchestrator's ``wave_outputs`` dict, keyed by ``slot_id``.

    Attributes:
        text: The agent's text output.
        agent_name: Name of the agent that produced this output.
        slot_label: Human-readable label of the DAG slot.
        files: Paths written via the ``file_write`` tool (if any).
    """

    text: str
    agent_name: str
    slot_label: str
    files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Line-based token helpers
# ---------------------------------------------------------------------------


def _take_tokens_from_start(lines: list[str], budget: int) -> str:
    """Greedily take lines from the start until the token budget is reached.

    Always takes at least one line (even if it exceeds the budget on its own)
    to guarantee non-empty output.
    """
    result: list[str] = []
    used = 0
    for line in lines:
        t = count_tokens(line)
        if used + t > budget and result:
            break
        result.append(line)
        used += t
        if used >= budget:
            break
    return "\n".join(result)


def _take_tokens_from_end(lines: list[str], budget: int) -> str:
    """Greedily take lines from the end until the token budget is reached.

    Always takes at least one line (even if it exceeds the budget on its own)
    to guarantee non-empty output.
    """
    result: list[str] = []
    used = 0
    for line in reversed(lines):
        t = count_tokens(line)
        if used + t > budget and result:
            break
        result.append(line)
        used += t
        if used >= budget:
            break
    result.reverse()
    return "\n".join(result)


# ---------------------------------------------------------------------------
# Truncation (TDD-03 Section 8.2)
# ---------------------------------------------------------------------------


def truncate_middle(text: str, max_tokens: int = UPSTREAM_TOKEN_CAP) -> str:
    """Truncate text using middle-out strategy if it exceeds the token budget.

    Keeps the first 47% of tokens (introduction, structure, key definitions)
    and the last 53% of tokens (conclusions, specific details, most recent
    content), inserting a truncation marker in the middle.

    Cuts are made at line boundaries for readability. If line-based splitting
    produces overlapping head/tail (e.g. a single enormous line), falls back
    to token-level splitting.

    If the text is within budget, returns it unchanged.

    Args:
        text: The text to potentially truncate.
        max_tokens: Maximum token budget (default: 15,000 per AD-11).

    Returns:
        The original text if within budget, or truncated text with marker.
    """
    total_tokens = count_tokens(text)
    if total_tokens <= max_tokens:
        return text

    head_budget = int(max_tokens * HEAD_RATIO)
    tail_budget = int(max_tokens * TAIL_RATIO)

    # Try line-based truncation for cleaner cuts
    lines = text.split("\n")
    head = _take_tokens_from_start(lines, head_budget)
    tail = _take_tokens_from_end(lines, tail_budget)

    head_tokens = count_tokens(head)
    tail_tokens = count_tokens(tail)

    # If line-based approach yields overlapping head/tail (head + tail >= total),
    # fall back to token-level truncation for precise cuts.
    if head_tokens + tail_tokens >= total_tokens:
        all_tokens = _encoder.encode(text)
        head = _encoder.decode(all_tokens[:head_budget])
        tail = _encoder.decode(all_tokens[-tail_budget:])
        head_tokens = count_tokens(head)
        tail_tokens = count_tokens(tail)

    truncated_count = total_tokens - head_tokens - tail_tokens
    marker = f"\n\n[... {truncated_count} tokens truncated for brevity ...]\n\n"

    return f"{head}{marker}{tail}"


# ---------------------------------------------------------------------------
# Context assembly (TDD-03 Section 8.1)
# ---------------------------------------------------------------------------


def build_upstream_context(
    wave: Any,
    wave_outputs: dict[str, WaveOutput],
) -> str | None:
    """Assemble upstream agent outputs for a downstream wave's prompt.

    Iterates the wave's ``depends_on`` slot IDs, retrieves each upstream
    output from ``wave_outputs``, truncates per-dependency if over the
    15,000-token cap, and concatenates with headers and ``---`` separators.

    The result is injected at prompt position 6 by
    ``prompt_builder.build_user_message()``.

    Args:
        wave: A ``DagWave`` instance (or any object with
              ``depends_on: list[str]``).
        wave_outputs: Dict mapping ``slot_id`` → ``WaveOutput`` for all
                      completed slots from previous waves.

    Returns:
        Formatted upstream context string, or ``None`` if the wave has
        no dependencies or all dependencies produced empty/missing output.
    """
    depends_on: list[str] = getattr(wave, "depends_on", [])
    if not depends_on:
        return None

    sections: list[str] = []

    for dep_slot_id in depends_on:
        output = wave_outputs.get(dep_slot_id)
        if output is None:
            logger.warning(
                "Upstream slot '%s' not found in wave_outputs — skipping",
                dep_slot_id,
            )
            continue

        if not output.text or not output.text.strip():
            logger.warning(
                "Upstream slot '%s' produced empty output — skipping",
                dep_slot_id,
            )
            continue

        header = f"## Upstream Output — {output.agent_name}: {output.slot_label}"
        content = truncate_middle(output.text, max_tokens=UPSTREAM_TOKEN_CAP)
        sections.append(f"{header}\n\n{content}")

    if not sections:
        return None

    return "\n\n---\n\n".join(sections)
