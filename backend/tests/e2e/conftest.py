"""Shared fixtures for E2E tests.

These tests run against the FastAPI app with mocked Anthropic/Celery calls
but real DB-backed dependency overrides to verify full request → response flows.
LLM calls are mocked with deterministic responses since we're testing integration,
not Claude's output quality.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.workspace_id import get_workspace_id
from app.main import app


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
WEBHOOK_SECRET = "test-webhook-secret-hex"


# ---------------------------------------------------------------------------
# Mock DB session that records operations
# ---------------------------------------------------------------------------


class MockDBSession:
    """A mock async DB session that tracks entities and supports basic queries.

    This is more sophisticated than a bare AsyncMock — it stores entities
    in-memory so tests can verify state transitions across multiple API calls.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[type, str], Any] = {}
        self._added: list[Any] = []
        self._deleted: list[Any] = []

    def add(self, entity: Any) -> None:
        """Track an entity being added."""
        self._added.append(entity)
        if hasattr(entity, "id") and entity.id:
            self._store[(type(entity), entity.id)] = entity

    async def flush(self) -> None:
        """Flush — persist tracked entities to the in-memory store."""
        for entity in self._added:
            if hasattr(entity, "id") and entity.id:
                self._store[(type(entity), entity.id)] = entity
        self._added.clear()

    async def commit(self) -> None:
        await self.flush()

    async def rollback(self) -> None:
        self._added.clear()

    async def delete(self, entity: Any) -> None:
        self._deleted.append(entity)
        if hasattr(entity, "id"):
            self._store.pop((type(entity), entity.id), None)

    async def get(self, model_class: type, entity_id: str) -> Any | None:
        return self._store.get((model_class, entity_id))

    async def scalar(self, query: Any) -> Any:
        return 0

    async def execute(self, query: Any) -> MockResult:
        """Return a mock result. Override per-test as needed."""
        return MockResult([])

    def get_entity(self, model_class: type, entity_id: str) -> Any | None:
        """Direct access for test assertions."""
        return self._store.get((model_class, entity_id))

    def get_all(self, model_class: type) -> list[Any]:
        """Get all entities of a given type."""
        return [v for (cls, _), v in self._store.items() if cls is model_class]

    def put(self, entity: Any) -> None:
        """Directly insert an entity (for test setup)."""
        if hasattr(entity, "id") and entity.id:
            self._store[(type(entity), entity.id)] = entity


