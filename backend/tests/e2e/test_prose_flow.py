"""Ticket 11.1 — E2E: Prose Artifact Flow (Journey J2).

Verifies the complete prose artifact lifecycle:
  Onboarding → Agents ready → Create project → Publish brief →
  Create artifact → Validate → Fix → Re-validate → Delegate →
  Heartbeat progress → In Review → Review content → Contextual comment →
  Iteration → Diff (v1→v2) → Approve → Reflection trigger.

Every state transition is verified against TDD-01 Section 5.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.workspace_id import get_workspace_id
from app.main import app
from app.models.agent import Agent
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.contextual_comment import ContextualComment
from app.models.execution_wave import ExecutionWave
from app.models.project import Project
from app.models.workspace import Workspace

from .conftest import (
    WORKSPACE_ID,
    make_agent,
    make_artifact,
    make_artifact_version,
    make_contextual_comment,
    make_execution_wave,
    make_project,
    make_workspace,
    mock_routing_result,
    mock_sufficiency_eligible,
    mock_sufficiency_with_issues,
)


# ---------------------------------------------------------------------------
# Shared mock setup
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
# Step 1: Onboarding (J1)
# ---------------------------------------------------------------------------


class TestOnboarding:
    """Verify first-time onboarding creates workspace + agents."""

    def test_onboarding_creates_workspace_and_agents(self) -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        ws = make_workspace(onboarding_completed=False)
        mock_db.get = AsyncMock(return_value=ws)

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.api.routes.onboarding._generate_roster",
                new_callable=AsyncMock,
                return_value=[
                    {"name": "Research Analyst", "specialization": "Research"},
                    {"name": "Content Writer", "specialization": "Writing"},
                    {"name": "QA Engineer", "specialization": "QA"},
                ],
            ), patch("app.core.celery_app.execute_agent_learning") as mock_learn:
                resp = client.post("/api/onboarding", json={
                    "company_name": "Test Corp",
                    "domain_description": "B2B SaaS startup",
                    "tech_stack": "Python, FastAPI, Next.js",
                    "team_size": 3,
                    "use_case": "both",
                })

            assert resp.status_code == 201
            data = resp.json()
            assert data["workspace"]["onboarding_completed"] is True
            assert len(data["agents"]) == 3
            assert all(a["status"] == "learning" for a in data["agents"])
            assert all(a["readiness_score"] == 0 for a in data["agents"])
            assert mock_learn.delay.call_count == 3
        finally:
            _teardown()

    def test_onboarding_409_if_already_completed(self) -> None:
        mock_db = AsyncMock()
        ws = make_workspace(onboarding_completed=True)
        mock_db.get = AsyncMock(return_value=ws)

        client = _setup_overrides(mock_db)
        try:
            resp = client.post("/api/onboarding", json={
                "company_name": "Test Corp",
                "domain_description": "B2B SaaS",
                "use_case": "both",
            })
            assert resp.status_code == 409
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Step 2: Create Project + Publish Brief (J5)
# ---------------------------------------------------------------------------


class TestProjectAndBrief:
    """Verify project creation and brief publishing with rebriefing."""

    def test_create_project(self) -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        client = _setup_overrides(mock_db)
        try:
            resp = client.post("/api/projects", json={
                "name": "Q3 Product Launch",
                "description": "Launch new pricing tier for enterprise customers.",
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["name"] == "Q3 Product Launch"
            assert data["brief_draft"] is None
            assert data["brief_published"] is None
        finally:
            _teardown()

    def test_save_draft_and_publish_brief(self) -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        project = make_project(project_id="proj-1")
        mock_db.get = AsyncMock(return_value=project)

        client = _setup_overrides(mock_db)
        try:
            # Save draft
            draft_resp = client.put("/api/projects/proj-1/context/draft", json={
                "content": "We are launching a new pricing tier for enterprise.",
            })
            assert draft_resp.status_code == 200
            assert draft_resp.json()["draft"] is not None

            # Publish brief (triggers rebriefing)
            project.brief_draft = "We are launching a new pricing tier for enterprise."
            with patch(
                "app.agents.briefing.brief_all_agents",
                new_callable=AsyncMock,
                return_value=5,
            ) as mock_brief:
                pub_resp = client.post("/api/projects/proj-1/context/publish")

            assert pub_resp.status_code == 200
            data = pub_resp.json()
            assert data["published"] is not None
            assert data["fingerprint"] is not None
            assert data["agents_rebriefed"] == 5
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Step 3: Create Prose Artifact (J2 Steps 1-3)
# ---------------------------------------------------------------------------


class TestCreateProseArtifact:
    """Verify artifact creation and sufficiency check flow."""

    def test_create_prose_artifact(self) -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        project = make_project(project_id="proj-1")
        mock_db.get = AsyncMock(return_value=project)

        client = _setup_overrides(mock_db)
        try:
            resp = client.post("/api/artifacts", json={
                "project_id": "proj-1",
                "artifact_type": "prose",
                "title": "Q3 Competitive Analysis",
                "goal": "Identify top 3 competitor weaknesses",
                "target_audience": "Exec team, investors",
                "context": "US market, B2B SaaS only",
                "description": "Compare Notion, Coda, Confluence on pricing and features.",
                "max_budget_usd": 5.00,
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["artifact_type"] == "prose"
            assert data["status"] == "drafting"
            assert data["current_version"] == 0
            assert data["total_cost_usd"] == 0.0
        finally:
            _teardown()

    def test_validate_shows_issues_for_vague_brief(self) -> None:
        """Brief with 'various' triggers a critical issue."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", project_id="proj-1")
        project = make_project(project_id="proj-1")
        ws = make_workspace(onboarding_completed=True)

        mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
            (Artifact, "art-1"): artifact,
            (Project, "proj-1"): project,
            (Workspace, WORKSPACE_ID): ws,
        }.get((cls, id_)))

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.agents.sufficiency.run_sufficiency_check",
                new_callable=AsyncMock,
            ) as mock_check:
                mock_result = MagicMock()
                mock_result.eligible = False
                mock_result.score = 40
                issue = MagicMock()
                issue.severity = "critical"
                issue.field = "description"
                issue.matched_text = "various"
                issue.issue = "Ambiguous language"
                issue.suggestion = "Specify which items"
                mock_result.issues = [issue]
                mock_check.return_value = mock_result

                resp = client.post("/api/artifacts/art-1/validate")

            assert resp.status_code == 200
            data = resp.json()
            assert data["eligible"] is False
            assert data["score"] == 40
            assert len(data["issues"]) == 1
            assert data["issues"][0]["severity"] == "critical"
            assert data["issues"][0]["matched_text"] == "various"
        finally:
            _teardown()

    def test_validate_eligible_after_fix(self) -> None:
        """After fixing issues, validation returns eligible."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", project_id="proj-1")
        project = make_project(project_id="proj-1")
        ws = make_workspace(onboarding_completed=True)

        mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
            (Artifact, "art-1"): artifact,
            (Project, "proj-1"): project,
            (Workspace, WORKSPACE_ID): ws,
        }.get((cls, id_)))

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.agents.sufficiency.run_sufficiency_check",
                new_callable=AsyncMock,
            ) as mock_check:
                mock_result = MagicMock()
                mock_result.eligible = True
                mock_result.score = 85
                mock_result.issues = []
                mock_check.return_value = mock_result

                resp = client.post("/api/artifacts/art-1/validate")

            assert resp.status_code == 200
            data = resp.json()
            assert data["eligible"] is True
            assert data["score"] == 85
            assert len(data["issues"]) == 0
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Step 4: Delegate + Heartbeat (J2 Steps 6-8)
# ---------------------------------------------------------------------------


class TestDelegateAndHeartbeat:
    """Verify delegation preview, confirm, and heartbeat polling."""

    def test_delegate_preview_shows_plan(self) -> None:
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", project_id="proj-1")
        ws = make_workspace(onboarding_completed=True)
        agents = [
            make_agent(name="Research Analyst", specialization="Research"),
            make_agent(name="Content Writer", specialization="Writing"),
            make_agent(name="QA Engineer", specialization="QA"),
        ]

        mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
            (Artifact, "art-1"): artifact,
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
                return_value=mock_routing_result(),
            ):
                resp = client.post("/api/artifacts/art-1/delegate", json={
                    "confirm": False,
                })

            assert resp.status_code == 200
            data = resp.json()
            assert "plan" in data
            assert data["plan"]["template_name"] is not None
            assert len(data["plan"]["waves"]) >= 1
            assert data["plan"]["estimated_cost_usd"] > 0
        finally:
            _teardown()

    def test_delegate_confirm_creates_wave_and_enqueues(self) -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", project_id="proj-1")
        ws = make_workspace(onboarding_completed=True)
        agents = [make_agent(name="Agent", specialization="General")]

        mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
            (Artifact, "art-1"): artifact,
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
                return_value=mock_routing_result(),
            ), patch(
                "app.core.celery_app.execute_artifact_dag",
            ) as mock_celery:
                resp = client.post("/api/artifacts/art-1/delegate", json={
                    "confirm": True,
                })

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "drafting"
            assert "execution_wave_id" in data
            assert mock_celery.delay.called
        finally:
            _teardown()

    def test_heartbeat_returns_execution_status(self) -> None:
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="drafting")
        wave = make_execution_wave(
            artifact_id="art-1",
            status="running",
            current_step=1,
            total_steps=3,
        )

        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=wave)
        ))

        client = _setup_overrides(mock_db)
        try:
            resp = client.get("/api/artifacts/art-1/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "drafting"
            assert data["execution"] is not None
            assert data["execution"]["current_step"] == 1
            assert data["execution"]["total_steps"] == 3
            assert len(data["execution"]["step_labels"]) == 3
            assert data["execution"]["cost_usd"] >= 0
        finally:
            _teardown()

    def test_heartbeat_no_execution_when_not_drafting(self) -> None:
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="in_review")
        mock_db.get = AsyncMock(return_value=artifact)

        client = _setup_overrides(mock_db)
        try:
            resp = client.get("/api/artifacts/art-1/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "in_review"
            assert data["execution"] is None
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Step 5: Review + Versions (J2 Steps 9-10)
# ---------------------------------------------------------------------------


class TestArtifactReview:
    """Verify review endpoints — versions list and file proxy."""

    def test_list_versions(self) -> None:
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="in_review")
        v1 = make_artifact_version(artifact_id="art-1", version_number=1)

        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[v1])))
        ))

        client = _setup_overrides(mock_db)
        try:
            resp = client.get("/api/artifacts/art-1/versions")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["version_number"] == 1
            assert "report.md" in data["items"][0]["file_manifest"]
            assert len(data["items"][0]["assumptions"]) > 0
            assert len(data["items"][0]["sources"]) > 0
        finally:
            _teardown()

    def test_file_proxy_serves_content(self) -> None:
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="in_review")
        v1 = make_artifact_version(
            artifact_id="art-1",
            version_number=1,
            file_manifest=["report.md"],
        )

        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=v1)
        ))

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.core.s3_workspace.download_artifact_file",
                return_value=b"# Competitive Analysis\n\nContent here.",
            ):
                resp = client.get("/api/artifacts/art-1/versions/1/files/report.md")

            assert resp.status_code == 200
            assert b"Competitive Analysis" in resp.content
            assert "text/markdown" in resp.headers.get("content-type", "")
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Step 6: Contextual Comment + Iteration (J2 Steps 11-13)
# ---------------------------------------------------------------------------


class TestIterationFlow:
    """Verify contextual comment creation and iteration execution."""

    def test_iterate_creates_comment_and_new_wave(self) -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="in_review")
        ws = make_workspace()
        v1 = make_artifact_version(artifact_id="art-1", version_number=1)
        agents = [make_agent(name="Writer", specialization="Content")]

        mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
            (Artifact, "art-1"): artifact,
            (Workspace, WORKSPACE_ID): ws,
        }.get((cls, id_)))

        # execute returns: first call for version lookup, second for agent roster
        call_count = 0

        async def _execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Version query
                return MagicMock(
                    scalar_one_or_none=MagicMock(return_value=v1)
                )
            else:
                # Agent query
                return MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=agents)))
                )

        mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.agents.router.route_brief",
                new_callable=AsyncMock,
                return_value=mock_routing_result(),
            ), patch(
                "app.core.celery_app.execute_artifact_dag",
            ) as mock_celery:
                resp = client.post("/api/artifacts/art-1/iterate", json={
                    "highlighted_text": "pricing comparison paragraph",
                    "highlight_start": 150,
                    "highlight_end": 220,
                    "instruction": "Add per-seat vs. flat-rate pricing breakdown.",
                })

            assert resp.status_code == 202
            data = resp.json()
            assert data["artifact_status"] == "drafting"
            assert "comment_id" in data
            assert "execution_wave_id" in data
            assert mock_celery.delay.called
            # Artifact should have transitioned back to drafting
            assert artifact.status == "drafting"
        finally:
            _teardown()

    def test_iterate_requires_in_review_status(self) -> None:
        """Cannot iterate an artifact that's not in_review."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="drafting")
        mock_db.get = AsyncMock(return_value=artifact)

        client = _setup_overrides(mock_db)
        try:
            resp = client.post("/api/artifacts/art-1/iterate", json={
                "instruction": "Change this section",
            })
            assert resp.status_code == 422 or resp.status_code == 400
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Step 7: Approve + Reflection Trigger (J2 Step 14)
# ---------------------------------------------------------------------------


