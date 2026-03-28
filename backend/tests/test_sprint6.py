"""Tests for Sprint 6 — API Routes Core.

Verify sections for Tickets 6.1 through 6.5.
Uses FastAPI TestClient with dependency overrides.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.workspace_id import get_workspace_id
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Shared mock DB session
# ---------------------------------------------------------------------------


def _override_workspace_id():
    async def _ws():
        return "1"
    return _ws


def _make_mock_db():
    """Create an AsyncMock that works as a FastAPI dependency."""
    mock = AsyncMock()
    mock.add = MagicMock()
    mock.flush = AsyncMock()
    mock.delete = AsyncMock()
    mock.commit = AsyncMock()
    mock.rollback = AsyncMock()
    return mock


def _override_db(mock_db):
    async def _db():
        yield mock_db
    return _db


# ---------------------------------------------------------------------------
# Ticket 6.1 — Onboarding
# ---------------------------------------------------------------------------


class TestOnboarding:
    """6.1 Verify: POST creates agents, returns 201. Second POST returns 409."""

    def test_onboarding_returns_201(self) -> None:
        mock_db = _make_mock_db()
        ws = MagicMock()
        ws.id = "1"
        ws.name = "Old Name"
        ws.onboarding_completed = False
        ws.domain_description = None
        ws.tech_stack = None

        mock_db.get = AsyncMock(return_value=ws)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            with patch(
                "app.api.routes.onboarding._generate_roster",
                new_callable=AsyncMock,
                return_value=[
                    {"name": "Dev Agent", "specialization": "Full-Stack Dev"},
                ],
            ), patch(
                "app.core.celery_app.execute_agent_learning",
            ) as mock_learn:
                mock_learn.delay = MagicMock()
                resp = client.post("/api/onboarding", json={
                    "company_name": "Test Corp",
                    "domain_description": "B2B SaaS",
                    "use_case": "both",
                })
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert "workspace" in data
        assert "agents" in data
        assert data["workspace"]["onboarding_completed"] is True
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "Dev Agent"
        assert data["agents"][0]["status"] == "learning"

    def test_onboarding_409_if_already_done(self) -> None:
        mock_db = _make_mock_db()
        ws = MagicMock()
        ws.id = "1"
        ws.onboarding_completed = True

        mock_db.get = AsyncMock(return_value=ws)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            resp = client.post("/api/onboarding", json={
                "company_name": "Test Corp",
                "domain_description": "B2B SaaS",
                "use_case": "both",
            })
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Ticket 6.2 — Roster CRUD
# ---------------------------------------------------------------------------


class TestRosterCRUD:
    """6.2 Verify: CRUD lifecycle and cursor pagination."""

    def test_create_agent_returns_201(self) -> None:
        mock_db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            with patch(
                "app.core.celery_app.execute_agent_learning",
            ) as mock_learn:
                mock_learn.delay = MagicMock()
                resp = client.post("/api/roster", json={
                    "name": "Test Agent",
                    "specialization": "Testing",
                })
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Agent"
        assert data["status"] == "learning"

    def test_list_agents_returns_200(self) -> None:
        mock_db = _make_mock_db()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_db.execute = AsyncMock(return_value=mock_result)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            resp = client.get("/api/roster")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "has_more" in data
        assert "next_cursor" in data


# ---------------------------------------------------------------------------
# Ticket 6.3 — Projects + Brief + Documents
# ---------------------------------------------------------------------------


class TestProjects:
    """6.3 Verify: project lifecycle and brief publishing."""

    def test_create_project_returns_201(self) -> None:
        mock_db = _make_mock_db()

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            resp = client.post("/api/projects", json={
                "name": "Test Project",
                "description": "A test project",
            })
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Project"

    def test_delete_requires_confirm_header(self) -> None:
        mock_db = _make_mock_db()
        project = MagicMock()
        project.id = "proj-1"
        project.workspace_id = "1"
        mock_db.get = AsyncMock(return_value=project)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            resp = client.delete("/api/projects/proj-1")
            assert resp.status_code == 400

            resp2 = client.delete(
                "/api/projects/proj-1",
                headers={"X-Confirm-Delete": "true"},
            )
            assert resp2.status_code == 204
        finally:
            app.dependency_overrides.clear()

    def test_brief_fingerprint(self) -> None:
        """Publishing computes SHA-256 fingerprint and triggers rebriefing."""
        mock_db = _make_mock_db()
        project = MagicMock()
        project.id = "proj-1"
        project.workspace_id = "1"
        project.brief_draft = "This is the brief content."
        project.brief_published = None
        project.brief_fingerprint = None
        project.brief_published_at = None
        mock_db.get = AsyncMock(return_value=project)

        expected_hash = hashlib.sha256(b"This is the brief content.").hexdigest()

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            with patch(
                "app.agents.briefing.brief_all_agents",
                new_callable=AsyncMock,
                return_value=5,
            ):
                resp = client.post("/api/projects/proj-1/context/publish")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["fingerprint"] == expected_hash
        assert data["agents_rebriefed"] == 5


# ---------------------------------------------------------------------------
# Ticket 6.4 — Document processing
# ---------------------------------------------------------------------------

from app.agents.document_processor import (
    chunk_text,
    extract_text,
)


class TestDocumentProcessing:
    """6.4 Verify: text extraction and chunking."""

    def test_extract_plain_text(self) -> None:
        content = b"Hello world, this is a test document."
        result = extract_text(content, "text/plain", "test.txt")
        assert "Hello world" in result

    def test_extract_markdown(self) -> None:
        content = b"# Header\n\nSome **bold** text."
        result = extract_text(content, "text/markdown", "test.md")
        assert "# Header" in result

    def test_chunk_text_basic(self) -> None:
        text = " ".join(["word"] * 2000)
        chunks = chunk_text(text)
        assert len(chunks) > 1
        assert all(len(c) > 0 for c in chunks)

    def test_chunk_text_short(self) -> None:
        text = "A short sentence."
        chunks = chunk_text(text)
        assert len(chunks) == 1

    def test_chunk_text_empty(self) -> None:
        assert chunk_text("") == []

    def test_chunk_overlap(self) -> None:
        text = " ".join(["word"] * 2000)
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) > 2


# ---------------------------------------------------------------------------
# Ticket 6.5 — Artifact lifecycle
# ---------------------------------------------------------------------------


class TestArtifactLifecycle:
    """6.5 Verify: artifact create, validate, delegate, status, approve, cancel."""

    def test_create_artifact_returns_201(self) -> None:
        mock_db = _make_mock_db()
        project = MagicMock()
        project.id = "proj-1"
        project.workspace_id = "1"
        mock_db.get = AsyncMock(return_value=project)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            resp = client.post("/api/artifacts", json={
                "project_id": "proj-1",
                "artifact_type": "prose",
                "title": "Test Artifact",
                "description": "Build something",
            })
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Artifact"
        assert data["status"] == "drafting"

    def test_validate_calls_sufficiency(self) -> None:
        from app.agents.sufficiency import SufficiencyResult, SufficiencyIssue

        mock_db = _make_mock_db()
        artifact = MagicMock()
        artifact.id = "art-1"
        artifact.project_id = "proj-1"
        workspace = MagicMock()
        workspace.tech_stack = "Python"

        mock_db.get = AsyncMock(side_effect=lambda model, id: artifact if id == "art-1" else workspace)

        mock_result = SufficiencyResult(
            eligible=True,
            score=85,
            issues=[
                SufficiencyIssue(
                    severity="warning", field="description",
                    matched_text="test", issue="Minor", suggestion="Fix",
                )
            ],
        )

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            with patch(
                "app.agents.sufficiency.run_sufficiency_check",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                resp = client.post("/api/artifacts/art-1/validate")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["eligible"] is True
        assert len(data["issues"]) == 1

    def test_cancel_sets_cancelled(self) -> None:
        mock_db = _make_mock_db()
        artifact = MagicMock()
        artifact.id = "art-1"
        artifact.status = "in_review"
        artifact.cancelled_at = None

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        mock_exec = MagicMock()
        mock_exec.scalars = MagicMock(return_value=mock_scalars)
        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=mock_exec)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            resp = client.patch("/api/artifacts/art-1/cancel")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"

    def test_cancel_already_approved_returns_400(self) -> None:
        mock_db = _make_mock_db()
        artifact = MagicMock()
        artifact.id = "art-1"
        artifact.status = "approved"
        mock_db.get = AsyncMock(return_value=artifact)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            resp = client.patch("/api/artifacts/art-1/cancel")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400

    def test_standalone_sufficiency_check(self) -> None:
        from app.agents.sufficiency import SufficiencyResult

        mock_db = _make_mock_db()
        workspace = MagicMock()
        workspace.tech_stack = None
        mock_db.get = AsyncMock(return_value=workspace)

        mock_result = SufficiencyResult(eligible=True, score=90, issues=[])

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            with patch(
                "app.agents.sufficiency.run_sufficiency_check",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                resp = client.post("/api/briefs/sufficiency-check", json={
                    "artifact_type": "prose",
                    "title": "Test Brief",
                    "description": "A clear brief.",
                })
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["eligible"] is True

    def test_iterate_requires_in_review(self) -> None:
        mock_db = _make_mock_db()
        artifact = MagicMock()
        artifact.id = "art-1"
        artifact.status = "drafting"
        mock_db.get = AsyncMock(return_value=artifact)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            resp = client.post("/api/artifacts/art-1/iterate", json={
                "instruction": "Change this.",
            })
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400

    def test_approve_requires_in_review(self) -> None:
        mock_db = _make_mock_db()
        artifact = MagicMock()
        artifact.id = "art-1"
        artifact.status = "drafting"
        mock_db.get = AsyncMock(return_value=artifact)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        try:
            resp = client.patch("/api/artifacts/art-1/approve")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_onboarding_use_case_enum(self) -> None:
        from app.api.schemas.onboarding import OnboardingRequest
        with pytest.raises(Exception):
            OnboardingRequest(
                company_name="Test",
                domain_description="B2B",
                use_case="invalid",
            )

    def test_artifact_type_enum(self) -> None:
        from app.api.schemas.artifacts import CreateArtifactRequest
        with pytest.raises(Exception):
            CreateArtifactRequest(
                project_id="test", artifact_type="invalid",
                title="Test", description="Test",
            )


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    def test_endpoint_count(self) -> None:
        routes = [r for r in app.routes if hasattr(r, 'path') and r.path.startswith('/api')]
        assert len(routes) >= 37

    def test_key_endpoints_exist(self) -> None:
        route_paths = {r.path for r in app.routes if hasattr(r, 'path')}
        expected = [
            "/health",
            "/api/onboarding",
            "/api/roster",
            "/api/roster/{agent_id}",
            "/api/roster/{agent_id}/skills",
            "/api/roster/{agent_id}/learning-profile",
            "/api/roster/readiness/global",
            "/api/projects",
            "/api/projects/{project_id}",
            "/api/projects/{project_id}/context",
            "/api/projects/{project_id}/context/draft",
            "/api/projects/{project_id}/context/publish",
            "/api/projects/{project_id}/documents",
            "/api/projects/{project_id}/artifacts",
            "/api/artifacts",
            "/api/artifacts/{artifact_id}",
            "/api/artifacts/{artifact_id}/validate",
            "/api/artifacts/{artifact_id}/delegate",
            "/api/artifacts/{artifact_id}/status",
            "/api/artifacts/{artifact_id}/versions",
            "/api/artifacts/{artifact_id}/versions/{version_number}/files/{file_path:path}",
            "/api/artifacts/{artifact_id}/iterate",
            "/api/artifacts/{artifact_id}/approve",
            "/api/artifacts/{artifact_id}/cancel",
            "/api/briefs/sufficiency-check",
        ]
        for path in expected:
            assert path in route_paths, f"Missing route: {path}"
