"""Pydantic schemas for the onboarding endpoint (TDD-04 Section 2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OnboardingRequest(BaseModel):
    company_name: str
    domain_description: str
    tech_stack: str | None = None
    team_size: int | None = None
    use_case: str = Field(pattern=r"^(code|content|both)$")


class AgentSummary(BaseModel):
    id: str
    name: str
    specialization: str
    status: str
    readiness_score: int
    progression_level: str


class WorkspaceSummary(BaseModel):
    id: str
    name: str
    onboarding_completed: bool


class OnboardingResponse(BaseModel):
    workspace: WorkspaceSummary
    agents: list[AgentSummary]
