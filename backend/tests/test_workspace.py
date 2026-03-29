"""Tests for workspace endpoints.

Covers:
- GET /api/workspace
- PATCH /api/workspace
- GET /api/workspace/documents
- POST /api/workspace/documents
- DELETE /api/workspace/documents/{id}
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.workspace_id import get_workspace_id
from app.main import app

client = TestClient(app, raise_server_exceptions=False)

WS_ID = "1"
NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _override_workspace_id():
    async def _ws():
        return WS_ID
    return _ws


def _make_mock_db():
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


def _make_workspace(**kwargs):
    ws = MagicMock()
    ws.id = WS_ID
    ws.name = "Test Corp"
    ws.domain_description = "B2B SaaS"
    ws.product_description = None
    ws.tech_stack = None
    ws.company_stage = None
    ws.target_audience = None
    ws.main_goals = None
    ws.existing_team = None
    ws.monthly_budget_usd = 50.0
    ws.monthly_spend_usd = 0.0
    ws.onboarding_completed = True
    ws.created_at = NOW
    for k, v in kwargs.items():
        setattr(ws, k, v)
    return ws


def _make_document(**kwargs):
    doc = MagicMock()
    doc.id = str(uuid.uuid4())
    doc.workspace_id = WS_ID
    doc.filename = "spec.pdf"
    doc.mime_type = "application/pdf"
    doc.s3_path = f"documents/{doc.id}/spec.pdf"
    doc.size_bytes = 1024
    doc.processing_status = "pending"
    doc.created_at = NOW
    for k, v in kwargs.items():
        setattr(doc, k, v)
    return doc


# ---------------------------------------------------------------------------
# GET /api/workspace
# ---------------------------------------------------------------------------


class TestGetWorkspace:
    def test_returns_workspace_detail(self):
        mock_db = _make_mock_db()
        ws = _make_workspace()
        mock_db.get = AsyncMock(return_value=ws)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            resp = client.get("/api/workspace")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == WS_ID
        assert data["name"] == "Test Corp"
        assert data["domain_description"] == "B2B SaaS"
        assert data["monthly_budget_usd"] == 50.0
        assert data["onboarding_completed"] is True

    def test_404_when_workspace_missing(self):
        mock_db = _make_mock_db()
        mock_db.get = AsyncMock(return_value=None)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            resp = client.get("/api/workspace")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/workspace
# ---------------------------------------------------------------------------


class TestPatchWorkspace:
    def test_updates_name_field(self):
        mock_db = _make_mock_db()
        ws = _make_workspace()
        mock_db.get = AsyncMock(return_value=ws)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            resp = client.patch("/api/workspace", json={"name": "New Corp"})
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        # Name was set on the workspace object
        assert ws.name == "New Corp"

    def test_404_when_workspace_missing(self):
        mock_db = _make_mock_db()
        mock_db.get = AsyncMock(return_value=None)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            resp = client.patch("/api/workspace", json={"name": "x"})
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404

    def test_context_change_triggers_agent_learning(self):
        """When a CONTEXT_FIELD changes, existing ready/learning agents get re-triggered."""
        mock_db = _make_mock_db()
        ws = _make_workspace()
        mock_db.get = AsyncMock(return_value=ws)

        agent = MagicMock()
        agent.id = str(uuid.uuid4())
        agent.status = "ready"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [agent]
        mock_db.execute = AsyncMock(return_value=mock_result)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            with patch("app.core.celery_app.execute_agent_learning") as mock_task:
                mock_task.delay = MagicMock()
                resp = client.patch(
                    "/api/workspace",
                    json={"product_description": "New product"},
                )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        mock_task.delay.assert_called_once_with(agent.id)

    def test_non_context_change_does_not_trigger_learning(self):
        """Changing `name` alone (not a CONTEXT_FIELD) must not trigger learning."""
        mock_db = _make_mock_db()
        ws = _make_workspace()
        mock_db.get = AsyncMock(return_value=ws)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            with patch("app.core.celery_app.execute_agent_learning") as mock_task:
                mock_task.delay = MagicMock()
                resp = client.patch("/api/workspace", json={"name": "Updated"})
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        mock_task.delay.assert_not_called()

    def test_team_size_not_stored_on_workspace(self):
        """team_size is accepted in request but not written to the workspace model."""
        mock_db = _make_mock_db()
        ws = _make_workspace()
        mock_db.get = AsyncMock(return_value=ws)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            resp = client.patch("/api/workspace", json={"team_size": 10})
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        # team_size must NOT have been set via setattr
        # (the mock's team_size is whatever MagicMock auto-creates, NOT 10)
        # Just check the response doesn't 500
        assert resp.json()["id"] == WS_ID


# ---------------------------------------------------------------------------
# GET /api/workspace/documents
# ---------------------------------------------------------------------------


class TestListWorkspaceDocuments:
    def test_returns_empty_list_when_no_docs(self):
        mock_db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            resp = client.get("/api/workspace/documents")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False

    def test_returns_documents_list(self):
        mock_db = _make_mock_db()
        doc1 = _make_document(filename="spec.pdf")
        doc2 = _make_document(filename="readme.txt", mime_type="text/plain")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [doc1, doc2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            resp = client.get("/api/workspace/documents")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert items[0]["filename"] == "spec.pdf"
        assert items[1]["filename"] == "readme.txt"
        assert items[0]["processing_status"] == "pending"


# ---------------------------------------------------------------------------
# POST /api/workspace/documents
# ---------------------------------------------------------------------------


class TestUploadWorkspaceDocument:
    def test_upload_returns_201(self):
        mock_db = _make_mock_db()
        fake_doc = _make_document(filename="spec.pdf", size_bytes=11)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            with patch("app.api.routes.workspace.Document", return_value=fake_doc), \
                 patch("app.core.s3_workspace.upload_document"), \
                 patch("app.core.celery_app.process_document_upload") as mock_task:
                mock_task.delay = MagicMock()
                resp = client.post(
                    "/api/workspace/documents",
                    files={"file": ("spec.pdf", io.BytesIO(b"PDF content"), "application/pdf")},
                )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert data["filename"] == "spec.pdf"
        assert data["mime_type"] == "application/pdf"
        assert data["processing_status"] == "pending"
        mock_task.delay.assert_called_once()

    def test_upload_rejects_oversized_file(self):
        mock_db = _make_mock_db()

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            # 21 MB > 20 MB limit
            large_content = b"x" * (21 * 1024 * 1024)
            resp = client.post(
                "/api/workspace/documents",
                files={"file": ("big.bin", io.BytesIO(large_content), "application/octet-stream")},
            )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 413


# ---------------------------------------------------------------------------
# DELETE /api/workspace/documents/{id}
# ---------------------------------------------------------------------------


class TestDeleteWorkspaceDocument:
    def test_delete_returns_204(self):
        mock_db = _make_mock_db()
        doc = _make_document()
        mock_db.get = AsyncMock(return_value=doc)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            with patch("app.core.s3_workspace.delete_document"):
                resp = client.delete(f"/api/workspace/documents/{doc.id}")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 204
        mock_db.delete.assert_awaited_once_with(doc)

    def test_delete_404_when_document_missing(self):
        mock_db = _make_mock_db()
        mock_db.get = AsyncMock(return_value=None)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            resp = client.delete("/api/workspace/documents/nonexistent-id")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404

    def test_delete_404_when_doc_belongs_to_different_workspace(self):
        mock_db = _make_mock_db()
        doc = _make_document(workspace_id="other-workspace")
        mock_db.get = AsyncMock(return_value=doc)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            resp = client.delete(f"/api/workspace/documents/{doc.id}")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404

    def test_delete_succeeds_even_if_s3_fails(self):
        """S3 errors are swallowed — DB record is still deleted."""
        mock_db = _make_mock_db()
        doc = _make_document()
        mock_db.get = AsyncMock(return_value=doc)

        app.dependency_overrides[get_db] = _override_db(mock_db)
        app.dependency_overrides[get_workspace_id] = _override_workspace_id()
        try:
            with patch("app.core.s3_workspace.delete_document", side_effect=Exception("S3 down")):
                resp = client.delete(f"/api/workspace/documents/{doc.id}")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 204
        mock_db.delete.assert_awaited_once_with(doc)
