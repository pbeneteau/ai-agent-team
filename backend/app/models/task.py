from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskExecutionMode(str, Enum):
    AUTO = "auto"
    STANDALONE = "standalone"
    DEPENDENCY_GRAPH = "dependency_graph"


class TaskExecutionEligibility(str, Enum):
    ELIGIBLE = "eligible"
    CLARIFICATION_REQUIRED = "clarification_required"
    INELIGIBLE = "ineligible"


class TaskPlanStatus(str, Enum):
    NOT_PLANNED = "not_planned"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskNodeStatus(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskNodeType(str, Enum):
    SINGLE_AGENT = "single_agent"
    SPECIALIST = "specialist"
    LEAD_COMPILE = "lead_compile"


class TaskProgressEntry(BaseModel):
    timestamp: str
    message: str
    agent: Optional[str] = None
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    node_id: Optional[str] = None
    stage: Optional[str] = None
    structured_flow: Optional[str] = None
    structured_channel: Optional[str] = None


class TaskExecutionNode(BaseModel):
    id: str
    title: str
    description: str
    node_type: TaskNodeType
    status: TaskNodeStatus = TaskNodeStatus.PENDING
    assigned_agent_id: Optional[str] = None
    assigned_agent_name: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    error_traceback: Optional[str] = None
    failure_stage: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    sources: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TaskExecutionPlan(BaseModel):
    status: TaskPlanStatus = TaskPlanStatus.NOT_PLANNED
    mode: TaskExecutionMode = TaskExecutionMode.AUTO
    compiler_agent_id: Optional[str] = None
    compiler_agent_name: Optional[str] = None
    planning_notes: str = ""
    nodes: list[TaskExecutionNode] = Field(default_factory=list)


class TaskDeliverable(BaseModel):
    path: str
    name: str
    type: str
    size_bytes: int
    modified_at: str


class TaskCreate(BaseModel):
    title: str
    description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_team_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    execution_mode: TaskExecutionMode = TaskExecutionMode.AUTO
    context_document_ids: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    assigned_team_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    assigned_agent_ids: list[str] = Field(default_factory=list)
    execution_mode: TaskExecutionMode = TaskExecutionMode.AUTO
    context_document_ids: list[str] = Field(default_factory=list)
    execution_plan: TaskExecutionPlan = Field(default_factory=TaskExecutionPlan)
    result: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    error_traceback: Optional[str] = None
    failure_stage: Optional[str] = None
    brief_revision: Optional[int] = None
    brief_fingerprint: Optional[str] = None
    created_at: str
    updated_at: str
    execution_eligibility: TaskExecutionEligibility = TaskExecutionEligibility.ELIGIBLE
    execution_blockers: list[str] = Field(default_factory=list)
    progress_log: list[TaskProgressEntry] = Field(default_factory=list)
    deliverables_dir: Optional[str] = None
    deliverables: list[TaskDeliverable] = Field(default_factory=list)
    # Provenance and reliability metadata
    sources: list[str] = Field(default_factory=list)        # Cited URLs and publications from the result
    assumptions: list[str] = Field(default_factory=list)    # Assumptions / TBDs flagged by the agents
    warnings: list[str] = Field(default_factory=list)       # Unverified claims or missing evidence flagged by agents


class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    result: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    error_traceback: Optional[str] = None
    failure_stage: Optional[str] = None
    progress_entry: Optional[TaskProgressEntry] = None
