from typing import Literal, Optional

from pydantic import BaseModel, Field


class RecommendedAgentSpec(BaseModel):
    name: str = Field(max_length=60)
    title: str = Field(max_length=100)
    specialization: str = Field(max_length=80)
    goal: str = Field(max_length=180)
    backstory: str = Field(max_length=180)
    is_lead: bool = False
    model_tier: Literal["sonnet", "opus"] = "sonnet"


class TeamRecommendation(BaseModel):
    id: str = Field(max_length=60)
    name: str = Field(max_length=100)
    description: str = Field(max_length=180)
    domain: str = Field(max_length=80)
    reason: str = Field(max_length=180)
    urgency: Literal["now", "soon", "later"]
    score: int
    agents: list[RecommendedAgentSpec] = Field(default_factory=list, max_length=3)


class TeamChangeRecommendation(BaseModel):
    id: str = Field(max_length=60)
    team_id: str = Field(max_length=80)
    team_name: str = Field(max_length=100)
    change_type: Literal["add_specialist", "remove_agent", "adjust_scope"]
    urgency: Literal["now", "soon", "later"]
    score: int
    reason: str = Field(max_length=180)
    target_agent_id: Optional[str] = Field(default=None, max_length=80)
    target_agent_name: Optional[str] = Field(default=None, max_length=100)
    suggested_agent: Optional[RecommendedAgentSpec] = None
    scope_update: Optional[str] = Field(default=None, max_length=160)


class RecommendationResponse(BaseModel):
    new_teams: list[TeamRecommendation]
    team_changes: list[TeamChangeRecommendation]
    generation_source: Literal["llm", "heuristic_fallback"] = "llm"
    generation_channel: Optional[str] = None
    generation_issue: Optional[str] = None


class RecommendationCachePayload(BaseModel):
    version: int
    fingerprint: str
    recommendations: RecommendationResponse


class RecommendationLLMPayload(BaseModel):
    new_teams: list[TeamRecommendation] = Field(default_factory=list)
    team_changes: list[TeamChangeRecommendation] = Field(default_factory=list)
