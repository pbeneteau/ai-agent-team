from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
import uuid


class AgentStatus(str, Enum):
    PENDING = "pending"
    LEARNING = "learning"
    READY = "ready"
    WORKING = "working"
    ERROR = "error"


class AgentRole(str, Enum):
    ASSOCIATE = "associate"
    TEAM_LEAD = "team_lead"
    SPECIALIST = "specialist"


class ModelTier(str, Enum):
    SONNET = "sonnet"   # Default — all agents
    OPUS = "opus"       # High-stakes agents (complex reasoning, critical decisions)


class AgentConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    role: AgentRole
    title: str
    specialization: str
    goal: str
    backstory: str
    team_id: Optional[str] = None
    parent_id: Optional[str] = None
    status: AgentStatus = AgentStatus.PENDING
    skills_path: Optional[str] = None
    workspace_path: Optional[str] = None
    tools: list[str] = Field(default_factory=list)

    # Model configuration
    model_tier: ModelTier = ModelTier.SONNET
    # max_iter: max think→act→observe cycles per task.
    # Too low = incomplete work. Too high = circular reasoning waste.
    # Realistic range: 10-20 depending on task complexity.
    max_iter: int = 15
    max_tokens: int = 8192    # Max output tokens per agent response


class AgentResponse(BaseModel):
    id: str
    name: str
    role: AgentRole
    title: str
    specialization: str
    status: AgentStatus
    team_id: Optional[str] = None
    parent_id: Optional[str] = None
    workspace_path: Optional[str] = None
    tools: list[str] = []
    model_tier: ModelTier = ModelTier.SONNET
    max_iter: int = 5


class AgentModelUpdate(BaseModel):
    model_tier: ModelTier
