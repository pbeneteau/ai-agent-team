import asyncio
import json

import pytest


def _reset_backend_caches():
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


class FakeCrewResult:
    def __init__(self, text: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.raw = text
        self.token_usage = type(
            "FakeUsage",
            (),
            {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )()

    def __str__(self) -> str:
        return self.raw


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


def _create_ready_team():
    from app.core.agent_factory import get_agent_factory
    from app.models.agent import AgentRole, AgentStatus

    factory = get_agent_factory()
    team, agents = factory.create_custom_team(
        name="Execution Team",
        description="Team for orchestration tests",
        domain="ops",
        agent_specs=[
            {
                "name": "Lead",
                "title": "Execution Lead",
                "specialization": "coordination",
                "goal": "Coordinate execution",
                "backstory": "Lead the team and compile outcomes.",
                "is_lead": True,
                "model_tier": "opus",
                "tools": [],
            },
            {
                "name": "Analyst A",
                "title": "Analyst A",
                "specialization": "analysis_a",
                "goal": "Handle scope A",
                "backstory": "Expert in scope A.",
                "tools": [],
            },
            {
                "name": "Analyst B",
                "title": "Analyst B",
                "specialization": "analysis_b",
                "goal": "Handle scope B",
                "backstory": "Expert in scope B.",
                "tools": [],
            },
            {
                "name": "Analyst C",
                "title": "Analyst C",
                "specialization": "analysis_c",
                "goal": "Handle scope C",
                "backstory": "Expert in scope C.",
                "tools": [],
            },
        ],
    )
    for agent in agents:
        factory.update_agent_status(agent.id, AgentStatus.READY)

    ordered_agents = factory.get_ordered_team_agents(team.id)
    lead = next(agent for agent in ordered_agents if agent.role == AgentRole.TEAM_LEAD)
    specialists = [agent for agent in ordered_agents if agent.role == AgentRole.SPECIALIST]
    return factory, team, lead, specialists


def test_legacy_tasks_load_with_default_execution_plan(isolated_backend):
    from app.core.orchestrator import Orchestrator

    legacy_payload = {
        "legacy-task": {
            "id": "legacy-task",
            "title": "Legacy",
            "description": "Old schema payload",
            "status": "pending",
            "priority": "medium",
            "assigned_team_id": None,
            "assigned_agent_ids": [],
            "result": None,
            "error": None,
            "created_at": "2026-03-07T00:00:00+00:00",
            "updated_at": "2026-03-07T00:00:00+00:00",
            "progress_log": [],
            "sources": [],
            "assumptions": [],
            "warnings": [],
        }
    }
    (isolated_backend / "tasks.json").write_text(
        json.dumps(legacy_payload, indent=2),
        encoding="utf-8",
    )

    orchestrator = Orchestrator()
    task = orchestrator.get_task("legacy-task")

    assert task is not None
    assert task.execution_mode == "auto"
    assert task.execution_plan.status == "not_planned"
    assert task.context_document_ids == []


def test_get_ordered_team_agents_respects_lead_first(isolated_backend):
    factory, team, lead, specialists = _create_ready_team()

    team.agent_ids = [specialists[1].id, lead.id, specialists[0].id, specialists[2].id]
    ordered = factory.get_ordered_team_agents(team.id)

    assert ordered[0].id == lead.id
    assert [agent.id for agent in ordered[1:]] == [
        specialists[1].id,
        specialists[0].id,
        specialists[2].id,
    ]


def test_standalone_execution_keeps_specialists_isolated(isolated_backend, monkeypatch):
    from app.core import orchestrator as orchestrator_module
    from app.core.usage_tracker import get_usage_tracker
    from app.models.task import TaskExecutionMode, TaskNodeType, TaskStatus

    _, team, _, specialists = _create_ready_team()
    orchestrator = orchestrator_module.Orchestrator()

    async def fake_plan(*_args, **_kwargs):
        return {
            "mode": "standalone",
            "planning_notes": "Independent specialists only.",
            "nodes": [
                {
                    "agent_id": specialists[0].id,
                    "title": "Scope A",
                    "brief": "Handle the A workstream independently.",
                    "depends_on": [],
                },
                {
                    "agent_id": specialists[1].id,
                    "title": "Scope B",
                    "brief": "Handle the B workstream independently.",
                    "depends_on": [],
                },
            ],
        }

    def fake_kickoff(self):
        return FakeCrewResult(self.tasks[0].description, prompt_tokens=11, completion_tokens=7)

    monkeypatch.setattr(orchestrator, "_plan_with_lead", fake_plan)
    monkeypatch.setattr(orchestrator_module, "get_tools_for_agent", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orchestrator_module.Crew, "kickoff", fake_kickoff)
    monkeypatch.setattr(orchestrator_module, "run_learn_from_work", lambda *_args, **_kwargs: asyncio.sleep(0, result=False))

    task = orchestrator.create_task(
        title="Standalone orchestration",
        description="Prepare a structured execution package.",
        team_id=team.id,
        execution_mode=TaskExecutionMode.AUTO,
    )

    asyncio.run(orchestrator.execute_task(task.id))
    stored_task = orchestrator.get_task(task.id)
    specialist_nodes = [
        node for node in stored_task.execution_plan.nodes if node.node_type == TaskNodeType.SPECIALIST
    ]
    compile_node = next(
        node for node in stored_task.execution_plan.nodes if node.node_type == TaskNodeType.LEAD_COMPILE
    )

    assert stored_task.status == TaskStatus.COMPLETED
    assert stored_task.execution_plan.mode == "standalone"
    assert all(
        "## Upstream results you are allowed to use" not in (node.result or "")
        for node in specialist_nodes
    )
    assert "## Upstream results you are allowed to use" in (compile_node.result or "")
    usage = get_usage_tracker().summary()
    assert usage["total"]["calls"] == 3
    assert usage["total"]["input_tokens"] == 33
    assert usage["total"]["output_tokens"] == 21
    deliverables = orchestrator.list_task_deliverables(task.id)
    assert [item.path for item in deliverables] == [
        "system/final-deliverable.md",
        "system/nodes/01-scope-a.md",
        "system/nodes/02-scope-b.md",
        "system/nodes/03-execution-lead-final-compilation.md",
    ]
    final_deliverable = orchestrator.read_task_deliverable(task.id, "system/final-deliverable.md")
    assert "## Résultat final" in final_deliverable["content"]
    assert "Prepare a structured execution package." in final_deliverable["content"]


def test_sync_task_deliverables_preserves_agent_authored_files(isolated_backend):
    from app.core.orchestrator import Orchestrator
    from app.models.task import TaskExecutionNode, TaskExecutionPlan, TaskNodeStatus, TaskNodeType, TaskStatus

    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Authored deliverables",
        description="Verify task-authored files are preserved.",
    )
    task.status = TaskStatus.COMPLETED
    task.result = "Final result"
    task.execution_plan = TaskExecutionPlan(
        nodes=[
            TaskExecutionNode(
                id="node-1",
                title="Research brief",
                description="Draft the brief",
                node_type=TaskNodeType.SINGLE_AGENT,
                status=TaskNodeStatus.COMPLETED,
                assigned_agent_id="agent-1",
                assigned_agent_name="Agent 1",
                result="Node result",
            )
        ]
    )

    authored_path = orchestrator._task_deliverables_root(task.id) / "authored" / "brief.md"
    authored_path.parent.mkdir(parents=True, exist_ok=True)
    authored_path.write_text("# Brief\n\nAgent-authored file", encoding="utf-8")

    orchestrator._sync_task_deliverables(task)

    deliverables = [item.path for item in orchestrator.list_task_deliverables(task.id)]
    assert "authored/brief.md" in deliverables
    assert "system/final-deliverable.md" in deliverables
    assert "system/nodes/01-research-brief.md" in deliverables


def test_delete_task_removes_persisted_state_and_deliverables(isolated_backend):
    from app.core.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Delete me",
        description="Verify full task deletion cleanup.",
    )

    deliverable_path = orchestrator._task_deliverables_root(task.id) / "authored" / "notes.md"
    deliverable_path.parent.mkdir(parents=True, exist_ok=True)
    deliverable_path.write_text("# Notes\n\nCleanup me too.", encoding="utf-8")

    assert orchestrator.delete_task(task.id) is True
    assert orchestrator.get_task(task.id) is None
    assert not orchestrator._task_deliverables_root(task.id, create=False).exists()

    persisted = json.loads((isolated_backend / "tasks.json").read_text(encoding="utf-8"))
    assert task.id not in persisted


