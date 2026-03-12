import asyncio
import json
import os

import pytest

from app.core.universal_plan import (
    PlanClarificationRequiredError,
    TaskPlanExecutor,
    TeamPlanExecutor,
    UniversalPlanSession,
    validate_task_draft,
    validate_team_draft,
)
from app.models.plan import PlanExecutionEligibility, PlanKind, PlanState

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-for-smoke")


@pytest.fixture()
def isolated_backend(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.core.agent_factory import get_agent_factory
    from app.core.document_store import get_document_store
    from app.core.knowledge import get_knowledge_audit_service
    from app.core.orchestrator import get_orchestrator
    from app.core import usage_tracker as usage_tracker_module
    from app.core.workspace import get_workspace_manager
    from app.memory.project_context import get_project_context_store
    from app.memory.skills_store import get_skills_store
    from app.memory.vector_store import get_vector_store

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-for-smoke")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("TEAMS_FILE", str(data_dir / "teams.json"))
    monkeypatch.setenv("WORKSPACES_DIR", str(data_dir / "workspaces"))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(data_dir / "chromadb"))

    get_settings.cache_clear()
    get_agent_factory.cache_clear()
    get_document_store.cache_clear()
    get_knowledge_audit_service.cache_clear()
    get_orchestrator.cache_clear()
    get_workspace_manager.cache_clear()
    get_project_context_store.cache_clear()
    get_skills_store.cache_clear()
    get_vector_store.cache_clear()
    usage_tracker_module._tracker = None

    yield data_dir

    get_settings.cache_clear()
    get_agent_factory.cache_clear()
    get_document_store.cache_clear()
    get_knowledge_audit_service.cache_clear()
    get_orchestrator.cache_clear()
    get_workspace_manager.cache_clear()
    get_project_context_store.cache_clear()
    get_skills_store.cache_clear()
    get_vector_store.cache_clear()
    usage_tracker_module._tracker = None


def test_universal_plan_session_creates_task_draft(isolated_backend):
    session = UniversalPlanSession(session_id="session-task")

    draft = session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Prepare investor memo",
            "description": "Draft a concise investor memo for pre-seed outreach.",
            "summary": "Investor memo draft",
            "team_id": "team-123",
            "team_name": "Fundraising Team",
            "priority": "high",
            "execution_mode": "standalone",
        },
        tagged_doc_ids=["doc-1", "doc-2"],
    )

    assert session.kind == PlanKind.TASK
    assert session.state == PlanState.AWAITING_CONFIRMATION
    assert draft.assigned_team_name == "Fundraising Team"
    assert draft.context_document_ids == ["doc-1", "doc-2"]
    assert draft.execution_eligibility == PlanExecutionEligibility.CLARIFICATION_REQUIRED
    assert any(issue.field_path == "assigned_team_name" for issue in draft.validation_issues)


def test_universal_plan_session_creates_team_draft():
    session = UniversalPlanSession(session_id="session-team")

    draft = session.set_team_draft(
        {
            "action": "plan_mode",
            "kind": "team",
            "summary": "Founding GTM pod",
            "project": {
                "name": "Glance",
                "description": "AI support for devices",
                "domain": "support",
                "short_term_goal": "Pre-seed fundraising deck",
            },
            "teams": [
                {
                    "name": "Go To Market",
                    "description": "Support fundraising and positioning",
                    "domain": "gtm",
                    "agents": [
                        {
                            "name": "Sophie",
                            "title": "Fundraising Lead",
                            "specialization": "fundraising",
                            "goal": "Run the pre-seed process",
                            "backstory": "10+ years in B2B SaaS fundraising",
                            "is_lead": True,
                            "model_tier": "sonnet",
                        }
                    ],
                }
            ],
        }
    )

    assert session.kind == PlanKind.TEAM
    assert session.state == PlanState.AWAITING_CONFIRMATION
    assert draft.project.name == "Glance"
    assert len(draft.teams) == 1
    assert draft.teams[0].agents[0].name == "Sophie"


