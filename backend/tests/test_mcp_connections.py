from fastapi.testclient import TestClient


def _reset_backend_caches():
    from app.config import get_settings
    from app.core import usage_tracker as usage_tracker_module
    from app.core.agent_factory import get_agent_factory
    from app.core.document_store import get_document_store
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
    get_knowledge_audit_service.cache_clear()
    get_mcp_connection_store.cache_clear()
    get_orchestrator.cache_clear()
    get_workspace_manager.cache_clear()
    get_project_context_store.cache_clear()
    get_skills_store.cache_clear()
    get_vector_store.cache_clear()
    usage_tracker_module._tracker = None


def _create_ready_agent():
    from app.core.agent_factory import get_agent_factory
    from app.models.agent import AgentStatus

    factory = get_agent_factory()
    team, agents = factory.create_custom_team(
        name="MCP Team",
        description="Tests MCP tools",
        domain="ops",
        agent_specs=[
            {
                "name": "Alexis",
                "title": "Operations Lead",
                "specialization": "operations",
                "goal": "Use external MCP tools when needed.",
                "backstory": "Coordinates operations with external systems.",
                "is_lead": True,
                "tools": [],
            }
        ],
    )
    agent = agents[0]
    factory.update_agent_status(agent.id, AgentStatus.READY)
    return team, factory.get_agent(agent.id)


def _fake_tool_descriptors():
    from app.models.mcp import McpCapabilityClass, McpToolDescriptor

    return [
        McpToolDescriptor(
            name="list_projects",
            description="List remote projects",
            input_schema={"type": "object", "properties": {}},
            read_only=True,
            capability_class=McpCapabilityClass.READ_ONLY,
        ),
        McpToolDescriptor(
            name="delete_project",
            description="Delete a remote project",
            input_schema={"type": "object", "properties": {"id": {"type": "string"}}},
            read_only=False,
            capability_class=McpCapabilityClass.WRITE,
        ),
    ]


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


def test_mcp_connection_crud_and_discovery(tmp_path, monkeypatch):
    _isolated_backend(tmp_path, monkeypatch)

    from app.core import mcp_connection_store as mcp_store_module
    from app.models.mcp import McpTestResult

    monkeypatch.setattr(
        mcp_store_module,
        "test_mcp_connection",
        lambda connection: McpTestResult(
            ok=True,
            status="healthy",
            server_name="Demo",
            server_version="1.0",
            protocol_version="2024-11-05",
            error=None,
        ),
    )
    monkeypatch.setattr(mcp_store_module, "discover_mcp_tools", lambda connection: _fake_tool_descriptors())

    from app.main import create_app

    with TestClient(create_app(), raise_server_exceptions=True) as client:
        created = client.post(
            "/api/mcp/connections",
            json={
                "name": "Linear MCP",
                "endpoint_url": "https://example.com/mcp",
                "auth_token": "Bearer secret",
                "notes": "Primary remote MCP",
            },
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["name"] == "Linear MCP"
        assert payload["has_auth_token"] is True
        connection_id = payload["id"]

        listing = client.get("/api/mcp/connections")
        assert listing.status_code == 200
        assert len(listing.json()) == 1

        tested = client.post(f"/api/mcp/connections/{connection_id}/test")
        assert tested.status_code == 200
        assert tested.json()["ok"] is True

        discovered = client.post(f"/api/mcp/connections/{connection_id}/discover-tools")
        assert discovered.status_code == 200
        assert [item["name"] for item in discovered.json()] == ["list_projects", "delete_project"]

        tools = client.get(f"/api/mcp/connections/{connection_id}/tools")
        assert tools.status_code == 200
        assert len(tools.json()) == 2

        updated = client.patch(
            f"/api/mcp/connections/{connection_id}",
            json={"notes": "Updated notes", "tool_allowlist": ["list_projects"]},
        )
        assert updated.status_code == 200
        assert updated.json()["notes"] == "Updated notes"

        filtered_tools = client.get(f"/api/mcp/connections/{connection_id}/tools")
        assert filtered_tools.status_code == 200
        assert [item["name"] for item in filtered_tools.json()] == ["list_projects"]


def test_agent_mcp_bindings_are_resolved_and_cleaned_on_delete(tmp_path, monkeypatch):
    _isolated_backend(tmp_path, monkeypatch)

    from app.core import mcp_connection_store as mcp_store_module

    monkeypatch.setattr(mcp_store_module, "discover_mcp_tools", lambda connection: _fake_tool_descriptors())

    team, agent = _create_ready_agent()
    assert team.id
    assert agent is not None

    from app.main import create_app

    with TestClient(create_app(), raise_server_exceptions=True) as client:
        created = client.post(
            "/api/mcp/connections",
            json={"name": "Demo", "endpoint_url": "https://example.com/mcp"},
        )
        connection_id = created.json()["id"]
        client.post(f"/api/mcp/connections/{connection_id}/discover-tools")

        binding_response = client.put(
            f"/api/agents/{agent.id}/mcp-tools",
            json={
                "bindings": [
                    {
                        "connection_id": connection_id,
                        "tool_name": "list_projects",
                        "enabled": True,
                        "approval_mode": "auto",
                    },
                    {
                        "connection_id": connection_id,
                        "tool_name": "delete_project",
                        "enabled": True,
                        "approval_mode": "auto",
                    },
                ]
            },
        )
        assert binding_response.status_code == 200
        resolved = binding_response.json()
        assert len(resolved) == 1
        assert resolved[0]["tool_name"] == "list_projects"
        assert resolved[0]["read_only"] is True

        agent_payload = client.get(f"/api/agents/{agent.id}")
        assert agent_payload.status_code == 200
        assert len(agent_payload.json()["mcp_tool_bindings"]) == 1

        deleted = client.delete(f"/api/mcp/connections/{connection_id}")
        assert deleted.status_code == 200

        empty_bindings = client.get(f"/api/agents/{agent.id}/mcp-tools")
        assert empty_bindings.status_code == 200
        assert empty_bindings.json() == []


def test_registry_builds_mcp_tool_and_records_usage(tmp_path, monkeypatch):
    _isolated_backend(tmp_path, monkeypatch)

    from app.core import mcp_connection_store as mcp_store_module
    from app.tools import registry as registry_module

    monkeypatch.setattr(mcp_store_module, "discover_mcp_tools", lambda connection: _fake_tool_descriptors())

    from app.main import create_app

    with TestClient(create_app(), raise_server_exceptions=True) as client:
        created = client.post(
            "/api/mcp/connections",
            json={"name": "Demo", "endpoint_url": "https://example.com/mcp"},
        )
        connection_id = created.json()["id"]
        client.post(f"/api/mcp/connections/{connection_id}/discover-tools")

    from app.models.mcp import AgentMcpToolBinding

    monkeypatch.setattr(
        registry_module,
        "call_mcp_tool",
        lambda connection, tool_name, arguments: type(
            "FakeResult",
            (),
            {"content": f"projects for {tool_name}: {arguments}", "duration_ms": 12},
        )(),
    )

    tools = registry_module.build_mcp_tools_for_agent(
        [AgentMcpToolBinding(connection_id=connection_id, tool_name="list_projects")]
    )
    assert len(tools) == 1
    result = tools[0].func(arguments_json='{"limit": 3}')
    assert "projects for list_projects" in result

    from app.core.mcp_connection_store import get_mcp_connection_store

    store = get_mcp_connection_store()
    connection = store.get_connection(connection_id)
    assert connection is not None
    assert connection.total_calls == 1