def test_delete_task_rejects_running_task(isolated_backend):
    from app.core.orchestrator import Orchestrator
    from app.models.task import TaskStatus

    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Running delete guard",
        description="Deletion should be blocked while running.",
    )
    task.status = TaskStatus.RUNNING

    with pytest.raises(ValueError, match="running"):
        orchestrator.delete_task(task.id)

    assert orchestrator.get_task(task.id) is not None


def test_execute_task_persists_original_failure_details_and_traceback(isolated_backend, monkeypatch):
    from app.core import orchestrator as orchestrator_module
    from app.models.task import TaskExecutionMode, TaskNodeStatus, TaskPlanStatus, TaskStatus

    _, team, _, specialists = _create_ready_team()
    orchestrator = orchestrator_module.Orchestrator()

    async def fake_plan(*_args, **_kwargs):
        return {
            "mode": "standalone",
            "planning_notes": "Single failing specialist.",
            "nodes": [
                {
                    "agent_id": specialists[0].id,
                    "title": "Failing scope",
                    "brief": "Trigger a low-level I/O failure.",
                    "depends_on": [],
                }
            ],
        }

    def failing_kickoff(self):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(orchestrator, "_plan_with_lead", fake_plan)
    monkeypatch.setattr(orchestrator_module, "get_tools_for_agent", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orchestrator_module.Crew, "kickoff", failing_kickoff)
    monkeypatch.setattr(orchestrator_module, "run_learn_from_work", lambda *_args, **_kwargs: asyncio.sleep(0, result=False))

    task = orchestrator.create_task(
        title="Persist failure details",
        description="Make sure runtime failures preserve diagnostics.",
        team_id=team.id,
        execution_mode=TaskExecutionMode.AUTO,
    )

    asyncio.run(orchestrator.execute_task(task.id))
    stored_task = orchestrator.get_task(task.id)
    assert stored_task is not None

    failing_node = next(node for node in stored_task.execution_plan.nodes if node.title == "Failing scope")

    assert stored_task.status == TaskStatus.FAILED
    assert stored_task.execution_plan.status == TaskPlanStatus.FAILED
    assert stored_task.error_type == "OSError"
    assert stored_task.failure_stage == "crew_kickoff"
    assert "[Errno 5] Input/output error" in (stored_task.error or "")
    assert "OSError" in (stored_task.error_traceback or "")
    assert "Input/output error" in (stored_task.error_traceback or "")

    assert failing_node.status == TaskNodeStatus.FAILED
    assert failing_node.error_type == "OSError"
    assert failing_node.failure_stage == "crew_kickoff"
    assert "Input/output error" in (failing_node.error_traceback or "")

    deliverable_paths = [item.path for item in stored_task.deliverables]
    assert "system/error.txt" in deliverable_paths
    assert "system/error-traceback.txt" in deliverable_paths

    traceback_payload = orchestrator.read_task_deliverable(task.id, "system/error-traceback.txt")
    assert "Input/output error" in traceback_payload["content"]

    node_payload = orchestrator.read_task_deliverable(task.id, "system/nodes/01-failing-scope.md")
    assert "## Error Traceback" in node_payload["content"]
    assert "crew_kickoff" in node_payload["content"]


