"""Pydantic schemas for usage & cost tracking endpoints.

Ref: TDD-04 Section 12.
"""

from pydantic import BaseModel, Field


class BudgetInfo(BaseModel):
    monthly_limit_usd: float
    monthly_spent_usd: float
    remaining_usd: float
    usage_pct: int


class ModelUsage(BaseModel):
    cost_usd: float
    input_tokens: int
    output_tokens: int


class ArtifactUsage(BaseModel):
    artifact_id: str
    title: str
    cost_usd: float
    versions: int


class DailyBreakdown(BaseModel):
    date: str
    cost_usd: float
    artifact_count: int


class UsageResponse(BaseModel):
    period: str
    period_start: str
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    budget: BudgetInfo
    by_model: dict[str, ModelUsage] = Field(default_factory=dict)
    by_artifact: list[ArtifactUsage] = Field(default_factory=list)
    daily_breakdown: list[DailyBreakdown] = Field(default_factory=list)


class UpdateBudgetRequest(BaseModel):
    monthly_budget_usd: float = Field(..., gt=0)


class UpdateBudgetResponse(BaseModel):
    monthly_budget_usd: float
    monthly_spent_usd: float
    remaining_usd: float
