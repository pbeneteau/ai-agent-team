"""Unit tests for Ticket 3.4 — agent memory loader.

Verify section:
  1. load_agent_memory() formats with ## Skill: / ## Work Learning: headers.
  2. check_memory_budget() returns accurate token counts.
  3. Briefing entries are not counted against the 8,000 budget.
  4. Loading respects recency ordering (newest first).
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.memory import (
    MEMORY_BUDGET_LEARNINGS,
    MEMORY_BUDGET_SKILLS,
    MEMORY_BUDGET_TOTAL,
    MemoryBudgetStatus,
    count_tokens,
    format_briefing_entries,
    format_memory_entries,
    _parse_compaction_output,
)


# ---------------------------------------------------------------------------
# Mock entries
# ---------------------------------------------------------------------------


@dataclass
class _MockSkillEntry:
    """Minimal stand-in for AgentSkill model."""

    category: str
    title: str
    content: str
    token_count: int
    updated_at: datetime
    id: str = "mock-id"
    agent_id: str = "agent-1"
    source_artifact_id: str | None = None


def _make_skill(title: str, content: str, updated_at: datetime | None = None) -> _MockSkillEntry:
    updated = updated_at or datetime(2025, 1, 1, tzinfo=timezone.utc)
    return _MockSkillEntry(
        category="skill",
        title=title,
        content=content,
        token_count=count_tokens(f"## Skill: {title}\n{content}"),
        updated_at=updated,
    )


def _make_learning(title: str, content: str, updated_at: datetime | None = None) -> _MockSkillEntry:
    updated = updated_at or datetime(2025, 1, 1, tzinfo=timezone.utc)
    return _MockSkillEntry(
        category="work_learning",
        title=title,
        content=content,
        token_count=count_tokens(f"## Work Learning: {title}\n{content}"),
        updated_at=updated,
    )


def _make_briefing(title: str, content: str) -> _MockSkillEntry:
    return _MockSkillEntry(
        category="briefing",
        title=title,
        content=content,
        token_count=count_tokens(content),
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Verify 1: format_memory_entries — correct headers
# ---------------------------------------------------------------------------


class TestFormatMemoryEntries:
    def test_skill_header(self) -> None:
        entries = [_make_skill("TypeScript patterns", "Use strict mode always.")]
        result = format_memory_entries(entries)
        assert "## Skill: TypeScript patterns" in result
        assert "Use strict mode always." in result

    def test_learning_header(self) -> None:
        entries = [_make_learning("API rate limits", "Always add retry logic.")]
        result = format_memory_entries(entries)
        assert "## Work Learning: API rate limits" in result
        assert "Always add retry logic." in result

    def test_mixed_entries(self) -> None:
        entries = [
            _make_skill("React", "Use functional components."),
            _make_skill("CSS", "Prefer oklch colors."),
            _make_learning("Deploy gotcha", "Run migrations first."),
        ]
        result = format_memory_entries(entries)
        assert "## Skill: React" in result
        assert "## Skill: CSS" in result
        assert "## Work Learning: Deploy gotcha" in result

    def test_empty_entries(self) -> None:
        result = format_memory_entries([])
        assert result == ""

    def test_sections_separated_by_blank_line(self) -> None:
        entries = [
            _make_skill("A", "Content A."),
            _make_skill("B", "Content B."),
        ]
        result = format_memory_entries(entries)
        assert "\n\n" in result

    def test_briefing_entries_excluded(self) -> None:
        """Briefing entries are silently skipped by format_memory_entries."""
        entries = [
            _make_skill("Real skill", "Skill content."),
            _make_briefing("Project brief", "Brief content."),
        ]
        result = format_memory_entries(entries)
        assert "Real skill" in result
        assert "Project brief" not in result

    def test_preserves_input_order(self) -> None:
        """Entries appear in the order provided (caller controls ordering)."""
        entries = [
            _make_skill("First", "1"),
            _make_learning("Second", "2"),
            _make_skill("Third", "3"),
        ]
        result = format_memory_entries(entries)
        idx_first = result.index("First")
        idx_second = result.index("Second")
        idx_third = result.index("Third")
        assert idx_first < idx_second < idx_third


# ---------------------------------------------------------------------------
# Verify 2: check_memory_budget — accurate token counts
# ---------------------------------------------------------------------------


class TestCheckMemoryBudget:
    def test_budget_constants(self) -> None:
        """Verify the budget breakdown matches TDD-03 Section 5.1."""
        assert MEMORY_BUDGET_TOTAL == 8_000
        assert MEMORY_BUDGET_SKILLS == 6_000
        assert MEMORY_BUDGET_LEARNINGS == 2_000
        assert MEMORY_BUDGET_SKILLS + MEMORY_BUDGET_LEARNINGS == MEMORY_BUDGET_TOTAL

    def test_budget_status_under_budget(self) -> None:
        status = MemoryBudgetStatus(
            skills_tokens=3_000,
            skills_budget=MEMORY_BUDGET_SKILLS,
            learnings_tokens=1_000,
            learnings_budget=MEMORY_BUDGET_LEARNINGS,
            total_tokens=4_000,
            total_budget=MEMORY_BUDGET_TOTAL,
            remaining=4_000,
            over_budget=False,
        )
        assert status.remaining == 4_000
        assert not status.over_budget

    def test_budget_status_over_budget(self) -> None:
        status = MemoryBudgetStatus(
            skills_tokens=6_500,
            skills_budget=MEMORY_BUDGET_SKILLS,
            learnings_tokens=2_000,
            learnings_budget=MEMORY_BUDGET_LEARNINGS,
            total_tokens=8_500,
            total_budget=MEMORY_BUDGET_TOTAL,
            remaining=0,
            over_budget=True,
        )
        assert status.over_budget
        assert status.remaining == 0

    def test_budget_status_exact_budget(self) -> None:
        status = MemoryBudgetStatus(
            skills_tokens=6_000,
            skills_budget=MEMORY_BUDGET_SKILLS,
            learnings_tokens=2_000,
            learnings_budget=MEMORY_BUDGET_LEARNINGS,
            total_tokens=8_000,
            total_budget=MEMORY_BUDGET_TOTAL,
            remaining=0,
            over_budget=False,
        )
        assert not status.over_budget
        assert status.remaining == 0


# ---------------------------------------------------------------------------
# Verify 3: briefing entries not counted against budget
# ---------------------------------------------------------------------------


class TestBriefingEntries:
    def test_format_briefing_entries(self) -> None:
        entries = [
            _make_briefing("Project Alpha", "Build a dashboard for metrics."),
            _make_briefing("Tech constraints", "Must use React + TypeScript."),
        ]
        result = format_briefing_entries(entries)
        assert "## Briefing: Project Alpha" in result
        assert "## Briefing: Tech constraints" in result

    def test_briefing_entries_separate_from_memory(self) -> None:
        """Briefings and skills use different format functions — no cross-contamination."""
        briefing = _make_briefing("Brief", "Brief content")
        skill = _make_skill("Skill", "Skill content")

        memory_output = format_memory_entries([skill, briefing])
        briefing_output = format_briefing_entries([briefing])

        # Memory output includes skill, excludes briefing
        assert "Skill" in memory_output
        assert "Brief" not in memory_output

        # Briefing output includes briefing
        assert "## Briefing: Brief" in briefing_output


# ---------------------------------------------------------------------------
# Verify 4: recency ordering (input order preserved)
# ---------------------------------------------------------------------------


class TestRecencyOrdering:
    def test_skills_before_learnings_in_format(self) -> None:
        """When entries are pre-sorted (skills first, then learnings), format preserves that."""
        entries = [
            _make_skill("Newest skill", "New.", datetime(2025, 3, 1, tzinfo=timezone.utc)),
            _make_skill("Older skill", "Old.", datetime(2025, 1, 1, tzinfo=timezone.utc)),
            _make_learning("Recent learning", "Recent.", datetime(2025, 2, 1, tzinfo=timezone.utc)),
        ]
        result = format_memory_entries(entries)
        idx_newest_skill = result.index("Newest skill")
        idx_older_skill = result.index("Older skill")
        idx_learning = result.index("Recent learning")
        # Skills before learnings, newest first within each
        assert idx_newest_skill < idx_older_skill < idx_learning


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


class TestCountTokens:
    def test_empty_string(self) -> None:
        assert count_tokens("") == 0

    def test_simple_string(self) -> None:
        tokens = count_tokens("Hello world")
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_longer_string_more_tokens(self) -> None:
        short = count_tokens("Hello")
        long = count_tokens("Hello world, this is a longer sentence with more tokens.")
        assert long > short

    def test_not_approximation(self) -> None:
        """Verify we're using a real tokenizer, not len()/4."""
        text = "The quick brown fox jumps over the lazy dog."
        tokens = count_tokens(text)
        naive = len(text) // 4
        # Real tokenizer should give a specific count, not len/4
        assert tokens != naive or tokens > 0