def test_task_deliverable_tools_accept_relative_paths(isolated_backend):
    from app.core.orchestrator import (
        Orchestrator,
        _build_task_deliverable_list_tool,
        _build_task_deliverable_read_tool,
        _build_task_deliverable_write_tool,
    )

    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Deliverable tools",
        description="Verify authored deliverable tools work with relative paths.",
    )

    root = orchestrator._task_deliverables_root(task.id)
    write_tool = _build_task_deliverable_write_tool(root)
    list_tool = _build_task_deliverable_list_tool(root)
    read_tool = _build_task_deliverable_read_tool(root)

    result = write_tool.func(
        path="authored/test-output.md",
        content="# Test\n\nHello",
    )
    assert "Saved deliverable: authored/test-output.md" in result
    assert (root / "authored" / "test-output.md").read_text(encoding="utf-8") == "# Test\n\nHello"

    listing = list_tool.func(sub_path="authored")
    assert "authored/test-output.md" in listing

    content = read_tool.func(path="authored/test-output.md")
    assert content == "# Test\n\nHello"


def test_task_deliverable_read_tool_rejects_directory_paths(isolated_backend):
    from app.core.orchestrator import Orchestrator, _build_task_deliverable_read_tool

    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Deliverable read validation",
        description="Verify directory paths are rejected.",
    )

    root = orchestrator._task_deliverables_root(task.id)
    (root / "authored").mkdir(parents=True, exist_ok=True)
    read_tool = _build_task_deliverable_read_tool(root)

    result = read_tool.func(path="authored")
    assert "ERROR: not a file: authored" in result


def test_task_prompt_explicitly_forbids_placeholder_deliverable_writes(isolated_backend):
    from app.core.orchestrator import Orchestrator, _prompt_for_node
    from app.models.task import TaskExecutionNode, TaskNodeType

    _, team, _lead, specialists = _create_ready_team()
    specialist = specialists[0]
    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Deliverable prompt",
        description="Generate a final file deliverable.",
        team_id=team.id,
    )
    node = TaskExecutionNode(
        id="node-1",
        title="Write file",
        description="Write a final deliverable to the task folder.",
        node_type=TaskNodeType.SINGLE_AGENT,
        assigned_agent_id=specialist.id,
        assigned_agent_name=specialist.name,
    )

    prompt = _prompt_for_node(task, node, specialist, None, None, False)

    assert "NEVER call task_deliverable_write with only a path." in prompt
    assert "NEVER create placeholder, empty, or stub deliverables." in prompt
    assert "Invalid example: task_deliverable_write(path='authored/summary.md')" in prompt


