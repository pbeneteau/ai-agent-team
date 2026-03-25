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
# Artifacts
# ---------------------------------------------------------------------------

def test_get_unknown_artifact_returns_404(client: TestClient):
    r = client.get("/api/artifacts/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_create_artifact_requires_existing_project(client: TestClient):
    r = client.post("/api/artifacts/", json={
        "project_id": "00000000-0000-0000-0000-000000000000",
        "title": "Ghost artifact",
    })
    assert r.status_code == 404
    assert "project" in r.json()["detail"].lower()


def test_iterate_unknown_artifact_returns_404(client: TestClient):
    r = client.post(
        "/api/artifacts/00000000-0000-0000-0000-000000000000/iterate",
        json={"instruction": "Make it better"},
    )
    assert r.status_code == 404


def test_diff_same_version_returns_400(client: TestClient):
    r = client.get("/api/artifacts/some-id/diff?v1=1&v2=1")
    assert r.status_code == 400
    assert "different" in r.json()["detail"].lower()


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
