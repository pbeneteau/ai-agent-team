from pathlib import Path

from fastapi.testclient import TestClient


def _reset_backend_caches():
    from app.config import get_settings
    from app.core import usage_tracker as usage_tracker_module
    from app.core.agent_factory import get_agent_factory
    from app.core.document_store import get_document_store
    from app.core.git_provider_store import get_git_provider_store
    from app.core.knowledge import get_knowledge_audit_service
    from app.core.mcp_connection_store import get_mcp_connection_store
    from app.core.orchestrator import get_orchestrator
    from app.core.workspace import get_workspace_manager
    from app.memory.project_context import get_project_context_store
    from app.memory.skills_store import get_skills_store
    from app.memory.vector_store import get_vector_store

    get_settings.cache_clear()
    get_agent_factory.cache_clear()
    get_document_store.cache_clear()
    get_git_provider_store.cache_clear()
    get_knowledge_audit_service.cache_clear()
    get_mcp_connection_store.cache_clear()
    get_orchestrator.cache_clear()
    get_workspace_manager.cache_clear()
    get_project_context_store.cache_clear()
    get_skills_store.cache_clear()
    get_vector_store.cache_clear()
    usage_tracker_module._tracker = None


def _isolated_backend(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-for-smoke")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("TEAMS_FILE", str(data_dir / "teams.json"))
    monkeypatch.setenv("WORKSPACES_DIR", str(data_dir / "workspaces"))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(data_dir / "chromadb"))
    _reset_backend_caches()
    return data_dir


def _create_ready_agent():
    from app.core.agent_factory import get_agent_factory
    from app.models.agent import AgentStatus

    factory = get_agent_factory()
    team, agents = factory.create_custom_team(
        name="Dev Team",
        description="Tests git provider tools",
        domain="engineering",
        agent_specs=[
            {
                "name": "Morgan",
                "title": "Backend Engineer",
                "specialization": "backend",
                "goal": "Ship code changes safely.",
                "backstory": "Works on repositories and opens pull requests.",
                "is_lead": True,
                "tools": [],
            }
        ],
    )
    agent = agents[0]
    factory.update_agent_status(agent.id, AgentStatus.READY)
    return team, factory.get_agent(agent.id)


def _fake_repo(full_name: str = "acme/service-api"):
    from app.models.git_providers import GitRemoteRepo

    owner, name = full_name.split("/", 1)
    return GitRemoteRepo(
        full_name=full_name,
        owner=owner,
        name=name,
        web_url=f"https://example.com/{full_name}",
        clone_url=f"https://example.com/{full_name}.git",
        default_branch="main",
    )


class _FakeGitHandler:
    def test_connection(self, connection):
        from app.models.git_providers import GitProviderTestResult

        return GitProviderTestResult(
            ok=True,
            status="healthy",
            account_name="Demo User",
            account_username="demo",
            repo_count=2,
            error=None,
        )

    def list_repos(self, connection):
        return [_fake_repo(), _fake_repo("acme/frontend-app")]

    def create_pull_request(self, connection, *, repo, title, body, source_branch, target_branch):
        from app.core.git_providers import GitProviderPullRequestResult

        return GitProviderPullRequestResult(number=12, web_url=f"{repo.web_url}/-/merge_requests/12")

    def fetch_pull_request_context(self, connection, *, repo, number=None):
        if number:
            return f"PR {number} on {repo.full_name}"
        return f"Open review requests for {repo.full_name}"