def test_task_deliverable_write_tool_requires_content_argument(isolated_backend):
    from app.core.orchestrator import Orchestrator, _build_task_deliverable_write_tool

    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Deliverable write validation",
        description="Verify missing content is rejected at the tool signature level.",
    )

    write_tool = _build_task_deliverable_write_tool(orchestrator._task_deliverables_root(task.id))
    schema = write_tool.args_schema.model_json_schema()

    assert set(schema.get("required", [])) == {"path", "content"}

    with pytest.raises(TypeError):
        write_tool.func(path="authored/empty.md")


def test_execute_task_surfaces_tool_validation_errors_readably(isolated_backend, monkeypatch):
    from pydantic import ValidationError

    from app.core import orchestrator as orchestrator_module
    from app.models.task import TaskExecutionMode, TaskStatus

    _, team, _, specialists = _create_ready_team()
    orchestrator = orchestrator_module.Orchestrator()

    async def fake_plan(*_args, **_kwargs):
        return {
            "mode": "standalone",
            "planning_notes": "Single specialist with an invalid tool call.",
            "nodes": [
                {
                    "agent_id": specialists[0].id,
                    "title": "Bad tool invocation",
                    "brief": "Simulate a tool call that omits required content.",
                    "depends_on": [],
                }
            ],
        }

    write_tool = orchestrator_module._build_task_deliverable_write_tool(isolated_backend / "task-deliverables")
    with pytest.raises(ValidationError) as exc_info:
        write_tool.args_schema.model_validate({"path": "authored/only-path.md"})
    validation_error = exc_info.value

    def failing_kickoff(self):
        raise validation_error

    monkeypatch.setattr(orchestrator, "_plan_with_lead", fake_plan)
    monkeypatch.setattr(orchestrator_module, "get_tools_for_agent", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orchestrator_module.Crew, "kickoff", failing_kickoff)
    monkeypatch.setattr(orchestrator_module, "run_learn_from_work", lambda *_args, **_kwargs: asyncio.sleep(0, result=False))

    task = orchestrator.create_task(
        title="Readable tool validation error",
        description="Make sure tool validation failures are explicit.",
        team_id=team.id,
        execution_mode=TaskExecutionMode.AUTO,
    )

    asyncio.run(orchestrator.execute_task(task.id))
    stored_task = orchestrator.get_task(task.id)
    assert stored_task is not None

    assert stored_task.status == TaskStatus.FAILED
    assert stored_task.error_type == "ValidationError"
    assert stored_task.failure_stage == "crew_kickoff"
    assert "content" in (stored_task.error or "").lower()
    assert "validation error" in (stored_task.error or "").lower()
    assert "content" in (stored_task.error_traceback or "").lower()


def test_workspace_file_tools_are_scoped_and_require_workspace_path(isolated_backend):
    from app.tools.registry import get_tools_for_agent

    workspace = isolated_backend / "workspaces" / "tool-scope"
    workspace.mkdir(parents=True, exist_ok=True)

    write_tool, read_tool = get_tools_for_agent(
        ["file_write", "file_read"],
        workspace_path=str(workspace),
    )

    schema = write_tool.args_schema.model_json_schema()
    assert set(schema.get("required", [])) == {"path", "content"}

    result = write_tool.func(path="notes/todo.md", content="# TODO\n\nScoped write")
    assert "Saved workspace file: notes/todo.md" in result
    assert (workspace / "notes" / "todo.md").read_text(encoding="utf-8") == "# TODO\n\nScoped write"
    assert read_tool.func(path="notes/todo.md") == "# TODO\n\nScoped write"

    assert "Path traversal attempt blocked" in write_tool.func(path="../escape.md", content="blocked")
    assert "Path traversal attempt blocked" in read_tool.func(path="../escape.md")

    with pytest.raises(ValueError, match="workspace_path"):
        get_tools_for_agent(["file_write"], workspace_path=None)


def test_read_task_deliverable_uses_resolved_root_paths(isolated_backend):
    from app.core.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Deliverable read path handling",
        description="Verify deliverable reads do not fail on relative_to path handling.",
    )

    root = orchestrator._task_deliverables_root(task.id)
    file_path = root / "authored" / "report.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("# Report\n\nOK", encoding="utf-8")

    payload = orchestrator.read_task_deliverable(task.id, "authored/report.md")
    assert payload["path"] == "authored/report.md"
    assert payload["name"] == "report.md"
    assert payload["content"] == "# Report\n\nOK"


