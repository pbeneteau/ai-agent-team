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
    return TestClient(create_app(), raise_server_exceptions=True)


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
    }
    r = client.post("/api/tasks/", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == payload["title"]
    assert body["status"] == "pending"
    assert "id" in body
    # cleanup
    client.delete(f"/api/tasks/{body['id']}")


def test_get_unknown_task_returns_404(client: TestClient):
    r = client.get("/api/tasks/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


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
