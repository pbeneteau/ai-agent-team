"""Unit tests for Ticket 3.3 — prompt assembly.

Verify section:
  1. build_user_message() has sections in correct recency bias order.
  2. Auto-assume text is present in every system prompt.
  3. build_iteration_prompt() includes previous version and comment.
  4. get_output_format_rules() returns correct rules per type/role.
  5. Empty/None sections are omitted cleanly.
"""

import pytest

from app.agents.prompt_builder import (
    AUTO_ASSUME_RULE,
    build_iteration_prompt,
    build_system_prompt,
    build_user_message,
    get_output_format_rules,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockAgent:
    """Minimal stand-in for the Agent model."""

    def __init__(
        self,
        name: str = "Aria",
        specialization: str = "content strategist",
        system_prompt: str | None = "Focus on clarity and audience.",
    ) -> None:
        self.name = name
        self.specialization = specialization
        self.system_prompt = system_prompt


class _MockComment:
    """Minimal stand-in for the ContextualComment model."""

    def __init__(
        self,
        file_path: str | None = "report.md",
        highlighted_text: str | None = "The market is growing.",
        instruction: str = "Add specific growth percentages.",
    ) -> None:
        self.file_path = file_path
        self.highlighted_text = highlighted_text
        self.instruction = instruction


_SAMPLE_BRIEF: dict[str, str | None] = {
    "title": "Q4 Market Report",
    "goal": "Analyze competitor landscape",
    "target_audience": "C-suite executives",
    "context": "Annual planning cycle",
    "description": "A comprehensive 10-page report with charts.",
}


# ---------------------------------------------------------------------------
# Verify 1: build_user_message — recency bias order
# ---------------------------------------------------------------------------


class TestBuildUserMessage:
    def test_sections_in_correct_order(self) -> None:
        """Skills → upstream → project brief → artifact brief → task."""
        msg = build_user_message(
            agent_memory="I specialize in market analysis.",
            upstream_context="## Output from Researcher: research_slot\nKey findings here.",
            project_brief="Build a competitor analysis for FY2026.",
            artifact_brief=_SAMPLE_BRIEF,
            wave_task="Write the executive summary section.",
        )

        # Find positions of each section
        idx_memory = msg.index("Your Knowledge & Experience")
        idx_upstream = msg.index("Output from Researcher")
        idx_project = msg.index("Project Context")
        idx_brief = msg.index("Your Assignment")
        idx_task = msg.index("Your Task in This Wave")

        # Verify strict ascending order (recency bias)
        assert idx_memory < idx_upstream < idx_project < idx_brief < idx_task

    def test_all_artifact_brief_fields_present(self) -> None:
        msg = build_user_message(
            agent_memory=None,
            upstream_context=None,
            project_brief=None,
            artifact_brief=_SAMPLE_BRIEF,
            wave_task=None,
        )
        assert "Title: Q4 Market Report" in msg
        assert "Goal: Analyze competitor landscape" in msg
        assert "Target Audience: C-suite executives" in msg
        assert "Context: Annual planning cycle" in msg
        assert "Description: A comprehensive 10-page report" in msg

    def test_omits_none_sections(self) -> None:
        """None sections should not produce empty headers."""
        msg = build_user_message(
            agent_memory=None,
            upstream_context=None,
            project_brief=None,
            artifact_brief=None,
            wave_task="Do the thing.",
        )
        assert "Your Knowledge" not in msg
        assert "Project Context" not in msg
        assert "Your Assignment" not in msg
        assert "Your Task in This Wave" in msg

    def test_omits_empty_string_sections(self) -> None:
        msg = build_user_message(
            agent_memory="",
            upstream_context="",
            project_brief="",
            artifact_brief={"title": None, "goal": None},
            wave_task="Do something.",
        )
        assert "Your Knowledge" not in msg
        assert "Project Context" not in msg
        assert "Your Assignment" not in msg

    def test_only_wave_task_produces_minimal_output(self) -> None:
        msg = build_user_message(
            agent_memory=None,
            upstream_context=None,
            project_brief=None,
            artifact_brief=None,
            wave_task="Summarize the findings.",
        )
        assert msg == "## Your Task in This Wave\n\nSummarize the findings."

    def test_partial_artifact_brief(self) -> None:
        """Brief with some None fields omits those fields cleanly."""
        msg = build_user_message(
            agent_memory=None,
            upstream_context=None,
            project_brief=None,
            artifact_brief={"title": "My Report", "goal": None, "target_audience": "Engineers"},
            wave_task=None,
        )
        assert "Title: My Report" in msg
        assert "Target Audience: Engineers" in msg
        assert "Goal" not in msg


# ---------------------------------------------------------------------------
# Verify 2: auto-assume text in every system prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    def test_auto_assume_present(self) -> None:
        agent = _MockAgent()
        prompt = build_system_prompt(agent, "OUTPUT RULES: test")
        assert "CRITICAL OPERATING RULE — AUTO-ASSUME" in prompt
        assert "You are fully autonomous" in prompt
        assert "[ASSUMPTION:" in prompt

    def test_auto_assume_present_with_minimal_agent(self) -> None:
        agent = _MockAgent(system_prompt=None)
        prompt = build_system_prompt(agent, "OUTPUT RULES: test")
        assert "AUTO-ASSUME" in prompt

    def test_position_1_role_identity(self) -> None:
        agent = _MockAgent(name="Viktor", specialization="code reviewer")
        prompt = build_system_prompt(agent, "OUTPUT RULES: test")
        assert "You are Viktor, a code reviewer." in prompt

    def test_position_1_includes_system_prompt(self) -> None:
        agent = _MockAgent(system_prompt="Always prefer TypeScript.")
        prompt = build_system_prompt(agent, "OUTPUT RULES: test")
        assert "Always prefer TypeScript." in prompt

    def test_position_3_output_format(self) -> None:
        agent = _MockAgent()
        rules = get_output_format_rules("code", "implementation")
        prompt = build_system_prompt(agent, rules)
        assert "OUTPUT RULES:" in prompt
        assert "--- FILE:" in prompt

    def test_correct_order_role_then_assume_then_format(self) -> None:
        agent = _MockAgent()
        prompt = build_system_prompt(agent, "OUTPUT RULES: custom")
        idx_role = prompt.index("You are Aria")
        idx_assume = prompt.index("AUTO-ASSUME")
        idx_format = prompt.index("OUTPUT RULES: custom")
        assert idx_role < idx_assume < idx_format


# ---------------------------------------------------------------------------
# Verify 3: build_iteration_prompt includes previous version + comment
# ---------------------------------------------------------------------------


class TestBuildIterationPrompt:
    def test_includes_previous_version(self) -> None:
        msg = build_iteration_prompt(
            previous_version_content="# Old Report\nStale data here.",
            comment=_MockComment(),
            artifact_brief=None,
        )
        assert "## Previous Version" in msg
        assert "# Old Report" in msg
        assert "Stale data here." in msg

    def test_includes_comment_fields(self) -> None:
        msg = build_iteration_prompt(
            previous_version_content="content",
            comment=_MockComment(
                file_path="chapter2.md",
                highlighted_text="Revenue grew",
                instruction="Add 2024 numbers",
            ),
            artifact_brief=None,
        )
        assert "## User Feedback" in msg
        assert "File: chapter2.md" in msg
        assert 'Highlighted text: "Revenue grew"' in msg
        assert "Instruction: Add 2024 numbers" in msg

    def test_includes_iteration_task_instruction(self) -> None:
        msg = build_iteration_prompt(
            previous_version_content="content",
            comment=_MockComment(),
            artifact_brief=None,
        )
        assert "## Your Task" in msg
        assert "Address the user's feedback" in msg
        assert "Modify ONLY the section" in msg
        assert "remove the assumption" in msg

    def test_comment_without_file_path_uses_entire_document(self) -> None:
        msg = build_iteration_prompt(
            previous_version_content="content",
            comment=_MockComment(file_path=None),
            artifact_brief=None,
        )
        assert "File: entire document" in msg

    def test_comment_without_highlight(self) -> None:
        msg = build_iteration_prompt(
            previous_version_content="content",
            comment=_MockComment(highlighted_text=None),
            artifact_brief=None,
        )
        assert "Highlighted text" not in msg

    def test_includes_artifact_brief(self) -> None:
        msg = build_iteration_prompt(
            previous_version_content="content",
            comment=_MockComment(),
            artifact_brief=_SAMPLE_BRIEF,
        )
        assert "## Your Assignment" in msg
        assert "Title: Q4 Market Report" in msg

    def test_includes_optional_agent_memory(self) -> None:
        msg = build_iteration_prompt(
            previous_version_content="content",
            comment=_MockComment(),
            artifact_brief=None,
            agent_memory="I know market analysis.",
        )
        assert "Your Knowledge & Experience" in msg
        assert "I know market analysis." in msg

    def test_includes_optional_project_brief(self) -> None:
        msg = build_iteration_prompt(
            previous_version_content="content",
            comment=_MockComment(),
            artifact_brief=None,
            project_brief="Build FY2026 report.",
        )
        assert "## Project Context" in msg
        assert "Build FY2026 report." in msg

    def test_version_number_label(self) -> None:
        msg = build_iteration_prompt(
            previous_version_content="content",
            comment=_MockComment(),
            artifact_brief=None,
            version_number=3,
        )
        assert "## Previous Version (v3)" in msg

    def test_recency_order_iteration(self) -> None:
        """Previous version → feedback → brief → iteration task (last)."""
        msg = build_iteration_prompt(
            previous_version_content="old content here",
            comment=_MockComment(),
            artifact_brief=_SAMPLE_BRIEF,
            agent_memory="skills here",
            project_brief="project context",
        )
        idx_memory = msg.index("Your Knowledge & Experience")
        idx_prev = msg.index("Previous Version")
        idx_feedback = msg.index("User Feedback")
        idx_project = msg.index("Project Context")
        idx_brief = msg.index("Your Assignment")
        idx_task = msg.index("## Your Task")
        assert idx_memory < idx_prev < idx_feedback < idx_project < idx_brief < idx_task


# ---------------------------------------------------------------------------
# Verify 4: get_output_format_rules returns correct rules
# ---------------------------------------------------------------------------


class TestGetOutputFormatRules:
    def test_code_implementation(self) -> None:
        rules = get_output_format_rules("code", "implementation")
        assert "--- FILE:" in rules
        assert "--- END FILE ---" in rules

    def test_code_developer(self) -> None:
        rules = get_output_format_rules("code", "developer")
        assert "--- FILE:" in rules

    def test_code_fixer(self) -> None:
        rules = get_output_format_rules("code", "fixer")
        assert "--- FILE:" in rules

    def test_prose_writer(self) -> None:
        rules = get_output_format_rules("prose", "writer")
        assert "No preamble" in rules
        assert "Use Markdown formatting" in rules

    def test_prose_editor(self) -> None:
        rules = get_output_format_rules("prose", "editor")
        assert "No preamble" in rules

    def test_prose_compiler(self) -> None:
        rules = get_output_format_rules("prose", "compiler")
        assert "No preamble" in rules

    def test_analysis_analyst(self) -> None:
        rules = get_output_format_rules("prose", "analyst")
        assert "structured Markdown" in rules
        assert "downstream agents" in rules

    def test_analysis_researcher(self) -> None:
        rules = get_output_format_rules("code", "researcher")
        assert "structured Markdown" in rules

    def test_qa_review(self) -> None:
        rules = get_output_format_rules("prose", "qa_review")
        assert "Review Report" in rules
        assert "PASS/FAIL" in rules

    def test_qa_validator(self) -> None:
        rules = get_output_format_rules("code", "validator")
        assert "Review Report" in rules

    def test_fallback_to_artifact_type_prose(self) -> None:
        """Unknown role falls back to artifact_type."""
        rules = get_output_format_rules("prose", "unknown_role")
        assert "No preamble" in rules

    def test_fallback_to_artifact_type_code(self) -> None:
        rules = get_output_format_rules("code", "unknown_role")
        assert "--- FILE:" in rules

    def test_default_to_analysis(self) -> None:
        """Unknown role + unknown type → analysis format."""
        rules = get_output_format_rules("unknown_type", "unknown_role")
        assert "structured Markdown" in rules


# ---------------------------------------------------------------------------
# Verify 5: empty sections omitted cleanly
# ---------------------------------------------------------------------------


class TestEmptySectionHandling:
    def test_all_none_produces_empty_string(self) -> None:
        msg = build_user_message(
            agent_memory=None,
            upstream_context=None,
            project_brief=None,
            artifact_brief=None,
            wave_task=None,
        )
        assert msg == ""

    def test_no_double_newlines_at_edges(self) -> None:
        msg = build_user_message(
            agent_memory=None,
            upstream_context=None,
            project_brief=None,
            artifact_brief=None,
            wave_task="Do the task.",
        )
        assert not msg.startswith("\n")
        assert not msg.endswith("\n\n\n")

    def test_system_prompt_no_none_text(self) -> None:
        """Agent with no system_prompt should not produce 'None' in output."""
        agent = _MockAgent(system_prompt=None)
        prompt = build_system_prompt(agent, "OUTPUT RULES: test")
        assert "None" not in prompt