def test_git_provider_connection_crud_and_refresh(tmp_path, monkeypatch):
    _isolated_backend(tmp_path, monkeypatch)

    from app.core import git_provider_store as git_store_module
    from app.main import create_app

    monkeypatch.setattr(git_store_module, "get_provider_handler", lambda provider: _FakeGitHandler())

    with TestClient(create_app(), raise_server_exceptions=True) as client:
        created = client.post(
            "/api/git-providers/connections",
            json={
                "provider": "github",
                "name": "Main GitHub",
                "auth_token": "ghp_secret",
            },
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["provider"] == "github"
        assert payload["has_auth_token"] is True
        connection_id = payload["id"]

        tested = client.post(f"/api/git-providers/connections/{connection_id}/test")
        assert tested.status_code == 200
        assert tested.json()["ok"] is True

        refreshed = client.post(f"/api/git-providers/connections/{connection_id}/repos/refresh")
        assert refreshed.status_code == 200
        assert len(refreshed.json()) == 2

        repos = client.get(f"/api/git-providers/connections/{connection_id}/repos")
        assert repos.status_code == 200
        assert repos.json()[0]["full_name"] == "acme/service-api"

        updated = client.patch(
            f"/api/git-providers/connections/{connection_id}",
            json={"notes": "Primary engineering account"},
        )
        assert updated.status_code == 200
        assert updated.json()["notes"] == "Primary engineering account"


def test_agent_git_bindings_resolve_and_cleanup(tmp_path, monkeypatch):
    _isolated_backend(tmp_path, monkeypatch)

    from app.core import git_provider_store as git_store_module
    from app.main import create_app

    monkeypatch.setattr(git_store_module, "get_provider_handler", lambda provider: _FakeGitHandler())

    _, agent = _create_ready_agent()
    assert agent is not None

    with TestClient(create_app(), raise_server_exceptions=True) as client:
        created = client.post(
            "/api/git-providers/connections",
            json={"provider": "github", "name": "Main GitHub", "auth_token": "ghp_secret"},
        )
        connection_id = created.json()["id"]
        client.post(f"/api/git-providers/connections/{connection_id}/repos/refresh")

        binding_response = client.put(
            f"/api/agents/{agent.id}/git-bindings",
            json={
                "bindings": [
                    {
                        "connection_id": connection_id,
                        "repo_full_name": "acme/service-api",
                        "enabled": True,
                        "can_push": True,
                        "can_open_pr": True,
                        "branch_prefix": "backend",
                    }
                ]
            },
        )
        assert binding_response.status_code == 200
        resolved = binding_response.json()
        assert len(resolved) == 1
        assert resolved[0]["repo_full_name"] == "acme/service-api"
        assert resolved[0]["can_push"] is True

        agent_payload = client.get(f"/api/agents/{agent.id}")
        assert agent_payload.status_code == 200
        assert len(agent_payload.json()["git_bindings"]) == 1

        deleted = client.delete(f"/api/git-providers/connections/{connection_id}")
        assert deleted.status_code == 200
        bindings = client.get(f"/api/agents/{agent.id}/git-bindings")
        assert bindings.status_code == 200
        assert bindings.json() == []


def test_registry_builds_git_tools_and_records_usage(tmp_path, monkeypatch):
    _isolated_backend(tmp_path, monkeypatch)

    from app.core import git_provider_store as git_store_module
    from app.main import create_app
    from app.tools import registry as registry_module

    monkeypatch.setattr(git_store_module, "get_provider_handler", lambda provider: _FakeGitHandler())

    with TestClient(create_app(), raise_server_exceptions=True) as client:
        created = client.post(
            "/api/git-providers/connections",
            json={"provider": "github", "name": "Main GitHub", "auth_token": "ghp_secret"},
        )
        connection_id = created.json()["id"]
        client.post(f"/api/git-providers/connections/{connection_id}/repos/refresh")

    from app.models.git_providers import AgentGitBinding

    monkeypatch.setattr(registry_module, "ensure_repo_cloned", lambda *args, **kwargs: Path("/tmp/repo"))
    monkeypatch.setattr(registry_module, "create_or_switch_branch", lambda *args, **kwargs: "backend/fix-issue")
    monkeypatch.setattr(registry_module, "commit_and_push_changes", lambda *args, **kwargs: "Pushed branch backend/fix-issue.")
    monkeypatch.setattr(registry_module, "create_pull_request", lambda *args, **kwargs: "Created review request #12: https://example.com/pr/12")
    monkeypatch.setattr(registry_module, "fetch_pull_request_context", lambda *args, **kwargs: "Open review requests for acme/service-api")

    tools = registry_module.build_git_tools_for_agent(
        [
            AgentGitBinding(
                connection_id=connection_id,
                repo_full_name="acme/service-api",
                can_push=True,
                can_open_pr=True,
                branch_prefix="backend",
            )
        ],
        workspace_path="/tmp/workspace",
        allow_write=True,
    )
    tool_names = sorted(tool.name for tool in tools)
    assert tool_names == [
        "repo_branch__acme_service_api",
        "repo_clone__acme_service_api",
        "repo_commit_push__acme_service_api",
        "repo_open_pr__acme_service_api",
        "repo_pr_context__acme_service_api",
    ]

    outputs = {tool.name: tool for tool in tools}
    assert "Repository available at" in outputs["repo_clone__acme_service_api"].executor()
    assert "backend/fix-issue" in outputs["repo_branch__acme_service_api"].executor("backend/fix-issue")
    assert "Pushed branch" in outputs["repo_commit_push__acme_service_api"].executor("Ship fix", "backend/fix-issue")
    assert "Created review request" in outputs["repo_open_pr__acme_service_api"].executor("Fix issue", "backend/fix-issue")

    from app.core.git_provider_store import get_git_provider_store

    store = get_git_provider_store()
    connection = store.get_connection(connection_id)
    assert connection is not None
    assert connection.total_repo_actions == 3
    assert connection.clone_actions == 1
    assert connection.push_actions == 1
    assert connection.pull_request_actions == 1
