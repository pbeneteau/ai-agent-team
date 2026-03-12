import pytest


def _reset_backend_caches():
    from app.config import get_settings
    from app.core import usage_tracker as usage_tracker_module
    from app.core.agent_factory import get_agent_factory
    from app.core.document_store import get_document_store
    from app.core.knowledge import get_knowledge_audit_service
    from app.core.orchestrator import get_orchestrator
    from app.core.workspace import get_workspace_manager
    from app.memory.project_context import get_project_context_store
    from app.memory.skills_store import get_skills_store
    from app.memory.vector_store import get_vector_store

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


@pytest.fixture()
def isolated_backend(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-for-smoke")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("TEAMS_FILE", str(data_dir / "teams.json"))
    monkeypatch.setenv("WORKSPACES_DIR", str(data_dir / "workspaces"))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(data_dir / "chromadb"))
    _reset_backend_caches()
    yield data_dir
    _reset_backend_caches()


class _FakeStructuredValue:
    def __init__(self, payload: dict):
        self._payload = payload
        for key, value in payload.items():
            setattr(self, key, value)

    def model_dump(self, mode: str = "json") -> dict:
        assert mode == "json"
        return self._payload


class _FakeStructuredResult:
    def __init__(self, payload: dict):
        self.value = _FakeStructuredValue(payload)


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, *, name: str, input_payload: dict):
        self.name = name
        self.input = input_payload


def test_associate_extract_action_parses_fenced_json(isolated_backend):
    from app.agents.associate import AssociateChat

    chat = AssociateChat()
    action = chat.extract_action(
        """Je prépare un plan.\n```json\n{"action":"plan_mode","kind":"task","title":"Deck","description":"Préparer le deck"}\n```"""
    )

    assert action is not None
    assert action["action"] == "plan_mode"
    assert action["kind"] == "task"


def test_associate_extracts_tool_action_from_response_blocks(isolated_backend):
    from app.agents.associate import AssociateChat

    chat = AssociateChat()
    action = chat._extract_action_from_response(
        [
            _FakeToolUseBlock(
                name="propose_task_plan",
                input_payload={
                    "title": "Deck",
                    "description": "Préparer le deck",
                    "summary": "Deck investisseur",
                },
            )
        ]
    )

    assert action is not None
    assert action.action == "plan_task"
    assert action.kind == "task"
    assert action.title == "Deck"


def test_associate_observability_request_name_maps_task_plan(isolated_backend):
    from app.agents.associate import _associate_observability_request_name
    from app.models.chat_actions import TaskPlanProposalAction

    request_name = _associate_observability_request_name(
        TaskPlanProposalAction(title="Deck", description="Préparer le deck")
    )

    assert request_name == "associate_propose_task_plan"


def test_associate_observability_request_name_maps_team_plan(isolated_backend):
    from app.agents.associate import _associate_observability_request_name
    from app.models.chat_actions import TeamPlanProposalAction

    request_name = _associate_observability_request_name(
        TeamPlanProposalAction(title="Team", summary="Structurer l'équipe")
    )

    assert request_name == "associate_propose_team_plan"


def test_associate_observability_request_name_maps_text_only_response(isolated_backend):
    from app.agents.associate import _associate_observability_request_name

    assert _associate_observability_request_name(None) == "associate_chat_response"


def test_associate_resolution_marks_invalid_tool_use_as_failed_text_only(isolated_backend):
    from app.agents.associate import AssociateChat

    chat = AssociateChat()
    resolution = chat._resolve_action(
        [
            _FakeToolUseBlock(
                name="propose_task_plan",
                input_payload={},
            )
        ],
        "Réponse simple sans JSON.",
    )

    assert resolution.action is None
    assert resolution.action_source == "tool_use_invalid_text_only"
    assert resolution.request_name == "associate_propose_task_plan"
    assert resolution.success is False
    assert resolution.tool_use_error is not None


def test_associate_resolution_recovers_from_invalid_tool_use_with_legacy_json(isolated_backend):
    from app.agents.associate import AssociateChat

    chat = AssociateChat()
    resolution = chat._resolve_action(
        [
            _FakeToolUseBlock(
                name="propose_task_plan",
                input_payload={},
            )
        ],
        """```json
{"action":"plan_task","kind":"task","title":"Deck","description":"Préparer le deck"}
```""",
    )

    assert resolution.action is not None
    assert resolution.action_source == "tool_use_invalid_legacy_json"
    assert resolution.request_name == "associate_propose_task_plan"
    assert resolution.success is True
    assert resolution.tool_use_error is not None


def test_team_builder_extract_json_parses_fenced_json(isolated_backend):
    from app.core.team_builder import TeamBuilderSession

    session = TeamBuilderSession()
    payload = session._extract_json(
        """Voici ma proposition.\n```json\n{"project":{"name":"Glance"},"teams":[],"ready_to_create":false}\n```"""
    )

    assert payload is not None
    assert payload["project"]["name"] == "Glance"
    assert payload["ready_to_create"] is False


def test_universal_plan_session_accepts_typed_task_action(isolated_backend):
    from app.core.universal_plan import UniversalPlanSession
    from app.models.chat_actions import TaskPlanProposalAction

    session = UniversalPlanSession(session_id="session-typed-task")
    draft = session.set_task_draft(
        TaskPlanProposalAction(
            title="Deck",
            description="Préparer le deck investisseur.",
            summary="Deck",
            team_id="team-1",
        )
    )

    assert draft.task_title == "Deck"
    assert draft.metadata["source_action"] == "plan_task"