def test_plan_confirm_rejected_after_cancel():
    session = UniversalPlanSession(session_id="cancelled-session")
    draft = session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Prepare memo",
            "description": "Short memo",
        }
    )

    session.cancel()

    with pytest.raises(ValueError, match="awaiting confirmation"):
        session.can_confirm(session_id="cancelled-session", draft_id=draft.id)


def test_plan_confirm_rejected_for_obsolete_draft():
    session = UniversalPlanSession(session_id="obsolete-session")
    session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Draft v1",
            "description": "First draft",
        }
    )
    second_draft = session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Draft v2",
            "description": "Second draft",
        }
    )

    with pytest.raises(ValueError, match="obsolete"):
        session.can_confirm(session_id="obsolete-session", draft_id="unknown-draft")

    assert second_draft.revision == 2


def test_plan_confirm_rejected_when_blockers_remain():
    session = UniversalPlanSession(session_id="blocked-session")
    draft = session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Prepare deck",
            "description": "Deck draft",
            "blocking_questions": ["Quel ton veux-tu ?"],
        }
    )

    with pytest.raises(ValueError, match="not eligible"):
        session.can_confirm(session_id="blocked-session", draft_id=draft.id)


def test_plan_confirm_is_idempotent_after_completion(isolated_backend):
    from app.core.agent_factory import get_agent_factory

    team, _agents = get_agent_factory().create_team_from_template("dev")
    session = UniversalPlanSession(session_id="completed-session")
    draft = session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Prepare deck",
            "description": "Deck draft",
            "team_id": team.id,
            "team_name": team.name,
        }
    )

    should_execute, payload = session.can_confirm(session_id="completed-session", draft_id=draft.id)
    assert should_execute is True
    assert payload is None

    session.mark_executing(draft.id)
    session.mark_completed(draft.id, {"id": "task-123", "status": "pending"})

    should_execute, payload = session.can_confirm(session_id="completed-session", draft_id=draft.id)
    assert should_execute is False
    assert payload == {"id": "task-123", "status": "pending"}


def test_validate_task_draft_returns_structured_clarification_when_assignment_missing(isolated_backend):
    from app.core.agent_factory import get_agent_factory

    factory = get_agent_factory()
    factory.create_team_from_template("dev")
    factory.create_team_from_template("product")

    session = UniversalPlanSession(session_id="task-validation")
    draft = session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Prepare memo",
            "description": "Need a valid owner",
        }
    )

    validated = validate_task_draft(draft)

    assert validated.execution_eligibility == PlanExecutionEligibility.CLARIFICATION_REQUIRED
    assert any(issue.field_path == "assigned_target" for issue in validated.validation_issues)


def test_validate_team_draft_returns_structured_clarification_when_lead_missing():
    session = UniversalPlanSession(session_id="team-validation")
    draft = session.set_team_draft(
        {
            "action": "plan_mode",
            "kind": "team",
            "project": {
                "name": "Glance",
                "description": "AI support for devices",
                "domain": "support",
            },
            "teams": [
                {
                    "name": "Research",
                    "description": "No lead defined",
                    "domain": "research",
                    "agents": [
                        {
                            "name": "Taylor",
                            "title": "Analyst",
                            "specialization": "research",
                            "goal": "Collect insights",
                            "backstory": "Generalist",
                            "is_lead": False,
                            "model_tier": "sonnet",
                        }
                    ],
                }
            ],
        }
    )

    validated = validate_team_draft(draft)

    assert validated.execution_eligibility == PlanExecutionEligibility.CLARIFICATION_REQUIRED
    assert any(issue.field_path == "teams[0].lead" for issue in validated.validation_issues)


