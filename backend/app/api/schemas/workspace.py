"""Pydantic schemas for workspace GET/PATCH and workspace documents."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WorkspaceDetail(BaseModel):
    id: str
    name: str
    domain_description: str | None
    product_description: str | None
    tech_stack: str | None
    company_stage: str | None
    target_audience: str | None
    main_goals: str | None
    existing_team: str | None
    team_size: int | None
    monthly_budget_usd: float
    monthly_spend_usd: float
    onboarding_completed: bool
    created_at: datetime


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = None
    domain_description: str | None = None
    product_description: str | None = None
    tech_stack: str | None = None
    company_stage: str | None = None
    target_audience: str | None = None
    main_goals: str | None = None
    existing_team: str | None = None
    team_size: int | None = None


class WorkspaceDocumentItem(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    processing_status: str
    created_at: datetime
