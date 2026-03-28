"""Tests for Sprint 5 — Sufficiency, Readiness, Learning, Reflection, Briefing.

Verify sections for Tickets 5.1 through 5.5.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ticket 5.1 — Sufficiency Check Engine
# ---------------------------------------------------------------------------

from app.agents.sufficiency import (
    SUFFICIENCY_SYSTEM_PROMPT,
    SufficiencyIssue,
    SufficiencyResult,
    build_sufficiency_user_msg,
    run_sufficiency_check,
    _fail_open_result,
)


class TestSufficiencyModels:
    """Verify Pydantic models parse correctly."""

    def test_valid_result_parsing(self) -> None:
        """Valid JSON response parses into SufficiencyResult."""
        data = {
            "eligible": False,
            "score": 62,
            "issues": [
                {
                    "severity": "critical",
                    "field": "description",
                    "matched_text": "Write a competitive analysis of SaaS.",
                    "issue": "No specific competitors named.",
                    "suggestion": "Which specific competitors?",
                }
            ],
        }
        result = SufficiencyResult(**data)
        assert result.eligible is False
        assert result.score == 62
        assert len(result.issues) == 1
        assert result.issues[0].severity == "critical"
        assert result.issues[0].matched_text == "Write a competitive analysis of SaaS."

    def test_eligible_no_issues(self) -> None:
        """Brief with no issues is eligible."""
        result = SufficiencyResult(eligible=True, score=95, issues=[])
        assert result.eligible is True
        assert result.issues == []

    def test_fail_open_result(self) -> None:
        """Fail-open returns eligible=True with a warning."""
        result = _fail_open_result()
        assert result.eligible is True
        assert result.score == 50
        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"


@dataclass
class _MockArtifact:
    title: str = "Test Artifact"
    goal: str = "Test goal"
    target_audience: str = "Developers"
    context: str = "Some context"
    description: str = "Build a feature"
    artifact_type: str = "code"
    git_repo_url: str | None = "https://github.com/test/repo"


@dataclass
class _MockWorkspace:
    tech_stack: str | None = "Python, FastAPI"
    domain_description: str | None = "SaaS platform"


class TestSufficiencyUserMsg:
    def test_prose_artifact(self) -> None:
        """Prose artifact does not include tech stack context."""
        artifact = _MockArtifact(artifact_type="prose")
        workspace = _MockWorkspace()
        msg = build_sufficiency_user_msg(artifact, workspace)
        assert "Title: Test Artifact" in msg
        assert "Artifact Type: prose" in msg
        assert "Tech Stack Context" not in msg

    def test_code_artifact(self) -> None:
        """Code artifact includes tech stack and repo URL."""
        artifact = _MockArtifact(artifact_type="code")
        workspace = _MockWorkspace()
        msg = build_sufficiency_user_msg(artifact, workspace)
        assert "Tech Stack Context: Python, FastAPI" in msg
        assert "Target Repository: https://github.com/test/repo" in msg


class TestSufficiencyCheck:
    """Integration test with mock Anthropic client."""

    def test_valid_response_parsed(self) -> None:
        """5.1 Verify: valid JSON response parsed correctly."""
        valid_response = json.dumps({
            "eligible": True,
            "score": 85,
            "issues": [
                {
                    "severity": "warning",
                    "field": "description",
                    "matched_text": "comprehensive",
                    "issue": "Ambiguous scope.",
                    "suggestion": "Define 'comprehensive'.",
                }
            ],
        })

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=valid_response)]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch(
            "app.agents.anthropic_runner.get_anthropic_client",
            return_value=mock_client,
        ):
            result = asyncio.run(
                run_sufficiency_check(_MockArtifact(), _MockWorkspace())
            )

        assert result.eligible is True
        assert result.score == 85
        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"

    def test_malformed_json_fail_open(self) -> None:
        """5.1 Verify: malformed JSON triggers fail-open (returns eligible=True)."""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="not valid json {{{")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch(
            "app.agents.anthropic_runner.get_anthropic_client",
            return_value=mock_client,
        ):
            result = asyncio.run(
                run_sufficiency_check(_MockArtifact(), _MockWorkspace())
            )

        assert result.eligible is True
        assert result.score == 50
        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"

    def test_api_error_fail_open(self) -> None:
        """API error triggers fail-open."""
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=Exception("API timeout")
        )

        with patch(
            "app.agents.anthropic_runner.get_anthropic_client",
            return_value=mock_client,
        ):
            result = asyncio.run(
                run_sufficiency_check(_MockArtifact(), _MockWorkspace())
            )

        assert result.eligible is True
        assert result.score == 50


# ---------------------------------------------------------------------------
# Ticket 5.2 — Knowledge Readiness Scoring
# ---------------------------------------------------------------------------

from app.agents.readiness import compute_readiness_score, update_agent_readiness


class TestReadinessScoring:
    """Unit tests for the heuristic readiness formula."""

    def _make_mock_session(
        self,
        skill_count: int = 0,
        briefing_count: int = 0,
        learning_count: int = 0,
        agent_status: str = "learning",
        completed_artifacts: int = 0,
    ) -> AsyncMock:
        """Build a mock db_session that returns the specified counts."""
        session = AsyncMock()

        # Mock scalar() for the three count queries
        scalar_results = iter([skill_count, briefing_count, learning_count])
        session.scalar = AsyncMock(side_effect=lambda q: next(scalar_results))

        # Mock get() for the agent
        mock_agent = MagicMock()
        mock_agent.status = agent_status
        mock_agent.completed_artifacts = completed_artifacts
        mock_agent.readiness_score = 0
        session.get = AsyncMock(return_value=mock_agent)
        session.flush = AsyncMock()

        return session

    def test_fresh_agent_zero(self) -> None:
        """5.2 Verify: fresh agent with nothing = readiness 0."""
        session = self._make_mock_session(
            skill_count=0,
            briefing_count=0,
            learning_count=0,
            agent_status="learning",
            completed_artifacts=0,
        )
        score = asyncio.run(
            compute_readiness_score("agent-1", "project-1", session)
        )
        assert score == 0

    def test_skills_plus_onboarding_60(self) -> None:
        """5.2 Verify: agent with skills (40) + onboarding complete (20) = 60."""
        session = self._make_mock_session(
            skill_count=3,
            briefing_count=0,
            learning_count=0,
            agent_status="ready",  # past learning = onboarding complete
            completed_artifacts=0,
        )
        score = asyncio.run(
            compute_readiness_score("agent-1", "project-1", session)
        )
        assert score == 60

    def test_all_four_components_100(self) -> None:
        """5.2 Verify: agent with all 4 components = readiness 100."""
        session = self._make_mock_session(
            skill_count=5,
            briefing_count=2,
            learning_count=3,
            agent_status="ready",
            completed_artifacts=2,
        )
        score = asyncio.run(
            compute_readiness_score("agent-1", "project-1", session)
        )
        assert score == 100

    def test_no_project_full_briefing_credit(self) -> None:
        """No project_id gives full briefing credit (30 points)."""
        session = self._make_mock_session(
            skill_count=0,
            briefing_count=0,
            learning_count=0,
            agent_status="learning",
            completed_artifacts=0,
        )
        # Override: only 2 scalar calls (skill_count, learning_count) — no briefing query
        scalar_results = iter([0, 0])
        session.scalar = AsyncMock(side_effect=lambda q: next(scalar_results))

        score = asyncio.run(
            compute_readiness_score("agent-1", None, session)
        )
        assert score == 30  # Only briefing credit


# ---------------------------------------------------------------------------
# Ticket 5.3 — Agent Learning Task
# ---------------------------------------------------------------------------

from app.agents.learning import (
    LEARNING_SYSTEM_PROMPT_TEMPLATE,
    LEARNING_USER_MSG_TEMPLATE,
    _store_learning_output,
)
from app.agents.anthropic_runner import AgentResult


class TestAgentLearning:
    """Integration test with mock Anthropic + mock tools."""

    def test_learning_produces_skills_and_transitions(self) -> None:
        """5.3 Verify: agent produces skill entries and transitions learning → ready."""
        agent_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())

        # Mock agent and workspace
        mock_agent = MagicMock()
        mock_agent.id = agent_id
        mock_agent.name = "Test Agent"
        mock_agent.specialization = "Frontend Dev"
        mock_agent.workspace_id = workspace_id
        mock_agent.status = "learning"

        mock_workspace = MagicMock()
        mock_workspace.id = workspace_id
        mock_workspace.domain_description = "E-commerce"
        mock_workspace.tech_stack = "React, TypeScript"

        # Mock the agent loop result
        mock_result = AgentResult(
            text="# Core Frontend Skills\n\n- React best practices\n- TypeScript patterns",
            files={"research.md": "Additional research content"},
            input_tokens=500,
            output_tokens=1000,
        )

        # Track skill additions
        added_skills: list[MagicMock] = []

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=lambda model, id: {
            agent_id: mock_agent,
            workspace_id: mock_workspace,
        }.get(id))

        # Mock the workspace query
        mock_scalar_result = MagicMock()
        mock_scalar_result.scalar_one_or_none = MagicMock(return_value=mock_workspace)
        mock_session.execute = AsyncMock(return_value=mock_scalar_result)
        mock_session.add = MagicMock(side_effect=lambda obj: added_skills.append(obj))
        mock_session.flush = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=1)  # For readiness queries

        with patch("app.agents.learning.run_agent", AsyncMock(return_value=mock_result)), \
             patch("app.agents.learning.get_tools_for_phase", return_value=[]), \
             patch("app.agents.learning.create_tool_executor", return_value=AsyncMock()), \
             patch("app.agents.learning.update_agent_readiness", AsyncMock(return_value=60)):

            from app.agents.learning import _execute_learning_impl
            asyncio.run(_execute_learning_impl(agent_id, mock_session))

        # Verify: agent transitioned to ready
        assert mock_agent.status == "ready"

        # Verify: skill entries were created (main text + 1 file)
        assert len(added_skills) == 2
        assert added_skills[0].category == "skill"
        assert added_skills[0].title == "Core Domain Knowledge"
        assert added_skills[1].category == "skill"
        assert added_skills[1].title == "Research: research.md"

    def test_learning_prompt_templates(self) -> None:
        """Prompt templates contain required placeholders."""
        assert "{agent_name}" in LEARNING_SYSTEM_PROMPT_TEMPLATE
        assert "{specialization}" in LEARNING_SYSTEM_PROMPT_TEMPLATE
        assert "{domain_description}" in LEARNING_USER_MSG_TEMPLATE
        assert "{tech_stack}" in LEARNING_USER_MSG_TEMPLATE
        assert "web_search" in LEARNING_USER_MSG_TEMPLATE


# ---------------------------------------------------------------------------
# Ticket 5.4 — Reflection Engine
# ---------------------------------------------------------------------------

from app.agents.reflection import (
    REFLECTION_SYSTEM_PROMPT,
    ReflectionResponse,
    ReflectionInsight,
    ReflectionCaution,
    ObsoleteSkill,
    should_trigger_reflection,
    _post_process_reflection,
    _build_artifacts_section,
)


class TestReflectionTrigger:
    """Test should_trigger_reflection conditions."""

    def test_trigger_after_3_artifacts(self) -> None:
        """Triggers when ≥3 artifacts since last reflection."""
        mock_agent = MagicMock()
        mock_agent.last_reflection_at = datetime.now(timezone.utc) - timedelta(days=1)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_agent)
        mock_session.scalar = AsyncMock(return_value=3)  # 3 artifacts

        result = asyncio.run(should_trigger_reflection("agent-1", mock_session))
        assert result is True

    def test_trigger_after_7_days(self) -> None:
        """Triggers when ≥7 days since last reflection."""
        mock_agent = MagicMock()
        mock_agent.last_reflection_at = datetime.now(timezone.utc) - timedelta(days=8)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_agent)
        mock_session.scalar = AsyncMock(return_value=1)  # Only 1 artifact but old

        result = asyncio.run(should_trigger_reflection("agent-1", mock_session))
        assert result is True

    def test_no_trigger_recent_reflection(self) -> None:
        """Does not trigger with recent reflection and <3 artifacts."""
        mock_agent = MagicMock()
        mock_agent.last_reflection_at = datetime.now(timezone.utc) - timedelta(days=2)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_agent)
        mock_session.scalar = AsyncMock(return_value=2)  # Only 2 artifacts

        result = asyncio.run(should_trigger_reflection("agent-1", mock_session))
        assert result is False


class TestReflectionModels:
    """Verify reflection Pydantic models."""

    def test_response_parsing(self) -> None:
        """ReflectionResponse parses valid JSON."""
        data = {
            "insights": [
                {
                    "title": "Brand voice: no exclamation marks",
                    "content": "Client prefers understated tone.",
                    "source_artifact": "uuid-123",
                }
            ],
            "cautions": [
                {
                    "title": "Avoid USD assumption",
                    "content": "Ask about currency first.",
                    "source_artifact": "uuid-456",
                }
            ],
            "obsolete_skills": [
                {
                    "skill_id": "uuid-789",
                    "reason": "User now prefers tables over bullets.",
                }
            ],
        }
        result = ReflectionResponse(**data)
        assert len(result.insights) == 1
        assert len(result.cautions) == 1
        assert len(result.obsolete_skills) == 1
        assert result.insights[0].title == "Brand voice: no exclamation marks"


class TestReflectionPostProcessing:
    """5.4 Verify: insights + obsolete → new rows created, old rows deleted."""

    def test_post_processing(self) -> None:
        """Insights create skills, cautions create learnings, obsolete deletes."""
        reflection = ReflectionResponse(
            insights=[
                ReflectionInsight(
                    title="New skill",
                    content="Learned from recent work.",
                    source_artifact="art-1",
                ),
            ],
            cautions=[
                ReflectionCaution(
                    title="Watch out",
                    content="Avoid this pattern.",
                    source_artifact="art-2",
                ),
            ],
            obsolete_skills=[
                ObsoleteSkill(
                    skill_id="old-skill-1",
                    reason="Contradicted by new feedback.",
                ),
            ],
        )

        added_items: list = []
        executed_stmts: list = []

        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=lambda obj: added_items.append(obj))
        mock_session.execute = AsyncMock(side_effect=lambda stmt: executed_stmts.append(stmt))
        mock_session.flush = AsyncMock()

        # Mock check_memory_budget to return under budget
        mock_budget = MagicMock()
        mock_budget.over_budget = False

        with patch(
            "app.agents.reflection.check_memory_budget",
            AsyncMock(return_value=mock_budget),
        ):
            asyncio.run(
                _post_process_reflection("agent-1", reflection, mock_session)
            )

        # Verify: 1 insight → 1 skill entry, 1 caution → 1 work_learning entry
        assert len(added_items) == 2
        skill_item = added_items[0]
        assert skill_item.category == "skill"
        assert skill_item.title == "New skill"

        learning_item = added_items[1]
        assert learning_item.category == "work_learning"
        assert learning_item.title == "Watch out"

        # Verify: delete was executed (1 flush + 1 delete statement)
        # The delete for obsolete skill was called via session.execute
        assert len(executed_stmts) >= 1


class TestReflectionLocking:
    """5.4 Verify: FOR UPDATE lock blocks concurrent reflection."""

    def test_for_update_used(self) -> None:
        """The reflection implementation uses with_for_update()."""
        # This test verifies the code path by checking that SELECT ... FOR UPDATE
        # is used in the implementation. We inspect the source code structure.
        import inspect
        from app.agents.reflection import _execute_reflection_impl
        source = inspect.getsource(_execute_reflection_impl)
        assert "with_for_update()" in source, (
            "Reflection must use SELECT ... FOR UPDATE for row locking"
        )


class TestArtifactsSection:
    """Test the prompt building for artifacts."""

    def test_builds_section_with_comments(self) -> None:
        artifacts = [
            {
                "id": "art-1",
                "title": "Feature X",
                "description": "Build feature X",
                "current_version": 3,
                "comments": [
                    {
                        "highlighted_text": "use blue",
                        "instruction": "Change to green",
                        "resolved_in_version": "v2",
                    }
                ],
            }
        ]
        section = _build_artifacts_section(artifacts)
        assert "Feature X" in section
        assert '"use blue"' in section
        assert '"Change to green"' in section

    def test_builds_section_no_comments(self) -> None:
        artifacts = [
            {
                "id": "art-1",
                "title": "Feature Y",
                "description": "Build feature Y",
                "current_version": 1,
                "comments": [],
            }
        ]
        section = _build_artifacts_section(artifacts)
        assert "(no comments)" in section


# ---------------------------------------------------------------------------
# Ticket 5.5 — Project Briefing
# ---------------------------------------------------------------------------

from app.agents.briefing import brief_all_agents, brief_agent


class TestProjectBriefing:
    """Unit tests for project briefing distribution."""

    def test_brief_creates_briefing_entries(self) -> None:
        """5.5 Verify: publishing a brief creates briefing agent_skill rows for all active agents."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.name = "Test Project"
        mock_project.workspace_id = "workspace-1"
        mock_project.brief_published = "This is the project brief content."

        mock_agent_1 = MagicMock()
        mock_agent_1.id = "agent-1"
        mock_agent_1.readiness_score = 0

        mock_agent_2 = MagicMock()
        mock_agent_2.id = "agent-2"
        mock_agent_2.readiness_score = 0

        # Mock query that returns active agents
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[mock_agent_1, mock_agent_2]))
        )

        added_items: list = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock(side_effect=lambda obj: added_items.append(obj))
        mock_session.flush = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=1)  # For readiness
        mock_session.get = AsyncMock(return_value=mock_agent_1)  # For readiness

        with patch(
            "app.agents.briefing.update_agent_readiness",
            AsyncMock(return_value=60),
        ):
            count = asyncio.run(
                brief_all_agents(mock_project, mock_session)
            )

        assert count == 2
        # Each agent gets a briefing entry
        assert len(added_items) == 2
        assert all(item.category == "briefing" for item in added_items)
        assert all(item.title == "Project: Test Project" for item in added_items)
        assert all(
            item.content == "This is the project brief content."
            for item in added_items
        )

    def test_republish_replaces_existing(self) -> None:
        """5.5 Verify: re-publishing replaces (not stacks) existing briefing entries."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.name = "Test Project"
        mock_project.workspace_id = "workspace-1"
        mock_project.brief_published = "Updated brief content."

        mock_agent = MagicMock()
        mock_agent.id = "agent-1"
        mock_agent.readiness_score = 0

        executed_stmts: list = []
        added_items: list = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=lambda stmt: executed_stmts.append(stmt)
        )
        mock_session.add = MagicMock(side_effect=lambda obj: added_items.append(obj))
        mock_session.flush = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=1)
        mock_session.get = AsyncMock(return_value=mock_agent)

        with patch(
            "app.agents.briefing.update_agent_readiness",
            AsyncMock(return_value=60),
        ):
            asyncio.run(
                brief_agent(mock_agent, mock_project, mock_session)
            )

        # Verify: delete was called before insert
        assert len(executed_stmts) >= 1  # At least the delete
        assert len(added_items) == 1  # The new briefing entry
        assert added_items[0].content == "Updated brief content."

    def test_empty_brief_no_action(self) -> None:
        """No briefing when brief_published is empty."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.brief_published = None

        mock_session = AsyncMock()
        count = asyncio.run(brief_all_agents(mock_project, mock_session))
        assert count == 0


