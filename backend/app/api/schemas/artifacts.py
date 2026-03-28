"""Pydantic schemas for artifact endpoints (TDD-04 Section 5)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class CreateArtifactRequest(BaseModel):
    project_id: str
    artifact_type: str = Field(pattern=r"^(prose|code)$")
    title: str
    goal: str | None = None
    target_audience: str | None = None
    context: str | None = None
    description: str
    max_budget_usd: float = 5.00
    git_repo_url: str | None = None
    git_base_branch: str | None = None


# ---------------------------------------------------------------------------
# Full artifact response (used by create, get, update)
# ---------------------------------------------------------------------------


class ArtifactResponse(BaseModel):
    id: str
    project_id: str
    artifact_type: str
    title: str
    goal: str | None = None
    target_audience: str | None = None
    context: str | None = None
    description: str | None = None
    status: str
    max_budget_usd: float
    total_cost_usd: float
    current_version: int
    git_repo_url: str | None = None
    git_base_branch: str | None = None
    git_feature_branch: str | None = None
    git_pr_url: str | None = None
    git_pr_number: int | None = None
    approved_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Sufficiency check
# ---------------------------------------------------------------------------


class SufficiencyIssueSchema(BaseModel):
    severity: str
    field: str
    matched_text: str
    issue: str
    suggestion: str


class SufficiencyResponse(BaseModel):
    eligible: bool
    score: int
    issues: list[SufficiencyIssueSchema]


class StandaloneSufficiencyRequest(BaseModel):
    artifact_type: str = Field(pattern=r"^(prose|code)$")
    title: str
    goal: str | None = None
    target_audience: str | None = None
    context: str | None = None
    description: str


# ---------------------------------------------------------------------------
# Delegate
# ---------------------------------------------------------------------------


class DelegateRequest(BaseModel):
    confirm: bool = False
    overrides: dict | None = None


class WaveAgentInfo(BaseModel):
    slot_id: str
    agent_id: str | None = None
    agent_name: str | None = None


class WavePlanInfo(BaseModel):
    wave_number: int
    label: str
    agents: list[WaveAgentInfo]


class DelegatePlan(BaseModel):
    template_id: str
    template_name: str
    waves: list[WavePlanInfo]
    estimated_cost_usd: float
    estimated_waves: int


class DelegatePreviewResponse(BaseModel):
    plan: DelegatePlan


class DelegateConfirmResponse(BaseModel):
    artifact_id: str
    status: str
    execution_wave_id: str
    plan: DelegatePlan


# ---------------------------------------------------------------------------
# Status (heartbeat)
# ---------------------------------------------------------------------------


class ExecutionStatus(BaseModel):
    wave_id: str
    current_step: int
    total_steps: int
    step_labels: list[str]
    cost_usd: float
    started_at: datetime | None = None
    estimated_remaining_seconds: int | None = None


class ArtifactStatusResponse(BaseModel):
    status: str
    execution: ExecutionStatus | None = None


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


class VersionItem(BaseModel):
    id: str
    version_number: int
    file_manifest: list[str]
    token_cost_usd: float
    input_tokens: int
    output_tokens: int
    assumptions: list
    sources: list
    created_at: datetime


# ---------------------------------------------------------------------------
# Iterate
# ---------------------------------------------------------------------------


class IterateRequest(BaseModel):
    file_path: str | None = None
    highlighted_text: str | None = None
    highlight_start: int | None = None
    highlight_end: int | None = None
    instruction: str


class IterateResponse(BaseModel):
    comment_id: str
    execution_wave_id: str
    artifact_status: str
    message: str


# ---------------------------------------------------------------------------
# Approve / Cancel
# ---------------------------------------------------------------------------


class ApproveResponse(BaseModel):
    id: str
    status: str
    approved_at: datetime


class CancelResponse(BaseModel):
    id: str
    status: str
    cancelled_at: datetime


# ---------------------------------------------------------------------------
# Artifact list item (for project listing)
# ---------------------------------------------------------------------------


class ArtifactListItem(BaseModel):
    id: str
    project_id: str
    artifact_type: str
    title: str
    status: str
    total_cost_usd: float
    current_version: int
    created_at: datetime
    updated_at: datetime
