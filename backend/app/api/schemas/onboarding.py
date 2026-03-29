"""Pydantic schemas for the onboarding endpoint (TDD-04 Section 2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OnboardingRequest(BaseModel):
    company_name: str
    domain_description: str
    product_description: str | None = None
    tech_stack: str | None = None
    company_stage: str | None = Field(
        default=None,
        pattern=r"^(idea|startup|growing|established)?$",
    )
    target_audience: str | None = None
    main_goals: str | None = None
    existing_team: str | None = None
    team_size: int | None = None
    use_case: str = Field(pattern=r"^(code|content|both)$")


class AgentSummary(BaseModel):
    id: str
    name: str
    specialization: str
    role: str
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
