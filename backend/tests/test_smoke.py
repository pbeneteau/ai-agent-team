"""
Smoke tests — validate that the API contract is stable and the critical routes
respond correctly without requiring a live Anthropic key or Redis.

Run from the backend/ directory:
    pytest tests/test_smoke.py -v
"""
import json
import os
import pytest
from fastapi.testclient import TestClient

# Inject a fake key so Settings validation passes without a real Anthropic account.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-for-smoke")


@pytest.fixture(scope="session")
def client():
    from app.main import create_app
    with TestClient(create_app(), raise_server_exceptions=True) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

def test_list_teams_returns_list(client: TestClient):
    r = client.get("/api/teams/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_organigramme_returns_list(client: TestClient):
    r = client.get("/api/teams/organigramme")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_project_context_returns_dict(client: TestClient):
    r = client.get("/api/teams/project-context")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_project_context_supports_draft_save(client: TestClient):
    draft_payload = {
        "name": "Smoke Project",
        "description": "Draft description",
        "domain": "support",
        "short_term_goal": "Clarify positioning",
        "notes": "Still validating the ICP.",
    }
    draft = client.put("/api/teams/project-context/draft", json=draft_payload)
    assert draft.status_code == 200
    draft_body = draft.json()
    assert draft_body["ok"] is True
    assert draft_body["state"]["draft"]["status"] == "draft"
    assert draft_body["state"]["draft"]["name"] == "Smoke Project"


def test_create_team_unknown_template_returns_400(client: TestClient):
    r = client.post("/api/teams/from-template", json={"template": "nonexistent"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def test_list_agents_returns_list(client: TestClient):
    r = client.get("/api/agents/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_associate_agent_is_created_on_startup(client: TestClient):
    agents = client.get("/api/agents/").json()
    associates = [a for a in agents if a["role"] == "associate"]
    assert len(associates) == 1
    assert associates[0]["name"] == "Alex"


def test_get_unknown_agent_returns_404(client: TestClient):
    r = client.get("/api/agents/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_capabilities_returns_dict(client: TestClient):
    r = client.get("/api/agents/capabilities")
    assert r.status_code == 200
    assert "web_search" in r.json()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def test_list_tasks_returns_list(client: TestClient):
    r = client.get("/api/tasks/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_task_returns_task_object(client: TestClient):
    payload = {
        "title": "Smoke test task",
        "description": "Created by smoke tests — should not be executed.",
        "priority": "low",
        "execution_mode": "standalone",
    }
    r = client.post("/api/tasks/", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == payload["title"]
    assert body["status"] == "pending"
    assert body["execution_mode"] == "standalone"
    assert body["execution_plan"]["status"] == "not_planned"
    assert "id" in body
    # cleanup
    client.delete(f"/api/tasks/{body['id']}")


def test_get_unknown_task_returns_404(client: TestClient):
    r = client.get("/api/tasks/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_execute_unknown_task_returns_404(client: TestClient):
    r = client.post("/api/tasks/00000000-0000-0000-0000-000000000000/execute")
    assert r.status_code == 404


def test_execute_task_rejects_ineligible_task(client: TestClient):
    payload = {
        "title": "Blocked execution",
        "description": "Should require an explicit owner before execution.",
        "priority": "low",
    }
    created = client.post("/api/tasks/", json=payload)
    assert created.status_code == 200
    task_id = created.json()["id"]

    executed = client.post(f"/api/tasks/{task_id}/execute")
    assert executed.status_code == 400
    assert "équipe" in executed.json()["detail"].lower() or "agent" in executed.json()["detail"].lower()

    client.delete(f"/api/tasks/{task_id}")


def test_delete_running_task_returns_409(client: TestClient):
    from app.core.orchestrator import get_orchestrator
    from app.models.task import TaskStatus

    payload = {
        "title": "Delete guard",
        "description": "Should not delete a running task.",
        "priority": "low",
    }
    created = client.post("/api/tasks/", json=payload)
    assert created.status_code == 200
    task_id = created.json()["id"]

    task = get_orchestrator().get_task(task_id)
    assert task is not None
    task.status = TaskStatus.RUNNING

    deleted = client.delete(f"/api/tasks/{task_id}")
    assert deleted.status_code == 409
    assert "running" in deleted.json()["detail"].lower()

    task.status = TaskStatus.FAILED
    client.delete(f"/api/tasks/{task_id}")


def test_create_task_invalid_priority(client: TestClient):
    r = client.post("/api/tasks/", json={
        "title": "Bad",
        "description": "test",
        "priority": "EXTREME",
    })
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def test_list_documents_returns_list(client: TestClient):
    r = client.get("/api/documents/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_upload_unsupported_format_returns_400(client: TestClient):
    r = client.post(
        "/api/documents/",
        files={"file": ("bad.exe", b"fake", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_upload_empty_file_returns_400(client: TestClient):
    r = client.post(
        "/api/documents/",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert r.status_code == 400


def test_upload_text_document_and_delete(client: TestClient):
    content = b"Contenu de test pour le smoke test."
    r = client.post(
        "/api/documents/",
        files={"file": ("smoke.txt", content, "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "smoke.txt"
    doc_id = body["id"]

    # verify it appears in listing
    listing = client.get("/api/documents/").json()
    assert any(d["id"] == doc_id for d in listing)

    # delete
    del_r = client.delete(f"/api/documents/{doc_id}")
    assert del_r.status_code == 200
    assert del_r.json()["ok"] is True


def test_delete_unknown_document_returns_404(client: TestClient):
    r = client.delete("/api/documents/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

def test_usage_returns_summary(client: TestClient):
    r = client.get("/api/usage/")
    assert r.status_code == 200
    body = r.json()
    assert "today" in body or "total" in body or isinstance(body, dict)
