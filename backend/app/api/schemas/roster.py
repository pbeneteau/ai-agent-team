"""Pydantic schemas for roster endpoints (TDD-04 Section 3)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent list/detail
# ---------------------------------------------------------------------------


class AgentListItem(BaseModel):
    id: str
    name: str
    specialization: str
    role: str
    description: str | None = None
    status: str
    readiness_score: int
    progression_level: str
    model_tier: str
    completed_artifacts: int
    avg_quality_score: float | None = None
    archived_at: datetime | None = None
    created_at: datetime


class SkillsSummary(BaseModel):
    total_skill_tokens: int
    total_learning_tokens: int
    budget_used_pct: int
    skill_count: int
    learning_count: int


class AgentDetail(BaseModel):
    id: str
    name: str
    specialization: str
    role: str
    description: str | None = None
    system_prompt: str | None = None
    status: str
    readiness_score: int
    progression_level: str
    model_tier: str
    tools: list[str]
    completed_artifacts: int
    avg_quality_score: float | None = None
    last_reflection_at: datetime | None = None
    archived_at: datetime | None = None
    skills_summary: SkillsSummary
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------


class CreateAgentRequest(BaseModel):
    name: str
    specialization: str
    description: str | None = None
    model_tier: str = "sonnet"


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    specialization: str | None = None
    description: str | None = None
    model_tier: str | None = None


# ---------------------------------------------------------------------------
# Archive response
# ---------------------------------------------------------------------------


class ArchiveResponse(BaseModel):
    id: str
    archived_at: datetime


class RestoreResponse(BaseModel):
    id: str
    restored: bool


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class SkillItem(BaseModel):
    id: str
    category: str
    title: str
    content: str
    token_count: int
    source_artifact_id: str | None = None
    created_at: datetime
    updated_at: datetime


class BudgetInfo(BaseModel):
    used_tokens: int
    max_tokens: int
    used_pct: int


class SkillsListResponse(BaseModel):
    items: list[SkillItem]
    budget: BudgetInfo


# ---------------------------------------------------------------------------
# Learning profile
# ---------------------------------------------------------------------------


class ReadinessComponent(BaseModel):
    points: int
    max: int
    met: bool


class ReadinessBreakdown(BaseModel):
    has_skills: ReadinessComponent
    has_briefing: ReadinessComponent
    onboarding_complete: ReadinessComponent
    has_learnings: ReadinessComponent


class LearningProfile(BaseModel):
    agent_id: str
    readiness_score: int
    readiness_breakdown: ReadinessBreakdown
    progression_level: str
    completed_artifacts: int
    avg_quality_score: float | None = None
    last_reflection_at: datetime | None = None
    skill_token_usage: BudgetInfo


# ---------------------------------------------------------------------------
# Research / Reflect / Knowledge
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    topic: str


class ActionResponse(BaseModel):
    message: str
    agent_status: str


class DismissResponse(BaseModel):
    id: str
    dismissed: bool


# ---------------------------------------------------------------------------
# Knowledge recommendations
# ---------------------------------------------------------------------------


class KnowledgeRecommendation(BaseModel):
    id: str
    type: str
    title: str
    reason: str
    suggested_action: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Global readiness
# ---------------------------------------------------------------------------


class ReadinessByLevel(BaseModel):
    sufficient: int
    partial: int
    insufficient: int


class ReadinessByStatus(BaseModel):
    ready: int
    learning: int
    reflecting: int
    working: int


class AgentAttention(BaseModel):
    agent_id: str
    agent_name: str
    readiness_score: int
    issue: str


class GlobalReadiness(BaseModel):
    total_agents: int
    by_readiness: ReadinessByLevel
    by_status: ReadinessByStatus
    avg_readiness_score: int
    agents_needing_attention: list[AgentAttention]