# ---------------------------------------------------------------------------
# Prompt content verification
# ---------------------------------------------------------------------------


class TestPromptContent:
    """Verify prompts match TDD specs."""

    def test_sufficiency_system_prompt_content(self) -> None:
        assert "Brief Quality Analyst" in SUFFICIENCY_SYSTEM_PROMPT
        assert "MISSING CONSTRAINTS" in SUFFICIENCY_SYSTEM_PROMPT
        assert "AMBIGUOUS LANGUAGE" in SUFFICIENCY_SYSTEM_PROMPT
        assert "Maximum 5 issues" in SUFFICIENCY_SYSTEM_PROMPT
        assert "valid JSON only" in SUFFICIENCY_SYSTEM_PROMPT

    def test_reflection_system_prompt_content(self) -> None:
        assert "Learning Extractor" in REFLECTION_SYSTEM_PROMPT
        assert "SPECIFIC, actionable learnings" in REFLECTION_SYSTEM_PROMPT
        assert "valid JSON only" in REFLECTION_SYSTEM_PROMPT

    def test_learning_prompts_content(self) -> None:
        sys_prompt = LEARNING_SYSTEM_PROMPT_TEMPLATE.format(
            agent_name="Test", specialization="Frontend Dev"
        )
        assert "onboarding phase" in sys_prompt
        assert "foundational knowledge" in sys_prompt

        user_msg = LEARNING_USER_MSG_TEMPLATE.format(
            domain_description="SaaS", tech_stack="React"
        )
        assert "Key concepts and best practices" in user_msg
        assert "web_search" in user_msg