def test_reconcile_interrupted_tasks_marks_running_task_failed(isolated_backend):
    from app.core.orchestrator import Orchestrator
    from app.models.task import (
        TaskExecutionNode,
        TaskExecutionPlan,
        TaskNodeStatus,
        TaskNodeType,
        TaskPlanStatus,
        TaskStatus,
    )

    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Interrupted task",
        description="Should be recovered on restart.",
    )
    task.status = TaskStatus.RUNNING
    task.execution_plan = TaskExecutionPlan(
        status=TaskPlanStatus.RUNNING,
        nodes=[
            TaskExecutionNode(
                id="node-running",
                title="Running node",
                description="Still running at shutdown",
                node_type=TaskNodeType.SINGLE_AGENT,
                status=TaskNodeStatus.RUNNING,
                assigned_agent_id="agent-1",
                assigned_agent_name="Agent 1",
                started_at="2026-03-07T00:00:00+00:00",
            ),
            TaskExecutionNode(
                id="node-pending",
                title="Pending node",
                description="Not started yet",
                node_type=TaskNodeType.SINGLE_AGENT,
                status=TaskNodeStatus.PENDING,
                assigned_agent_id="agent-2",
                assigned_agent_name="Agent 2",
            ),
        ],
    )
    orchestrator._save_tasks()

    result = orchestrator.reconcile_interrupted_tasks()
    stored_task = orchestrator.get_task(task.id)

    assert result["recovered_tasks"] == 1
    assert result["recovered_nodes"] == 2
    assert stored_task.status == TaskStatus.FAILED
    assert stored_task.execution_plan.status == TaskPlanStatus.FAILED
    assert stored_task.execution_plan.nodes[0].status == TaskNodeStatus.FAILED
    assert stored_task.execution_plan.nodes[1].status == TaskNodeStatus.SKIPPED
    assert stored_task.progress_log[-1].stage == "task_recovered_after_restart"


def test_reconcile_runtime_state_after_restart_clears_stale_agent_occupancy(isolated_backend):
    from app.core.agent_factory import get_agent_factory
    from app.models.agent import AgentOccupancyReason, AgentOccupancyStatus, AgentStatus

    factory, _, _, specialists = _create_ready_team()
    agent = specialists[0]

    factory.update_agent_status(agent.id, AgentStatus.LEARNING)
    factory.update_agent_occupancy(
        agent.id,
        occupancy_status=AgentOccupancyStatus.BUSY,
        occupancy_reason=AgentOccupancyReason.LEARNING,
        current_task_id="task-123",
        current_task_title="Interrupted learning",
        current_node_id="node-123",
        current_node_title="Learning node",
        busy_since="2026-03-07T00:00:00+00:00",
    )

    result = factory.reconcile_runtime_state_after_restart()
    recovered = get_agent_factory().get_agent(agent.id)

    assert result["updated_agents"] >= 1
    assert result["reset_learning_agents"] == 1
    assert recovered.status == AgentStatus.PENDING
    assert recovered.occupancy_status == AgentOccupancyStatus.IDLE
    assert recovered.occupancy_reason is None
    assert recovered.current_task_id is None
    assert recovered.current_node_id is None
    assert recovered.busy_since is None


def test_dependency_graph_injects_only_declared_dependencies(isolated_backend, monkeypatch):
    from app.core import orchestrator as orchestrator_module
    from app.models.task import TaskExecutionMode, TaskNodeType, TaskStatus

    _, team, _, specialists = _create_ready_team()
    orchestrator = orchestrator_module.Orchestrator()

    async def fake_plan(*_args, **_kwargs):
        return {
            "mode": "dependency_graph",
            "planning_notes": "B depends on A; C stays independent.",
            "nodes": [
                {
                    "agent_id": specialists[0].id,
                    "title": "Scope A",
                    "brief": "Produce the upstream analysis for scope A.",
                    "depends_on": [],
                },
                {
                    "agent_id": specialists[1].id,
                    "title": "Scope B",
                    "brief": "Use scope A only if provided as an explicit dependency.",
                    "depends_on": [specialists[0].id],
                },
                {
                    "agent_id": specialists[2].id,
                    "title": "Scope C",
                    "brief": "Handle the C workstream independently.",
                    "depends_on": [],
                },
            ],
        }

    def fake_kickoff(self):
        return FakeCrewResult(self.tasks[0].description, prompt_tokens=5, completion_tokens=3)

    monkeypatch.setattr(orchestrator, "_plan_with_lead", fake_plan)
    monkeypatch.setattr(orchestrator_module, "get_tools_for_agent", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orchestrator_module.Crew, "kickoff", fake_kickoff)
    monkeypatch.setattr(orchestrator_module, "run_learn_from_work", lambda *_args, **_kwargs: asyncio.sleep(0, result=False))

    task = orchestrator.create_task(
        title="Dependency orchestration",
        description="Build a dependency-aware execution plan.",
        team_id=team.id,
        execution_mode=TaskExecutionMode.DEPENDENCY_GRAPH,
    )

    asyncio.run(orchestrator.execute_task(task.id))
    stored_task = orchestrator.get_task(task.id)
    nodes_by_title = {node.title: node for node in stored_task.execution_plan.nodes}

    assert stored_task.status == TaskStatus.COMPLETED
    assert stored_task.execution_plan.mode == "dependency_graph"
    assert "## Upstream results you are allowed to use" in (nodes_by_title["Scope B"].result or "")
    assert "Scope A" in (nodes_by_title["Scope B"].result or "")
    assert "## Upstream results you are allowed to use" not in (nodes_by_title["Scope C"].result or "")


