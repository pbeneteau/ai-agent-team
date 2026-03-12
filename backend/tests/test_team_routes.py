import pytest
from fastapi import BackgroundTasks

from app.api.routes import teams as teams_route_module
from app.api.routes.teams import CreateCustomTeamRequest, CreateTeamFromTemplateRequest
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


@pytest.fixture()
def isolated_backend(tmp_path, monkeypatch):
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


def test_create_team_from_template_schedules_learning(isolated_backend):
    background_tasks = BackgroundTasks()

    response = teams_route_module.create_team_from_template(
        CreateTeamFromTemplateRequest(template="dev"),
        background_tasks,
    )

    assert response.id
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is teams_route_module.run_learning_phase_for_team
    assert task.args == (response.id,)


def test_create_custom_team_schedules_learning(isolated_backend):
    background_tasks = BackgroundTasks()

    response = teams_route_module.create_custom_team(
        CreateCustomTeamRequest(
            name="Fundraising",
            description="Prepare the pre-seed raise.",
            domain="finance",
            agents=[
                {
                    "name": "Sophie",
                    "title": "Fundraising Lead",
                    "specialization": "fundraising",
                    "goal": "Lead the pre-seed process.",
                    "backstory": "Raised multiple early-stage rounds.",
                    "is_lead": True,
                    "model_tier": "sonnet",
                }
            ],
        ),
        background_tasks,
    )

    assert response.id
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is teams_route_module.run_learning_phase_for_team
    assert task.args == (response.id,)


def test_reset_recreates_associate_agent(isolated_backend):
    factory = get_agent_factory()
    associate = factory.get_or_create_associate()

    factory.reset()

    recreated = factory.get_associate()
    assert recreated is not None
    assert recreated.role.value == "associate"
    assert recreated.name == "Alex"
    assert recreated.id != associate.id


def test_get_organigramme_ensures_associate_root(isolated_backend):
    factory = get_agent_factory()
    factory.reset()
    factory._agents = {
        agent_id: agent
        for agent_id, agent in factory._agents.items()
        if agent.role.value != "associate"
    }
    factory._save()

    background_tasks = BackgroundTasks()
    teams_route_module.create_custom_team(
        CreateCustomTeamRequest(
            name="Fundraising",
            description="Prepare the pre-seed raise.",
            domain="finance",
            agents=[
                {
                    "name": "Sophie",
                    "title": "Fundraising Lead",
                    "specialization": "fundraising",
                    "goal": "Lead the pre-seed process.",
                    "backstory": "Raised multiple early-stage rounds.",
                    "is_lead": True,
                    "model_tier": "sonnet",
                }
            ],
        ),
        background_tasks,
    )

    roots = teams_route_module.get_organigramme()

    assert len(roots) == 1
    assert roots[0].role == "associate"
    assert roots[0].name == "Alex"
    assert len(roots[0].children) == 1
    assert roots[0].children[0].name == "Sophie"