@pytest.mark.asyncio
async def test_orchestrator_plan_with_lead_uses_structured_runtime(isolated_backend, monkeypatch):
    from app.core.orchestrator import Orchestrator
    from app.models.agent import AgentConfig, AgentRole, ModelTier
    from app.models.task import TaskExecutionMode, TaskPriority, TaskResponse, TaskStatus
    from app.models.team import TeamConfig

    captured: dict = {}

    async def fake_request_structured_json_async(**kwargs):
        captured.update(kwargs)
        return _FakeStructuredResult(
            {
                "mode": "standalone",
                "planning_notes": "Use isolated specialists.",
                "nodes": [],
            }
        )

    monkeypatch.setattr(
        "app.core.orchestrator.request_structured_json_async",
        fake_request_structured_json_async,
    )

    orchestrator = Orchestrator()
    task = TaskResponse(
        id="task-1",
        title="Prepare plan",
        description="Create a concise execution plan.",
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        execution_mode=TaskExecutionMode.AUTO,
        created_at="2026-03-10T00:00:00+00:00",
        updated_at="2026-03-10T00:00:00+00:00",
    )
    team = TeamConfig(
        id="team-1",
        name="Ops",
        description="Operations team",
        domain="ops",
        scope_note="Keep execution explicit.",
    )
    lead = AgentConfig(
        id="lead-1",
        name="Lead",
        role=AgentRole.TEAM_LEAD,
        title="Execution Lead",
        specialization="coordination",
        goal="Coordinate planning",
        backstory="Lead planner.",
        model_tier=ModelTier.SONNET,
    )
    specialist = AgentConfig(
        id="spec-1",
        name="Analyst",
        role=AgentRole.SPECIALIST,
        title="Analyst",
        specialization="analysis",
        goal="Handle analysis",
        backstory="Focused specialist.",
        team_id=team.id,
    )

    blueprint = await orchestrator._plan_with_lead(
        task=task,
        team=team,
        lead=lead,
        specialists=[specialist],
        project_context_summary="Project context",
        task_documents_context="Documents context",
    )

    assert blueprint == {
        "mode": "standalone",
        "planning_notes": "Use isolated specialists.",
        "nodes": [],
    }
    assert captured["request_name"] == "task_planner:task-1"
    assert captured["system"]


@pytest.mark.asyncio
async def test_orchestrator_extract_result_metadata_uses_structured_runtime(isolated_backend, monkeypatch):
    from app.core.orchestrator import Orchestrator

    async def fake_request_structured_json_async(**_kwargs):
        return _FakeStructuredResult(
            {
                "sources": ["https://example.com/report"],
                "assumptions": ["Assumption"],
                "warnings": ["Warning"],
            }
        )

    monkeypatch.setattr(
        "app.core.orchestrator.request_structured_json_async",
        fake_request_structured_json_async,
    )

    orchestrator = Orchestrator()
    sources, assumptions, warnings = await orchestrator._extract_result_metadata(
        "## Sources\n- legacy source",
            task_id="task-1",
        node_id="node-1",
    )

    assert sources == ["https://example.com/report"]
    assert assumptions == ["Assumption"]
    assert warnings == ["Warning"]


@pytest.mark.asyncio
async def test_run_learn_from_work_uses_structured_runtime(isolated_backend, monkeypatch):
    from app.core.learning import run_learn_from_work
    from app.core.workspace import get_workspace_manager
    from app.models.agent import AgentConfig, AgentRole
    from app.models.task import (
        TaskExecutionMode,
        TaskExecutionNode,
        TaskNodeType,
        TaskPriority,
        TaskResponse,
        TaskStatus,
    )

    async def fake_request_structured_json_async(**_kwargs):
        return _FakeStructuredResult(
            {
                "insights": ["Preserve explicit execution plans for risky work."],
                "cautions": ["Do not hide degraded structured-output behavior."],
            }
        )

    monkeypatch.setattr(
        "app.core.learning.request_structured_json_async",
        fake_request_structured_json_async,
    )

    agent = AgentConfig(
        id="agent-1",
        name="Sophie",
        role=AgentRole.SPECIALIST,
        title="Fundraising Specialist",
        specialization="fundraising",
        goal="Help raise the round",
        backstory="Experienced operator.",
    )
    task = TaskResponse(
        id="task-1",
        title="Investor memo",
        description="Prepare a concise investor memo.",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.HIGH,
        execution_mode=TaskExecutionMode.STANDALONE,
        created_at="2026-03-10T00:00:00+00:00",
        updated_at="2026-03-10T00:00:00+00:00",
    )
    node = TaskExecutionNode(
        id="node-1",
        title="Memo synthesis",
        description="Summarize the output",
        node_type=TaskNodeType.SPECIALIST,
        assigned_agent_id=agent.id,
        assigned_agent_name=agent.name,
        result="A useful completed result.",
        sources=["https://example.com"],
        assumptions=["Assumption"],
        warnings=["Warning"],
    )

    success = await run_learn_from_work(agent, task, node)

    workspace = get_workspace_manager().get(agent.id, agent.name, agent.title)
    content = workspace.read_skill("work_learnings") or ""

    assert success is True
    assert "Preserve explicit execution plans" in content
    assert "Do not hide degraded structured-output behavior" in content