class MockResult:
    """Mimics SQLAlchemy async result."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> MockScalars:
        return MockScalars(self._rows)

    def scalar_one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def one(self) -> Any:
        return self._rows[0]

    def all(self) -> list[Any]:
        return self._rows

    def __iter__(self):
        return iter([(r,) for r in self._rows])


class MockScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db() -> MockDBSession:
    return MockDBSession()


@pytest.fixture()
def test_client(mock_db: MockDBSession) -> Generator[TestClient, None, None]:
    """TestClient with workspace_id and DB dependency overrides."""

    async def _db_override():
        yield mock_db

    async def _ws_override():
        return WORKSPACE_ID

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_workspace_id] = _ws_override

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Factory helpers — create entities for test setup
# ---------------------------------------------------------------------------


def make_workspace(
    workspace_id: str = WORKSPACE_ID,
    name: str = "Test Corp",
    onboarding_completed: bool = False,
    monthly_budget_usd: Decimal = Decimal("50.00"),
    monthly_spend_usd: Decimal = Decimal("0.00"),
    billing_period_start: datetime | None = None,
) -> MagicMock:
    ws = MagicMock()
    ws.id = workspace_id
    ws.name = name
    ws.domain_description = "B2B SaaS"
    ws.tech_stack = "Python, FastAPI"
    ws.onboarding_completed = onboarding_completed
    ws.monthly_budget_usd = monthly_budget_usd
    ws.monthly_spend_usd = monthly_spend_usd
    ws.billing_period_start = billing_period_start
    ws.created_at = datetime.now(timezone.utc)
    ws.updated_at = datetime.now(timezone.utc)
    return ws


def make_agent(
    agent_id: str | None = None,
    name: str = "Test Agent",
    specialization: str = "General purpose",
    status: str = "ready",
    readiness_score: int = 80,
    workspace_id: str = WORKSPACE_ID,
) -> MagicMock:
    agent = MagicMock()
    agent.id = agent_id or str(uuid.uuid4())
    agent.workspace_id = workspace_id
    agent.name = name
    agent.specialization = specialization
    agent.description = f"{name} description"
    agent.system_prompt = None
    agent.status = status
    agent.readiness_score = readiness_score
    agent.progression_level = "apprenti"
    agent.model_tier = "sonnet"
    agent.role = "worker"
    agent.tools = []
    agent.completed_artifacts = 3
    agent.avg_quality_score = Decimal("0.85")
    agent.last_reflection_at = None
    agent.archived_at = None
    agent.created_at = datetime.now(timezone.utc)
    agent.updated_at = datetime.now(timezone.utc)
    return agent


def make_project(
    project_id: str | None = None,
    name: str = "Test Project",
    workspace_id: str = WORKSPACE_ID,
    brief_published: str | None = None,
) -> MagicMock:
    project = MagicMock()
    project.id = project_id or str(uuid.uuid4())
    project.workspace_id = workspace_id
    project.name = name
    project.description = "Test project description"
    project.brief_draft = None
    project.brief_published = brief_published
    project.brief_fingerprint = None
    project.brief_published_at = None
    project.created_at = datetime.now(timezone.utc)
    project.updated_at = datetime.now(timezone.utc)
    return project


def make_artifact(
    artifact_id: str | None = None,
    project_id: str = "",
    artifact_type: str = "prose",
    status: str = "drafting",
    title: str = "Test Artifact",
    current_version: int = 0,
) -> MagicMock:
    artifact = MagicMock()
    artifact.id = artifact_id or str(uuid.uuid4())
    artifact.project_id = project_id
    artifact.artifact_type = artifact_type
    artifact.title = title
    artifact.goal = "Test goal"
    artifact.target_audience = "Test audience"
    artifact.context = "Test context"
    artifact.description = "Test description with enough detail for execution"
    artifact.status = status
    artifact.max_budget_usd = Decimal("5.00")
    artifact.total_cost_usd = Decimal("0.00")
    artifact.current_version = current_version
    artifact.git_repo_url = None
    artifact.git_base_branch = None
    artifact.git_feature_branch = None
    artifact.git_pr_url = None
    artifact.git_pr_number = None
    artifact.approved_at = None
    artifact.cancelled_at = None
    artifact.created_at = datetime.now(timezone.utc)
    artifact.updated_at = datetime.now(timezone.utc)
    return artifact


def make_execution_wave(
    wave_id: str | None = None,
    artifact_id: str = "",
    status: str = "queued",
    trigger: str = "initial",
    cost_usd: Decimal = Decimal("0.00"),
    current_step: int = 0,
    total_steps: int = 3,
) -> MagicMock:
    wave = MagicMock()
    wave.id = wave_id or str(uuid.uuid4())
    wave.artifact_id = artifact_id
    wave.celery_task_id = str(uuid.uuid4())
    wave.trigger = trigger
    wave.trigger_comment_id = None
    wave.dag_plan = {"waves": [{"wave_number": 1, "label": "Wave 1", "slots": []}]}
    wave.assembled_team = [{"agent_id": "a1", "agent_name": "Agent 1"}]
    wave.status = status
    wave.current_step = current_step
    wave.total_steps = total_steps
    wave.step_labels = ["Researching", "Drafting", "QA Review"]
    wave.cost_usd = cost_usd
    wave.input_tokens = 0
    wave.output_tokens = 0
    wave.error_message = None
    wave.started_at = datetime.now(timezone.utc) if status == "running" else None
    wave.completed_at = None
    wave.created_at = datetime.now(timezone.utc)
    return wave


def make_artifact_version(
    version_id: str | None = None,
    artifact_id: str = "",
    version_number: int = 1,
    file_manifest: list[str] | None = None,
) -> MagicMock:
    version = MagicMock()
    version.id = version_id or str(uuid.uuid4())
    version.artifact_id = artifact_id
    version.version_number = version_number
    version.s3_prefix = f"artifacts/{artifact_id}/v{version_number}/"
    version.file_manifest = file_manifest or ["report.md"]
    version.token_cost_usd = Decimal("0.15")
    version.input_tokens = 3000
    version.output_tokens = 1500
    version.assumptions = [{"text": "US market only", "category": "scope"}]
    version.sources = [{"url": "https://example.com", "title": "Source"}]
    version.execution_wave_id = None
    version.created_at = datetime.now(timezone.utc)
    return version


def make_contextual_comment(
    comment_id: str | None = None,
    artifact_version_id: str = "",
    instruction: str = "Fix this section",
) -> MagicMock:
    comment = MagicMock()
    comment.id = comment_id or str(uuid.uuid4())
    comment.artifact_version_id = artifact_version_id
    comment.file_path = None
    comment.highlight_start = 10
    comment.highlight_end = 50
    comment.highlighted_text = "some text"
    comment.instruction = instruction
    comment.source = "in_app"
    comment.external_comment_id = None
    comment.resolved = False
    comment.resolved_in_version_id = None
    comment.created_at = datetime.now(timezone.utc)
    return comment


def make_git_connection(
    connection_id: str | None = None,
    provider: str = "github",
    webhook_secret: str = WEBHOOK_SECRET,
) -> MagicMock:
    conn = MagicMock()
    conn.id = connection_id or str(uuid.uuid4())
    conn.workspace_id = WORKSPACE_ID
    conn.provider = provider
    conn.display_name = "Test GitHub"
    conn.access_token_encrypted = "encrypted-token"
    conn.repositories = [
        {
            "owner": "testorg",
            "name": "testrepo",
            "full_name": "testorg/testrepo",
            "default_branch": "main",
            "webhook_configured": True,
            "webhook_id": "wh-123",
        }
    ]
    conn.webhook_secret = webhook_secret
    conn.status = "active"
    conn.last_verified_at = datetime.now(timezone.utc)
    conn.created_at = datetime.now(timezone.utc)
    conn.updated_at = datetime.now(timezone.utc)
    return conn


# ---------------------------------------------------------------------------
# Mock LLM responses
# ---------------------------------------------------------------------------


def mock_sufficiency_eligible() -> dict:
    """Deterministic sufficiency check response — eligible, no issues."""
    return {
        "eligible": True,
        "score": 85,
        "issues": [],
    }


def mock_sufficiency_with_issues() -> dict:
    """Deterministic sufficiency check — not eligible, has critical issue."""
    return {
        "eligible": False,
        "score": 40,
        "issues": [
            {
                "severity": "critical",
                "field": "description",
                "matched_text": "various",
                "issue": "Ambiguous language — 'various' is too vague",
                "suggestion": "Specify exactly which items to include",
            }
        ],
    }


def mock_routing_result() -> MagicMock:
    """Deterministic routing result for delegate operations."""
    result = MagicMock()
    result.template_key = "bug_fix"
    result.dag_plan = {
        "waves": [
            {
                "wave_number": 1,
                "label": "Planning",
                "wave_type": "planning",
                "slots": [
                    {"slot_id": "tech_plan", "agent_id": "a1", "agent_name": "Tech Lead"},
                ],
            },
            {
                "wave_number": 2,
                "label": "Implementation",
                "wave_type": "execution",
                "slots": [
                    {"slot_id": "dev_impl", "agent_id": "a2", "agent_name": "Backend Dev"},
                ],
            },
            {
                "wave_number": 3,
                "label": "Review",
                "wave_type": "review",
                "slots": [
                    {"slot_id": "tech_review", "agent_id": "a1", "agent_name": "Tech Lead"},
                ],
            },
        ],
    }
    result.assembled_team = [
        {"agent_id": "a1", "agent_name": "Tech Lead"},
        {"agent_id": "a2", "agent_name": "Backend Dev"},
    ]
    result.step_labels = ["Planning", "Implementation", "Review"]
    result.estimated_cost = Decimal("0.42")
    result.reasoning = "Bug fix template selected."
    result.warnings = []
    result.is_fallback = False
    return result


def mock_code_routing_result() -> MagicMock:
    """Deterministic routing result for code artifacts."""
    result = MagicMock()
    result.template_key = "full_feature"
    result.dag_plan = {
        "waves": [
            {
                "wave_number": 1,
                "label": "Planning",
                "wave_type": "planning",
                "slots": [
                    {"slot_id": "pm_plan", "agent_id": "a1", "agent_name": "PM Lead"},
                    {"slot_id": "design_plan", "agent_id": "a2", "agent_name": "Design Lead"},
                ],
            },
            {
                "wave_number": 2,
                "label": "Implementation",
                "wave_type": "execution",
                "slots": [
                    {"slot_id": "backend_impl", "agent_id": "a3", "agent_name": "Backend Dev"},
                    {"slot_id": "frontend_impl", "agent_id": "a4", "agent_name": "Frontend Dev"},
                    {"slot_id": "qa_impl", "agent_id": "a5", "agent_name": "QA Engineer"},
                ],
            },
            {
                "wave_number": 3,
                "label": "Review",
                "wave_type": "review",
                "slots": [
                    {"slot_id": "tech_review", "agent_id": "a1", "agent_name": "Tech Lead"},
                ],
            },
        ],
    }
    result.assembled_team = [
        {"agent_id": "a1", "agent_name": "PM Lead"},
        {"agent_id": "a2", "agent_name": "Design Lead"},
        {"agent_id": "a3", "agent_name": "Backend Dev"},
        {"agent_id": "a4", "agent_name": "Frontend Dev"},
        {"agent_id": "a5", "agent_name": "QA Engineer"},
    ]
    result.step_labels = ["Planning", "Implementation", "Review"]
    result.estimated_cost = Decimal("0.84")
    result.reasoning = "Full feature template selected for code artifact."
    result.warnings = []
    result.is_fallback = False
    return result


# ---------------------------------------------------------------------------
# GitHub webhook signature helper
# ---------------------------------------------------------------------------


def github_signature(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """Compute GitHub-style HMAC-SHA256 signature."""
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"