def test_run_agent_research_logs_crewai_usage(isolated_backend, monkeypatch):
    import crewai

    from app.core.learning import run_agent_research
    from app.core.usage_tracker import get_usage_tracker

    factory, _, _, specialists = _create_ready_team()
    researcher = specialists[0]

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeTask:
        def __init__(self, **kwargs):
            self.description = kwargs["description"]
            self.expected_output = kwargs["expected_output"]
            self.agent = kwargs["agent"]

    class FakeCrew:
        def __init__(self, agents, tasks, verbose):
            self.agents = agents
            self.tasks = tasks
            self.verbose = verbose
            self.usage_metrics = None

        def kickoff(self):
            return FakeCrewResult("research done", prompt_tokens=13, completion_tokens=9)

    monkeypatch.setattr(crewai, "Agent", FakeAgent)
    monkeypatch.setattr(crewai, "Task", FakeTask)
    monkeypatch.setattr(crewai, "Crew", FakeCrew)
    monkeypatch.setattr("app.agents.base_agent.build_llm", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("app.tools.registry.get_tools_for_agent", lambda *_args, **_kwargs: [])

    ok = asyncio.run(run_agent_research(researcher.id, "competitive landscape"))

    usage = get_usage_tracker().summary()
    assert ok is True
    assert usage["total"]["calls"] == 1
    assert usage["total"]["input_tokens"] == 13
    assert usage["total"]["output_tokens"] == 9


def test_run_learn_from_work_writes_structured_memory(isolated_backend, monkeypatch):
    from app.core import learning as learning_module
    from app.core.orchestrator import Orchestrator
    from app.core.workspace import get_workspace_manager
    from app.models.task import TaskExecutionNode, TaskNodeStatus, TaskNodeType

    _, _, _, specialists = _create_ready_team()
    agent = specialists[0]
    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Investor positioning",
        description="Produce a strong investor lens from recent benchmarked findings.",
        assigned_agent_id=agent.id,
    )
    node = TaskExecutionNode(
        id="node-memory",
        title="Investor analysis",
        description="Analyse the investor angle with benchmarks and risks.",
        node_type=TaskNodeType.SINGLE_AGENT,
        status=TaskNodeStatus.COMPLETED,
        assigned_agent_id=agent.id,
        assigned_agent_name=agent.name,
        result=(
            "## Summary\n"
            "Benchmark-backed positioning converts better.\n\n"
            "## Sources\n"
            "- https://example.com/benchmark\n"
        ),
        sources=["https://example.com/benchmark"],
        warnings=["Treat TAM claims without a primary source as tentative."],
    )

    class FakeAsyncAnthropic:
        def __init__(self, api_key):
            self.messages = self

        async def create(self, **_kwargs):
            return type(
                "FakeResponse",
                (),
                {
                    "usage": type("Usage", (), {"input_tokens": 11, "output_tokens": 7})(),
                    "content": [type(
                        "ContentBlock",
                        (),
                        {
                            "text": json.dumps(
                                {
                                    "insights": [
                                        "Lead with benchmark-backed investor framing in the opening summary.",
                                        "State the sector fit before presenting financial upside.",
                                    ],
                                    "cautions": [
                                        "Treat TAM claims without a primary source as tentative.",
                                    ],
                                }
                            )
                        },
                    )()],
                },
            )()

    monkeypatch.setattr(learning_module, "AsyncAnthropic", FakeAsyncAnthropic)

    ok = asyncio.run(learning_module.run_learn_from_work(agent, task, node))

    content = get_workspace_manager().get(agent.id, agent.name, agent.title).read_skill(
        learning_module.WORK_LEARNINGS_SKILL
    )
    assert ok is True
    assert content is not None
    assert "## Verified reusable insights" in content
    assert "Lead with benchmark-backed investor framing" in content
    assert "Treat TAM claims without a primary source as tentative." in content