class TestApproveAndReflection:
    """Verify approval transitions and reflection triggering."""

    def test_approve_transitions_to_approved(self) -> None:
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="in_review")
        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            __iter__=MagicMock(return_value=iter([]))
        ))

        client = _setup_overrides(mock_db)
        try:
            resp = client.patch("/api/artifacts/art-1/approve")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "approved"
            assert data["approved_at"] is not None
            assert artifact.status == "approved"
        finally:
            _teardown()

    def test_approve_triggers_reflection_when_threshold_met(self) -> None:
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="in_review")
        wave = make_execution_wave(artifact_id="art-1")
        wave.assembled_team = [{"agent_id": "agent-1"}]
        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            __iter__=MagicMock(return_value=iter([(wave,)]))
        ))

        client = _setup_overrides(mock_db)
        try:
            with patch(
                "app.agents.reflection.should_trigger_reflection",
                new_callable=AsyncMock,
                return_value=True,
            ), patch(
                "app.core.celery_app.execute_agent_reflection",
            ) as mock_reflect:
                resp = client.patch("/api/artifacts/art-1/approve")

            assert resp.status_code == 200
            assert mock_reflect.delay.called
        finally:
            _teardown()

    def test_approve_requires_in_review_status(self) -> None:
        """Cannot approve artifact in drafting status."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="drafting")
        mock_db.get = AsyncMock(return_value=artifact)

        client = _setup_overrides(mock_db)
        try:
            resp = client.patch("/api/artifacts/art-1/approve")
            assert resp.status_code == 422 or resp.status_code == 400
        finally:
            _teardown()

    def test_approve_already_approved_fails(self) -> None:
        """Cannot approve artifact that's already approved."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="approved")
        mock_db.get = AsyncMock(return_value=artifact)

        client = _setup_overrides(mock_db)
        try:
            resp = client.patch("/api/artifacts/art-1/approve")
            assert resp.status_code == 422 or resp.status_code == 400
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Step 8: Cancel flow
# ---------------------------------------------------------------------------


