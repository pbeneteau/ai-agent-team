from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class KnowledgeReadinessLevel(str, Enum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class KnowledgeRecommendationPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class KnowledgeRecommendationType(str, Enum):
    PROJECT_PRIVATE = "project_private"
    INTERNAL_CONTEXT = "internal_context"
    USER_FEEDBACK = "user_feedback"
    TECHNICAL_CONTEXT = "technical_context"
    MARKET_CONTEXT = "market_context"
    DOMAIN_CONTEXT = "domain_context"
    PROCESS_PREFERENCE = "process_preference"


class KnowledgeRecommendationAction(str, Enum):
    PROVIDE_DOCUMENT = "provide_document"
    ADD_URL = "add_url"
    LAUNCH_RESEARCH = "launch_research"
    NO_ACTION_NEEDED = "no_action_needed"


class KnowledgeRecommendationStatus(str, Enum):
    SUGGESTED = "suggested"
    APPLIED = "applied"
    DISMISSED = "dismissed"
    STALE = "stale"


class KnowledgeGenerationSource(str, Enum):
    LLM = "llm"
    HEURISTIC_FALLBACK = "heuristic_fallback"


class KnowledgeRecommendationEvidence(BaseModel):
    source_label: str
    source_type: str
    excerpt: str


class KnowledgeRecommendation(BaseModel):
    id: str
    agent_id: str
    title: str
    summary: str
    reason: str
    priority: KnowledgeRecommendationPriority
    knowledge_type: KnowledgeRecommendationType
    action_type: KnowledgeRecommendationAction
    can_be_found_on_web: bool
    recommended_source: str
    suggested_topic: Optional[str] = None
    status: KnowledgeRecommendationStatus = KnowledgeRecommendationStatus.SUGGESTED
    evidence: list[KnowledgeRecommendationEvidence] = Field(default_factory=list)


class AgentKnowledgeReadiness(BaseModel):
    agent_id: str
    agent_name: str
    agent_title: str
    agent_role: str
    team_id: Optional[str] = None
    readiness_level: KnowledgeReadinessLevel
    readiness_score: int = 0
    summary: str
    missing_knowledge_summary: list[str] = Field(default_factory=list)
    recommendations: list[KnowledgeRecommendation] = Field(default_factory=list)
    generation_source: KnowledgeGenerationSource = KnowledgeGenerationSource.LLM
    generation_channel: Optional[str] = None
    generation_issue: Optional[str] = None
    context_fingerprint: str
    updated_at: str


class GlobalKnowledgeGap(BaseModel):
    id: str
    title: str
    action_type: KnowledgeRecommendationAction
    priority: KnowledgeRecommendationPriority
    can_be_found_on_web: bool
    agent_count: int = 0
    affected_agent_ids: list[str] = Field(default_factory=list)
    affected_agent_names: list[str] = Field(default_factory=list)


class GlobalKnowledgeReadiness(BaseModel):
    generated_at: str
    fingerprint: str
    total_agents: int = 0
    insufficient_agents: int = 0
    partial_agents: int = 0
    sufficient_agents: int = 0
    fallback_agent_count: int = 0
    has_fallback_results: bool = False
    generation_channel: Optional[str] = None
    agents: list[AgentKnowledgeReadiness] = Field(default_factory=list)
    shared_gaps: list[GlobalKnowledgeGap] = Field(default_factory=list)