def test_run_learn_from_work_deduplicates_existing_notes(isolated_backend, monkeypatch):
    from app.core import learning as learning_module
    from app.core.orchestrator import Orchestrator
    from app.core.workspace import get_workspace_manager
    from app.models.task import TaskExecutionNode, TaskNodeStatus, TaskNodeType

    _, _, _, specialists = _create_ready_team()
    agent = specialists[0]
    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Duplicate investor insight",
        description="Check that repeated learnings are not stored twice.",
        assigned_agent_id=agent.id,
    )
    node = TaskExecutionNode(
        id="node-duplicate",
        title="Investor summary",
        description="Summarise what matters most for investors.",
        node_type=TaskNodeType.SINGLE_AGENT,
        status=TaskNodeStatus.COMPLETED,
        assigned_agent_id=agent.id,
        assigned_agent_name=agent.name,
        result="Reusable investor framing insight.",
        sources=["https://example.com/source"],
    )

    class FakeAsyncAnthropic:
        def __init__(self, api_key):
            self.messages = self

        async def create(self, **_kwargs):
            return type(
                "FakeResponse",
                (),
                {
                    "usage": type("Usage", (), {"input_tokens": 9, "output_tokens": 5})(),
                    "content": [type(
                        "ContentBlock",
                        (),
                        {
                            "text": json.dumps(
                                {
                                    "insights": [
                                        "Lead with benchmark-backed investor framing in the opening summary.",
                                    ],
                                    "cautions": [],
                                }
                            )
                        },
                    )()],
                },
            )()

    monkeypatch.setattr(learning_module, "AsyncAnthropic", FakeAsyncAnthropic)

    asyncio.run(learning_module.run_learn_from_work(agent, task, node))
    asyncio.run(learning_module.run_learn_from_work(agent, task, node))

    content = get_workspace_manager().get(agent.id, agent.name, agent.title).read_skill(
        learning_module.WORK_LEARNINGS_SKILL
    )
    assert content is not None
    assert content.count("Lead with benchmark-backed investor framing in the opening summary.") == 1


def test_compact_work_learnings_content_respects_size_budget(isolated_backend, monkeypatch):
    from app.core import learning as learning_module

    monkeypatch.setattr(learning_module, "consolidate_skill_content", lambda *_args, **_kwargs: None)
    insights = [f"Reusable insight {i} " + ("x" * 260) for i in range(30)]
    cautions = [f"Reusable caution {i} " + ("y" * 260) for i in range(20)]

    content = learning_module._compact_work_learnings_content(
        insights,
        cautions,
        str(isolated_backend),
    )

    assert len(content) <= learning_module._WORK_LEARNINGS_MAX_CHARS
    assert "## Verified reusable insights" in content
    assert "## Reusable cautions" in content


def test_agent_memory_pack_includes_work_learnings(isolated_backend):
    from app.core.orchestrator import _build_agent_memory_pack
    from app.core.workspace import get_workspace_manager
    from app.memory.skills_store import get_skills_store

    _, _, _, specialists = _create_ready_team()
    agent = specialists[0]
    workspace = get_workspace_manager().get(agent.id, agent.name, agent.title)
    workspace.write_skill(
        "work_learnings",
        (
            "# Work Learnings\n\n"
            "## Verified reusable insights\n"
            "- Reuse benchmark-backed framing for investor updates.\n\n"
            "## Reusable cautions\n"
            "- Keep TAM claims tentative until sourced.\n"
        ),
        author="test",
    )

    memory_pack = _build_agent_memory_pack(agent, get_skills_store())

    assert "## Your reusable work learnings" in memory_pack
    assert "Reuse benchmark-backed framing for investor updates." in memory_pack


def test_execute_task_remains_successful_when_learn_from_work_fails(isolated_backend, monkeypatch):
    from app.core import orchestrator as orchestrator_module
    from app.models.task import TaskExecutionMode, TaskStatus

    _, team, _, specialists = _create_ready_team()
    orchestrator = orchestrator_module.Orchestrator()

    async def fake_plan(*_args, **_kwargs):
        return {
            "mode": "standalone",
            "planning_notes": "Single specialist execution.",
            "nodes": [
                {
                    "agent_id": specialists[0].id,
                    "title": "Scope A",
                    "brief": "Handle scope A.",
                    "depends_on": [],
                },
            ],
        }

    def fake_kickoff(self):
        return FakeCrewResult("## Sources\n- https://example.com", prompt_tokens=4, completion_tokens=2)

    async def failing_learn_from_work(*_args, **_kwargs):
        raise RuntimeError("learning failed")

    monkeypatch.setattr(orchestrator, "_plan_with_lead", fake_plan)
    monkeypatch.setattr(orchestrator_module, "get_tools_for_agent", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orchestrator_module.Crew, "kickoff", fake_kickoff)
    monkeypatch.setattr(orchestrator_module, "run_learn_from_work", failing_learn_from_work)

    task = orchestrator.create_task(
        title="Best effort learning",
        description="Learning failures should not fail the task.",
        team_id=team.id,
        execution_mode=TaskExecutionMode.AUTO,
    )

    asyncio.run(orchestrator.execute_task(task.id))
    stored_task = orchestrator.get_task(task.id)

    assert stored_task.status == TaskStatus.COMPLETED


