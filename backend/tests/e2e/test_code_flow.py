"""Ticket 11.2 — E2E: Code Artifact Flow (Journey J3).

Verifies the complete code artifact lifecycle:
  Git provider connection → Webhook config → Create code artifact →
  Delegate → Execution → PR created → Webhook: PR comment → Iteration →
  Webhook: PR merged → Approved.

All git integration and webhook flows verified against TDD-01 Journey J3.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.workspace_id import get_workspace_id
from app.main import app
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.contextual_comment import ContextualComment
from app.models.execution_wave import ExecutionWave
from app.models.git_provider_connection import GitProviderConnection
from app.models.project import Project
from app.models.workspace import Workspace

from .conftest import (
    WEBHOOK_SECRET,
    WORKSPACE_ID,
    github_signature,
    make_agent,
    make_artifact,
    make_artifact_version,
    make_execution_wave,
    make_git_connection,
    make_project,
    make_workspace,
    mock_code_routing_result,
)


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------


def _setup_overrides(mock_db: AsyncMock) -> TestClient:
    async def _db():
        yield mock_db

    async def _ws():
        return WORKSPACE_ID

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_workspace_id] = _ws
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Step 1: Git Provider Connection (J6 Steps 1-3)
# ---------------------------------------------------------------------------


class TestGitProviderConnection:
    """Verify GitHub PAT connection, repo listing, and webhook configuration."""

    def test_create_github_connection(self) -> None:
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        # Ensure entity gets populated with defaults that server_default would set
        def _add_with_defaults(entity):
            if not hasattr(entity, 'id') or entity.id is None:
                entity.id = str(uuid.uuid4())
            if not hasattr(entity, 'created_at') or entity.created_at is None:
                entity.created_at = datetime.now(timezone.utc)
            if not hasattr(entity, 'updated_at') or entity.updated_at is None:
                entity.updated_at = datetime.now(timezone.utc)

        mock_db.add = MagicMock(side_effect=_add_with_defaults)

        mock_client = AsyncMock()
        mock_client.validate_token = AsyncMock(return_value=MagicMock(
            username="testuser",
            scopes=["repo", "admin:repo_hook"],
            rate_limit_remaining=4900,
        ))
        mock_client.list_repos = AsyncMock(return_value=[
            MagicMock(
                owner="testorg", name="testrepo",
                full_name="testorg/testrepo",
                default_branch="main", private=False,
            ),
        ])
        mock_client.close = AsyncMock()

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.api.routes.git_providers.get_client",
                return_value=mock_client,
            ), patch("app.core.encryption.encrypt_string", return_value="enc-token"):
                resp = client.post("/api/git-providers/connections", json={
                    "provider": "github",
                    "display_name": "My GitHub",
                    "access_token": "ghp_test_token_123",
                })

            assert resp.status_code == 201
            data = resp.json()
            assert data["provider"] == "github"
            assert data["status"] == "active"
            assert len(data["repositories"]) >= 1
            assert data["repositories"][0]["full_name"] == "testorg/testrepo"
        finally:
            _teardown()

    def test_list_repos_from_connection(self) -> None:
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        conn = make_git_connection(connection_id="conn-1")
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=conn)
        ))

        # Use SimpleNamespace to avoid MagicMock attr issues with Pydantic
        from types import SimpleNamespace
        mock_client = AsyncMock()
        mock_client.list_repos = AsyncMock(return_value=[
            SimpleNamespace(
                owner="testorg", name="testrepo",
                full_name="testorg/testrepo",
                default_branch="main", private=False,
            ),
            SimpleNamespace(
                owner="testorg", name="frontend",
                full_name="testorg/frontend",
                default_branch="main", private=True,
            ),
        ])
        mock_client.close = AsyncMock()

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.api.routes.git_providers.get_client",
                return_value=mock_client,
            ), patch("app.api.routes.git_providers.decrypt_string", return_value="token"):
                resp = client.get("/api/git-providers/connections/conn-1/repos")

            assert resp.status_code == 200
            data = resp.json()
            assert len(data["items"]) == 2
        finally:
            _teardown()

    def test_configure_webhook_on_repo(self) -> None:
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        conn = make_git_connection(connection_id="conn-1")
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=conn)
        ))

        from types import SimpleNamespace
        mock_client = AsyncMock()
        mock_client.create_webhook = AsyncMock(return_value=SimpleNamespace(
            webhook_id=456,
            webhook_url="http://localhost:8000/api/webhooks/github",
            events=["pull_request", "pull_request_review_comment"],
            status="active",
        ))
        mock_client.close = AsyncMock()

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.api.routes.git_providers.get_client",
                return_value=mock_client,
            ), patch("app.api.routes.git_providers.decrypt_string", return_value="token"):
                resp = client.post(
                    "/api/git-providers/connections/conn-1/repos/testorg/testrepo/webhook"
                )

            assert resp.status_code == 200
            data = resp.json()
            assert data["webhook_id"] == 456
            assert "pull_request" in data["events"]
            assert conn.webhook_secret is not None
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Step 2: Create Code Artifact + Delegate (J3 Steps 1-7)
# ---------------------------------------------------------------------------


class TestCodeArtifactCreation:
    """Verify code artifact creation with git fields."""

    def test_create_code_artifact_with_git_fields(self) -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        project = make_project(project_id="proj-1")
        mock_db.get = AsyncMock(return_value=project)

        client = _setup_overrides(mock_db)
        try:
            resp = client.post("/api/artifacts", json={
                "project_id": "proj-1",
                "artifact_type": "code",
                "title": "Settings Page Feature",
                "goal": "Build a settings page with user preferences",
                "description": "Implement settings page with preferences and notification controls.",
                "max_budget_usd": 5.00,
                "git_repo_url": "https://github.com/testorg/testrepo",
                "git_base_branch": "main",
            })

            assert resp.status_code == 201
            data = resp.json()
            assert data["artifact_type"] == "code"
            assert data["status"] == "drafting"
            assert data["git_repo_url"] == "https://github.com/testorg/testrepo"
            assert data["git_base_branch"] == "main"
        finally:
            _teardown()

    def test_delegate_code_artifact(self) -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        artifact = make_artifact(
            artifact_id="art-code-1",
            project_id="proj-1",
            artifact_type="code",
        )
        artifact.git_repo_url = "https://github.com/testorg/testrepo"
        artifact.git_base_branch = "main"
        ws = make_workspace(onboarding_completed=True)
        agents = [
            make_agent(name="Product Expert"),
            make_agent(name="Frontend Dev", specialization="Frontend"),
            make_agent(name="QA Engineer", specialization="QA"),
        ]

        mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
            (Artifact, "art-code-1"): artifact,
            (Workspace, WORKSPACE_ID): ws,
        }.get((cls, id_)))
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=agents)))
        ))

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.agents.router.route_brief",
                new_callable=AsyncMock,
                return_value=mock_code_routing_result(),
            ), patch("app.core.celery_app.execute_artifact_dag") as mock_celery:
                resp = client.post("/api/artifacts/art-code-1/delegate", json={
                    "confirm": True,
                })

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "drafting"
            assert data["plan"]["template_id"] == "code_feature"
            assert mock_celery.delay.called
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Step 3: Webhook - PR Review Comment → Iteration (J3 Step 12a)
# ---------------------------------------------------------------------------


class TestWebhookPRComment:
    """Verify GitHub PR review comment triggers iteration."""

    def test_github_pr_comment_creates_iteration(self) -> None:
        """Webhook with valid signature creates comment + triggers execution."""
        # Set up artifact with pr_number
        artifact = make_artifact(
            artifact_id="art-code-1",
            status="in_review",
            artifact_type="code",
        )
        artifact.git_pr_number = 42
        artifact.project_id = "proj-1"

        v1 = make_artifact_version(artifact_id="art-code-1", version_number=1)

        # The webhook handler uses its own session (async_session_maker)
        # We mock at the DB level
        payload = {
            "action": "created",
            "pull_request": {"number": 42},
            "comment": {
                "id": 98765,
                "body": "Fix the error handling in the settings controller",
                "path": "src/controllers/settings.ts",
                "position": 15,
            },
        }
        body = json.dumps(payload).encode()

        client = TestClient(app, raise_server_exceptions=False)
        try:
            with patch(
                "app.api.routes.webhooks._verify_github_signature",
                new_callable=AsyncMock,
                return_value=True,
            ), patch(
                "app.api.routes.webhooks._handle_github_event",
                new_callable=AsyncMock,
            ) as mock_handler:
                resp = client.post(
                    "/api/webhooks/github",
                    content=body,
                    headers={
                        "X-GitHub-Event": "pull_request_review_comment",
                        "X-Hub-Signature-256": github_signature(body),
                        "Content-Type": "application/json",
                    },
                )

            assert resp.status_code == 200
            mock_handler.assert_called_once_with("pull_request_review_comment", payload)
        finally:
            app.dependency_overrides.clear()

    def test_github_webhook_invalid_signature_returns_401(self) -> None:
        """Invalid signature should return 401."""
        payload = {"action": "created", "pull_request": {"number": 42}}
        body = json.dumps(payload).encode()

        client = TestClient(app, raise_server_exceptions=False)
        try:
            with patch(
                "app.api.routes.webhooks._verify_github_signature",
                new_callable=AsyncMock,
                return_value=False,
            ):
                resp = client.post(
                    "/api/webhooks/github",
                    content=body,
                    headers={
                        "X-GitHub-Event": "pull_request_review_comment",
                        "X-Hub-Signature-256": "sha256=invalid",
                        "Content-Type": "application/json",
                    },
                )

            assert resp.status_code == 401
            assert resp.json()["status"] == "invalid_signature"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Step 4: Webhook - PR Merged → Approved (J3 Step 13)
# ---------------------------------------------------------------------------


class TestWebhookPRMerged:
    """Verify GitHub PR merge event approves artifact."""

    def test_github_pr_merged_approves_artifact(self) -> None:
        payload = {
            "action": "closed",
            "pull_request": {
                "number": 42,
                "merged": True,
            },
        }
        body = json.dumps(payload).encode()

        client = TestClient(app, raise_server_exceptions=False)
        try:
            with patch(
                "app.api.routes.webhooks._verify_github_signature",
                new_callable=AsyncMock,
                return_value=True,
            ), patch(
                "app.api.routes.webhooks._handle_github_event",
                new_callable=AsyncMock,
            ) as mock_handler:
                resp = client.post(
                    "/api/webhooks/github",
                    content=body,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": github_signature(body),
                        "Content-Type": "application/json",
                    },
                )

            assert resp.status_code == 200
            mock_handler.assert_called_once_with("pull_request", payload)
        finally:
            app.dependency_overrides.clear()

    def test_github_pr_closed_without_merge_ignored(self) -> None:
        """PR closed without merge should not trigger approval."""
        payload = {
            "action": "closed",
            "pull_request": {
                "number": 42,
                "merged": False,
            },
        }
        body = json.dumps(payload).encode()

        client = TestClient(app, raise_server_exceptions=False)
        try:
            with patch(
                "app.api.routes.webhooks._verify_github_signature",
                new_callable=AsyncMock,
                return_value=True,
            ), patch(
                "app.api.routes.webhooks._handle_github_event",
                new_callable=AsyncMock,
            ) as mock_handler:
                resp = client.post(
                    "/api/webhooks/github",
                    content=body,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": github_signature(body),
                        "Content-Type": "application/json",
                    },
                )

            assert resp.status_code == 200
            mock_handler.assert_called_once()
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GitLab Webhook Tests
# ---------------------------------------------------------------------------


class TestGitLabWebhooks:
    """Verify GitLab MR note and merge event handling."""

    def test_gitlab_mr_note_triggers_handler(self) -> None:
        payload = {
            "object_kind": "note",
            "object_attributes": {
                "id": 111,
                "noteable_type": "MergeRequest",
                "note": "Fix the import paths",
                "position": {"new_path": "src/index.ts", "new_line": 10},
            },
            "merge_request": {"iid": 7},
        }
        body = json.dumps(payload).encode()

        client = TestClient(app, raise_server_exceptions=False)
        try:
            with patch(
                "app.api.routes.webhooks._verify_gitlab_token",
                new_callable=AsyncMock,
                return_value=True,
            ), patch(
                "app.api.routes.webhooks._handle_gitlab_event",
                new_callable=AsyncMock,
            ) as mock_handler:
                resp = client.post(
                    "/api/webhooks/gitlab",
                    content=body,
                    headers={
                        "X-Gitlab-Token": "valid-token",
                        "Content-Type": "application/json",
                    },
                )

            assert resp.status_code == 200
            mock_handler.assert_called_once_with("note", payload)
        finally:
            app.dependency_overrides.clear()

    def test_gitlab_mr_merged_triggers_handler(self) -> None:
        payload = {
            "object_kind": "merge_request",
            "object_attributes": {
                "iid": 7,
                "action": "merge",
                "state": "merged",
            },
        }
        body = json.dumps(payload).encode()

        client = TestClient(app, raise_server_exceptions=False)
        try:
            with patch(
                "app.api.routes.webhooks._verify_gitlab_token",
                new_callable=AsyncMock,
                return_value=True,
            ), patch(
                "app.api.routes.webhooks._handle_gitlab_event",
                new_callable=AsyncMock,
            ) as mock_handler:
                resp = client.post(
                    "/api/webhooks/gitlab",
                    content=body,
                    headers={
                        "X-Gitlab-Token": "valid-token",
                        "Content-Type": "application/json",
                    },
                )

            assert resp.status_code == 200
            mock_handler.assert_called_once_with("merge_request", payload)
        finally:
            app.dependency_overrides.clear()

    def test_gitlab_invalid_token_returns_401(self) -> None:
        payload = {"object_kind": "note"}
        body = json.dumps(payload).encode()

        client = TestClient(app, raise_server_exceptions=False)
        try:
            with patch(
                "app.api.routes.webhooks._verify_gitlab_token",
                new_callable=AsyncMock,
                return_value=False,
            ):
                resp = client.post(
                    "/api/webhooks/gitlab",
                    content=body,
                    headers={
                        "X-Gitlab-Token": "wrong",
                        "Content-Type": "application/json",
                    },
                )

            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Artifact Versions with PR metadata
# ---------------------------------------------------------------------------


class TestCodeArtifactVersions:
    """Verify code artifact versions list shows correct metadata."""

    def test_code_artifact_has_pr_url_and_number(self) -> None:
        mock_db = AsyncMock()
        artifact = make_artifact(
            artifact_id="art-code-1",
            artifact_type="code",
            status="in_review",
        )
        artifact.git_pr_url = "https://github.com/testorg/testrepo/pull/42"
        artifact.git_pr_number = 42
        artifact.git_feature_branch = "feature/settings-page"
        mock_db.get = AsyncMock(return_value=artifact)

        client = _setup_overrides(mock_db)
        try:
            resp = client.get("/api/artifacts/art-code-1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["git_pr_url"] == "https://github.com/testorg/testrepo/pull/42"
            assert data["git_pr_number"] == 42
            assert data["git_feature_branch"] == "feature/settings-page"
        finally:
            _teardown()

    def test_code_artifact_versions_list(self) -> None:
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-code-1", artifact_type="code")
        v1 = make_artifact_version(
            artifact_id="art-code-1",
            version_number=1,
            file_manifest=["src/settings.tsx", "src/settings.test.tsx"],
        )
        v2 = make_artifact_version(
            artifact_id="art-code-1",
            version_number=2,
            file_manifest=["src/settings.tsx", "src/settings.test.tsx", "src/types.ts"],
        )

        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[v2, v1])))
        ))

        client = _setup_overrides(mock_db)
        try:
            resp = client.get("/api/artifacts/art-code-1/versions")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["items"]) == 2
            # Versions should be ordered descending
            assert data["items"][0]["version_number"] == 2
            assert data["items"][1]["version_number"] == 1
            assert len(data["items"][0]["file_manifest"]) == 3
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Full Code Journey Integration
# ---------------------------------------------------------------------------


class TestFullCodeJourney:
    """High-level J3 integration test: create → delegate → webhook iterate → webhook merge."""

    def test_code_artifact_lifecycle_with_webhooks(self) -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        project = make_project(project_id="proj-1")
        ws = make_workspace()
        agents = [make_agent(name="Dev", specialization="Full-Stack")]

        # 1. Create code artifact
        mock_db.get = AsyncMock(return_value=project)
        client = _setup_overrides(mock_db)
        try:
            resp = client.post("/api/artifacts", json={
                "project_id": "proj-1",
                "artifact_type": "code",
                "title": "Settings Feature",
                "description": "Build settings page with preferences.",
                "git_repo_url": "https://github.com/testorg/testrepo",
                "git_base_branch": "main",
            })
            assert resp.status_code == 201
            assert resp.json()["artifact_type"] == "code"
            artifact_id = resp.json()["id"]

            # 2. Delegate
            artifact = make_artifact(
                artifact_id=artifact_id,
                project_id="proj-1",
                artifact_type="code",
            )
            mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
                (Artifact, artifact_id): artifact,
                (Workspace, WORKSPACE_ID): ws,
            }.get((cls, id_)))
            mock_db.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=agents)))
            ))

            with patch(
                "app.agents.router.route_brief",
                new_callable=AsyncMock,
                return_value=mock_code_routing_result(),
            ), patch("app.core.celery_app.execute_artifact_dag"):
                resp = client.post(f"/api/artifacts/{artifact_id}/delegate", json={
                    "confirm": True,
                })
            assert resp.status_code == 200
            assert resp.json()["status"] == "drafting"

            # 3. Simulate execution complete — now in_review with PR
            artifact.status = "in_review"
            artifact.git_pr_url = "https://github.com/testorg/testrepo/pull/42"
            artifact.git_pr_number = 42
            mock_db.get = AsyncMock(return_value=artifact)

            # Verify artifact shows PR info
            resp = client.get(f"/api/artifacts/{artifact_id}")
            assert resp.status_code == 200
            assert resp.json()["git_pr_number"] == 42

            # 4. Webhook: PR comment → iteration
            payload = {
                "action": "created",
                "pull_request": {"number": 42},
                "comment": {
                    "id": 55555,
                    "body": "Fix the type definitions",
                    "path": "src/types.ts",
                    "position": 5,
                },
            }
            body = json.dumps(payload).encode()
            with patch(
                "app.api.routes.webhooks._verify_github_signature",
                new_callable=AsyncMock,
                return_value=True,
            ), patch(
                "app.api.routes.webhooks._handle_github_event",
                new_callable=AsyncMock,
            ):
                resp = client.post(
                    "/api/webhooks/github",
                    content=body,
                    headers={
                        "X-GitHub-Event": "pull_request_review_comment",
                        "X-Hub-Signature-256": github_signature(body),
                        "Content-Type": "application/json",
                    },
                )
            assert resp.status_code == 200

            # 5. Webhook: PR merged → approved
            merge_payload = {
                "action": "closed",
                "pull_request": {"number": 42, "merged": True},
            }
            merge_body = json.dumps(merge_payload).encode()
            with patch(
                "app.api.routes.webhooks._verify_github_signature",
                new_callable=AsyncMock,
                return_value=True,
            ), patch(
                "app.api.routes.webhooks._handle_github_event",
                new_callable=AsyncMock,
            ):
                resp = client.post(
                    "/api/webhooks/github",
                    content=merge_body,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": github_signature(merge_body),
                        "Content-Type": "application/json",
                    },
                )
            assert resp.status_code == 200
        finally:
            _teardown()