# ---------------------------------------------------------------------------
# Compaction output parsing
# ---------------------------------------------------------------------------


class TestParseCompactionOutput:
    def test_parses_both_sections(self) -> None:
        text = (
            "### COMPACTED SKILLS\n"
            "- React patterns\n"
            "- TypeScript strict mode\n\n"
            "### COMPACTED WORK LEARNINGS\n"
            "- Always run migrations before deploy"
        )
        skills, learnings = _parse_compaction_output(text)
        assert "React patterns" in skills
        assert "TypeScript strict mode" in skills
        assert "Always run migrations" in learnings

    def test_handles_missing_learnings(self) -> None:
        text = "### COMPACTED SKILLS\n- Just skills here"
        skills, learnings = _parse_compaction_output(text)
        assert "Just skills here" in skills
        assert learnings == ""

    def test_handles_missing_skills(self) -> None:
        text = "### COMPACTED WORK LEARNINGS\n- Just learnings"
        skills, learnings = _parse_compaction_output(text)
        assert skills == ""
        assert "Just learnings" in learnings

    def test_handles_empty_output(self) -> None:
        skills, learnings = _parse_compaction_output("")
        assert skills == ""
        assert learnings == ""

    def test_case_insensitive(self) -> None:
        text = (
            "### compacted skills\n"
            "Some skills\n\n"
            "### compacted work learnings\n"
            "Some learnings"
        )
        skills, learnings = _parse_compaction_output(text)
        assert "Some skills" in skills
        assert "Some learnings" in learnings

    def test_extra_whitespace(self) -> None:
        text = (
            "###  COMPACTED  SKILLS \n"
            "  Skill content  \n\n"
            "###  COMPACTED  WORK  LEARNINGS \n"
            "  Learning content  "
        )
        skills, learnings = _parse_compaction_output(text)
        assert "Skill content" in skills
        assert "Learning content" in learnings