def test_execute_task_broadcasts_agent_occupancy_transitions(isolated_backend, monkeypatch):
    from app.core import orchestrator as orchestrator_module
    from app.core.agent_factory import get_agent_factory
    from app.models.agent import AgentOccupancyStatus
    from app.models.task import TaskExecutionMode

    _, team, lead, specialists = _create_ready_team()
    orchestrator = orchestrator_module.Orchestrator()

    async def fake_plan(*_args, **_kwargs):
        return {
            "mode": "standalone",
            "planning_notes": "Single specialist then lead compilation.",
            "nodes": [
                {
                    "agent_id": specialists[0].id,
                    "title": "Scope A",
                    "brief": "Handle the A workstream independently.",
                    "depends_on": [],
                },
            ],
        }

    def fake_kickoff(self):
        return FakeCrewResult("result", prompt_tokens=3, completion_tokens=2)

    events = []

    async def capture(event):
        events.append(event)

    monkeypatch.setattr(orchestrator, "_plan_with_lead", fake_plan)
    monkeypatch.setattr(orchestrator_module, "get_tools_for_agent", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orchestrator_module.Crew, "kickoff", fake_kickoff)
    monkeypatch.setattr(orchestrator_module, "run_learn_from_work", lambda *_args, **_kwargs: asyncio.sleep(0, result=False))

    task = orchestrator.create_task(
        title="Occupancy transitions",
        description="Verify that agents expose assigned and busy transitions.",
        team_id=team.id,
        execution_mode=TaskExecutionMode.AUTO,
    )

    asyncio.run(orchestrator.execute_task(task.id, broadcast=capture))

    factory = get_agent_factory()
    for agent_id in task.assigned_agent_ids:
        agent = factory.get_agent(agent_id)
        assert agent is not None
        assert agent.occupancy_status == AgentOccupancyStatus.IDLE
        assert agent.current_task_id is None

    specialist_events = [
        event["data"]
        for event in events
        if event["type"] == "agent_status" and event["data"]["agent_id"] == specialists[0].id
    ]
    lead_events = [
        event["data"]
        for event in events
        if event["type"] == "agent_status" and event["data"]["agent_id"] == lead.id
    ]

    assert "assigned" in [event["occupancy_status"] for event in specialist_events]
    assert "busy" in [event["occupancy_status"] for event in specialist_events]
    assert specialist_events[-1]["occupancy_status"] == "idle"
    assert "busy" in [event["occupancy_status"] for event in lead_events]
    assert lead_events[-1]["occupancy_status"] == "idle"


def test_resolve_task_agents_excludes_occupied_agents(isolated_backend):
    from app.core.orchestrator import Orchestrator
    from app.models.agent import AgentOccupancyReason, AgentOccupancyStatus

    factory, team, lead, specialists = _create_ready_team()
    orchestrator = Orchestrator()

    factory.update_agent_occupancy(
        specialists[0].id,
        occupancy_status=AgentOccupancyStatus.BUSY,
        occupancy_reason=AgentOccupancyReason.TASK_EXECUTION,
        current_task_id="busy-task",
        current_task_title="Busy task",
        busy_since="2026-03-07T00:00:00+00:00",
    )

    task = orchestrator.create_task(
        title="Fresh task",
        description="Should avoid already occupied specialists.",
        team_id=team.id,
    )
    resolved_team, resolved_lead, resolved_specialists = orchestrator._resolve_task_agents(task, factory)

    assert resolved_team is not None
    assert resolved_lead.id == lead.id
    assert specialists[0].id not in [agent.id for agent in resolved_specialists]

    factory.update_agent_occupancy(
        lead.id,
        occupancy_status=AgentOccupancyStatus.BUSY,
        occupancy_reason=AgentOccupancyReason.TASK_EXECUTION,
        current_task_id="another-task",
        current_task_title="Another task",
        busy_since="2026-03-07T00:00:00+00:00",
    )

    blocked_task = orchestrator.create_task(
        title="Blocked task",
        description="Should fail when the lead is already occupied.",
        team_id=team.id,
    )
    with pytest.raises(ValueError, match="No usable team lead available"):
        orchestrator._resolve_task_agents(blocked_task, factory)


def test_create_task_pins_active_brief_revision(isolated_backend):
    from app.core.orchestrator import Orchestrator
    from app.memory.project_context import get_project_context_store

    ctx_store = get_project_context_store()
    state, changed = ctx_store.publish_context(
        {
            "name": "Glance",
            "description": "AI support for devices",
            "domain": "support",
            "short_term_goal": "Ship beta",
        }
    )

    orchestrator = Orchestrator()
    task = orchestrator.create_task(
        title="Pinned brief task",
        description="Verify task provenance against the active brief.",
    )

    assert changed is True
    assert state.published is not None
    assert task.brief_revision == state.published.revision
    assert task.brief_fingerprint == state.published.brief_fingerprint