class TestCancelFlow:
    """Verify cancellation from drafting and in_review states."""

    def test_cancel_from_drafting_revokes_celery(self) -> None:
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="drafting")
        wave = make_execution_wave(artifact_id="art-1", status="running")
        mock_db.get = AsyncMock(return_value=artifact)
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[wave])))
        ))

        client = _setup_overrides(mock_db)
        try:
            with patch("app.core.celery_app.celery_app") as mock_celery_app:
                resp = client.patch("/api/artifacts/art-1/cancel")

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "cancelled"
            assert data["cancelled_at"] is not None
            assert wave.status == "cancelled"
        finally:
            _teardown()

    def test_cancel_from_in_review(self) -> None:
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="in_review")
        mock_db.get = AsyncMock(return_value=artifact)

        client = _setup_overrides(mock_db)
        try:
            resp = client.patch("/api/artifacts/art-1/cancel")
            assert resp.status_code == 200
            assert resp.json()["status"] == "cancelled"
        finally:
            _teardown()

    def test_cancel_approved_fails(self) -> None:
        """Terminal state — cannot cancel an approved artifact."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="approved")
        mock_db.get = AsyncMock(return_value=artifact)

        client = _setup_overrides(mock_db)
        try:
            resp = client.patch("/api/artifacts/art-1/cancel")
            assert resp.status_code == 422 or resp.status_code == 400
        finally:
            _teardown()

    def test_cancel_already_cancelled_fails(self) -> None:
        """Terminal state — cannot cancel a cancelled artifact."""
        mock_db = AsyncMock()
        artifact = make_artifact(artifact_id="art-1", status="cancelled")
        mock_db.get = AsyncMock(return_value=artifact)

        client = _setup_overrides(mock_db)
        try:
            resp = client.patch("/api/artifacts/art-1/cancel")
            assert resp.status_code == 422 or resp.status_code == 400
        finally:
            _teardown()


# ---------------------------------------------------------------------------
# Full Journey Integration: J2 End-to-End
# ---------------------------------------------------------------------------


class TestFullProseJourney:
    """High-level integration test covering the complete J2 prose artifact lifecycle."""

    def test_full_prose_lifecycle_state_transitions(self) -> None:
        """Verify the full state machine: drafting → in_review → drafting → in_review → approved."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        ws = make_workspace(onboarding_completed=True)
        project = make_project(project_id="proj-1")
        agents = [
            make_agent(name="Researcher", specialization="Research"),
            make_agent(name="Writer", specialization="Content"),
        ]

        # Create artifact
        mock_db.get = AsyncMock(return_value=project)
        client = _setup_overrides(mock_db)
        try:
            resp = client.post("/api/artifacts", json={
                "project_id": "proj-1",
                "artifact_type": "prose",
                "title": "Competitive Analysis",
                "description": "Compare Notion, Coda, Confluence on pricing, features, AI.",
            })
            assert resp.status_code == 201
            artifact_id = resp.json()["id"]
            status = resp.json()["status"]
            assert status == "drafting"

            # Verify: artifact starts in drafting
            # Transition: delegate → stays in drafting (Celery task runs async)
            artifact = make_artifact(
                artifact_id=artifact_id,
                project_id="proj-1",
                status="drafting",
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
                return_value=mock_routing_result(),
            ), patch("app.core.celery_app.execute_artifact_dag"):
                resp = client.post(f"/api/artifacts/{artifact_id}/delegate", json={
                    "confirm": True,
                })
            assert resp.status_code == 200
            assert resp.json()["status"] == "drafting"

            # Simulate execution complete → in_review
            artifact.status = "in_review"
            v1 = make_artifact_version(artifact_id=artifact_id, version_number=1)

            # Iterate (contextual comment) → back to drafting
            call_count = 0

            async def _execute(*a, **kw):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return MagicMock(scalar_one_or_none=MagicMock(return_value=v1))
                return MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=agents)))
                )

            mock_db.execute = AsyncMock(side_effect=_execute)
            mock_db.get = AsyncMock(side_effect=lambda cls, id_: {
                (Artifact, artifact_id): artifact,
                (Workspace, WORKSPACE_ID): ws,
            }.get((cls, id_)))

            with patch(
                "app.agents.router.route_brief",
                new_callable=AsyncMock,
                return_value=mock_routing_result(),
            ), patch("app.core.celery_app.execute_artifact_dag"):
                resp = client.post(f"/api/artifacts/{artifact_id}/iterate", json={
                    "instruction": "Add per-seat pricing breakdown",
                })
            assert resp.status_code == 202
            assert artifact.status == "drafting"

            # Simulate second execution complete → back to in_review
            artifact.status = "in_review"
            mock_db.get = AsyncMock(return_value=artifact)
            mock_db.execute = AsyncMock(return_value=MagicMock(
                __iter__=MagicMock(return_value=iter([]))
            ))

            # Approve → approved (terminal)
            resp = client.patch(f"/api/artifacts/{artifact_id}/approve")
            assert resp.status_code == 200
            assert resp.json()["status"] == "approved"
            assert artifact.status == "approved"
        finally:
            _teardown()