def test_apply_clarification_values_revalidates_task_draft(isolated_backend):
    from app.core.agent_factory import get_agent_factory

    factory = get_agent_factory()
    team, _agents = factory.create_team_from_template("dev")
    factory.create_team_from_template("product")

    session = UniversalPlanSession(session_id="clarify-task")
    session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Prepare memo",
            "description": "Need a valid owner",
        }
    )

    updated = session.apply_clarification_values({"assigned_target": team.name})

    assert updated.assigned_team_id == team.id
    assert updated.execution_eligibility == PlanExecutionEligibility.ELIGIBLE
    assert updated.validation_issues == []


def test_validate_before_execute_returns_to_clarification_when_runtime_drift(isolated_backend):
    from app.core.agent_factory import get_agent_factory

    factory = get_agent_factory()
    team, _agents = factory.create_team_from_template("dev")

    session = UniversalPlanSession(session_id="task-drift")
    draft = session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Prepare memo",
            "description": "Need a valid owner",
            "team_id": team.id,
            "team_name": team.name,
        }
    )

    factory.delete_team(team.id)

    with pytest.raises(PlanClarificationRequiredError):
        session.validate_before_execute()

    assert session.draft is not None
    assert session.draft.id == draft.id
    assert session.draft.execution_eligibility == PlanExecutionEligibility.CLARIFICATION_REQUIRED
    assert session.state == PlanState.AWAITING_CONFIRMATION


def test_task_plan_executor_creates_pending_task_and_broadcasts(isolated_backend, monkeypatch):
    from app.core import universal_plan as universal_plan_module

    scheduled = []
    broadcasts = []

    async def fake_execute_task(*_args, **_kwargs):
        return None

    def fake_schedule(coro):
        scheduled.append(coro)
        coro.close()
        return None

    async def fake_broadcast(message):
        broadcasts.append(message)

    orchestrator = universal_plan_module.get_orchestrator()
    team, _agents = universal_plan_module.get_agent_factory().create_team_from_template("dev")
    monkeypatch.setattr(orchestrator, "execute_task", fake_execute_task)
    monkeypatch.setattr(asyncio, "create_task", fake_schedule)

    session = UniversalPlanSession(session_id="task-executor")
    draft = session.set_task_draft(
        {
            "action": "plan_mode",
            "kind": "task",
            "title": "Draft launch brief",
            "description": "Create a short launch brief.",
            "priority": "medium",
            "execution_mode": "auto",
                "team_id": team.id,
                "team_name": team.name,
        }
    )

    task = asyncio.run(TaskPlanExecutor().execute(draft, fake_broadcast))

    assert task.title == "Draft launch brief"
    assert task.status == "pending"
    assert len(scheduled) == 1
    assert broadcasts[0]["type"] == "task_created"


def test_team_plan_executor_creates_team_and_broadcasts(isolated_backend, monkeypatch):
    scheduled = []
    broadcasts = []

    def fake_schedule(coro):
        scheduled.append(coro)
        coro.close()
        return None

    async def fake_broadcast(message):
        broadcasts.append(message)

    monkeypatch.setattr(asyncio, "create_task", fake_schedule)

    session = UniversalPlanSession(session_id="team-executor")
    draft = session.set_team_draft(
        {
            "action": "plan_mode",
            "kind": "team",
            "project": {
                "name": "Glance",
                "description": "AI support for devices",
                "domain": "support",
                "short_term_goal": "Fundraising deck",
            },
            "teams": [
                {
                    "name": "Fundraising",
                    "description": "Raise the pre-seed",
                    "domain": "finance",
                    "agents": [
                        {
                            "name": "Sophie",
                            "title": "Fundraising Lead",
                            "specialization": "fundraising",
                            "goal": "Lead the process",
                            "backstory": "Experienced operator",
                            "is_lead": True,
                            "model_tier": "sonnet",
                        }
                    ],
                }
            ],
        }
    )

    result = asyncio.run(TeamPlanExecutor().execute(draft, fake_broadcast))

    assert result["project"]["name"] == "Glance"
    assert len(result["teams"]) == 1
    assert result["agents"][0]["name"] == "Sophie"
    assert len(scheduled) == 1
    assert broadcasts[0]["type"] == "team_created"


