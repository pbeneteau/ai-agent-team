from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
import uuid

from app.models.git_providers import AgentGitBinding, AgentGitBindingResolved
from app.models.mcp import AgentMcpToolBinding, AgentMcpToolBindingResolved


class AgentStatus(str, Enum):
    PENDING = "pending"
    LEARNING = "learning"
    READY = "ready"
    WORKING = "working"
    ERROR = "error"


class AgentOccupancyStatus(str, Enum):
    IDLE = "idle"
    ASSIGNED = "assigned"
    BUSY = "busy"


class AgentOccupancyReason(str, Enum):
    TASK_EXECUTION = "task_execution"
    LEARNING = "learning"
    RESEARCH = "research"
    REBRIEFING = "rebriefing"
    PROJECT_BRIEFING = "project_briefing"


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
    occupancy_status: AgentOccupancyStatus = AgentOccupancyStatus.IDLE
    occupancy_reason: Optional[AgentOccupancyReason] = None
    current_task_id: Optional[str] = None
    current_task_title: Optional[str] = None
    current_node_id: Optional[str] = None
    current_node_title: Optional[str] = None
    busy_since: Optional[str] = None
    skills_path: Optional[str] = None
    workspace_path: Optional[str] = None
    tools: list[str] = Field(default_factory=list)
    git_bindings: list[AgentGitBinding] = Field(default_factory=list)
    mcp_tool_bindings: list[AgentMcpToolBinding] = Field(default_factory=list)

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
    goal: str = ""
    backstory: str = ""
    status: AgentStatus
    occupancy_status: AgentOccupancyStatus = AgentOccupancyStatus.IDLE
    occupancy_reason: Optional[AgentOccupancyReason] = None
    current_task_id: Optional[str] = None
    current_task_title: Optional[str] = None
    current_node_id: Optional[str] = None
    current_node_title: Optional[str] = None
    busy_since: Optional[str] = None
    team_id: Optional[str] = None
    parent_id: Optional[str] = None
    workspace_path: Optional[str] = None
    tools: list[str] = []
    git_bindings: list[AgentGitBindingResolved] = []
    mcp_tool_bindings: list[AgentMcpToolBindingResolved] = []
    model_tier: ModelTier = ModelTier.SONNET
    max_iter: int = 5


class AgentLearningProfile(BaseModel):
    agent_id: str
    completed_task_nodes: int = 0
    avg_quality_score: Optional[float] = None
    last_5_learnings: list[str] = Field(default_factory=list)
    readiness_score: Optional[int] = None
    progression_level: str = "apprenti"  # apprenti | operationnel | expert
    last_reflection_at: Optional[str] = None
    episode_count: int = 0


class AgentModelUpdate(BaseModel):
    model_tier: ModelTier


def build_agent_status_payload(agent: AgentConfig) -> dict:
    return {
        "agent_id": agent.id,
        "name": agent.name,
        "status": agent.status.value,
        "occupancy_status": agent.occupancy_status.value,
        "occupancy_reason": agent.occupancy_reason.value if agent.occupancy_reason else None,
        "current_task_id": agent.current_task_id,
        "current_task_title": agent.current_task_title,
        "current_node_id": agent.current_node_id,
        "current_node_title": agent.current_node_title,
        "busy_since": agent.busy_since,
        "workspace_path": agent.workspace_path,
    }