def test_team_plan_executor_preserves_existing_brief_fields(isolated_backend, monkeypatch):
    from app.memory.project_context import get_project_context_store

    scheduled = []

    def fake_schedule(coro):
        scheduled.append(coro)
        coro.close()
        return None

    async def fake_broadcast(_message):
        return None

    monkeypatch.setattr(asyncio, "create_task", fake_schedule)

    ctx_store = get_project_context_store()
    initial_state, changed = ctx_store.publish_context(
        {
            "name": "Glance",
            "description": "AI support for devices",
            "domain": "support",
            "short_term_goal": "Fundraising deck",
            "tech_stack": "Next.js + FastAPI",
            "target_audience": "Device manufacturers",
            "business_model": "B2B SaaS",
            "notes": "Need validation on pilot pricing.",
        }
    )
    assert changed is True
    assert initial_state.published is not None

    session = UniversalPlanSession(session_id="team-executor-preserve-brief")
    draft = session.set_team_draft(
        {
            "action": "plan_mode",
            "kind": "team",
            "project": {
                "name": "Glance",
                "description": "AI support for devices",
                "domain": "support",
                "short_term_goal": "Customer discovery sprint",
            },
            "teams": [
                {
                    "name": "Fundraising",
                    "description": "Raise the pre-seed",
                    "domain": "finance",
                    "agents": [
                        {
                            "name": "Sophie",
                            "title": "Fundraising Lead",
                            "specialization": "fundraising",
                            "goal": "Lead the process",
                            "backstory": "Experienced operator",
                            "is_lead": True,
                            "model_tier": "sonnet",
                        }
                    ],
                }
            ],
        }
    )

    asyncio.run(TeamPlanExecutor().execute(draft, fake_broadcast))

    next_state = ctx_store.load_state()
    assert next_state.published is not None
    assert next_state.published.short_term_goal == "Customer discovery sprint"
    assert next_state.published.tech_stack == "Next.js + FastAPI"
    assert next_state.published.target_audience == "Device manufacturers"
    assert next_state.published.business_model == "B2B SaaS"
    assert next_state.published.notes == "Need validation on pilot pricing."
    assert len(scheduled) == 1


def test_project_context_store_normalizes_legacy_payload_without_conversation(isolated_backend):
    from app.memory.project_context import get_project_context_store

    legacy_payload = {
        "name": "Legacy Project",
        "description": "Legacy description",
        "domain": "legacy",
        "short_term_goal": "Ship beta",
        "conversation": [
            {"role": "user", "content": "This should not survive in the canonical brief."}
        ],
    }
    (isolated_backend / "project_context.json").write_text(
        json.dumps(legacy_payload, indent=2),
        encoding="utf-8",
    )

    ctx_store = get_project_context_store()
    state = ctx_store.load_state()
    active = ctx_store.load_context()

    assert state.published is not None
    assert state.draft is not None
    assert active is not None
    assert active["name"] == "Legacy Project"
    assert "conversation" not in active
    assert state.has_unpublished_changes is False


def test_project_context_publish_is_idempotent_for_same_payload(isolated_backend):
    from app.memory.project_context import get_project_context_store

    ctx_store = get_project_context_store()
    payload = {
        "name": "Glance",
        "description": "AI support for devices",
        "domain": "support",
        "short_term_goal": "Ship beta",
    }

    first_state, first_changed = ctx_store.publish_context(payload)
    second_state, second_changed = ctx_store.publish_context(payload)

    assert first_changed is True
    assert second_changed is False
    assert first_state.published is not None
    assert second_state.published is not None
    assert first_state.published.revision == second_state.published.revision
