from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.models.agent import ModelTier
from app.models.task import TaskExecutionMode, TaskPriority


class PlanKind(str, Enum):
    TASK = "task"
    TEAM = "team"


class PlanState(str, Enum):
    DISCOVERY = "discovery"
    DRAFT = "draft"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PlanFieldType(str, Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"


class PlanValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class PlanValidationStatus(str, Enum):
    VALID = "valid"
    NEEDS_CLARIFICATION = "needs_clarification"
    INVALID = "invalid"


class PlanExecutionEligibility(str, Enum):
    ELIGIBLE = "eligible"
    CLARIFICATION_REQUIRED = "clarification_required"
    INELIGIBLE = "ineligible"


class PlanField(BaseModel):
    id: str
    label: str
    type: PlanFieldType
    placeholder: str = ""
    options: list[str] = Field(default_factory=list)
    required: bool = False


class PlanForm(BaseModel):
    title: str
    description: str = ""
    fields: list[PlanField] = Field(default_factory=list)


class PlanValidationIssue(BaseModel):
    id: str
    field_path: str
    label: str
    message: str
    severity: PlanValidationSeverity = PlanValidationSeverity.BLOCKING
    requires_user_input: bool = False
    input_type: PlanFieldType = PlanFieldType.TEXT
    options: list[str] = Field(default_factory=list)
    current_value: Optional[str] = None


class PlanDraftBase(BaseModel):
    id: str
    session_id: str
    kind: PlanKind
    state: PlanState = PlanState.DRAFT
    revision: int = 1
    title: str
    summary: str = ""
    description: str = ""
    questions: list[str] = Field(default_factory=list)
    blocking_questions: list[str] = Field(default_factory=list)
    validation_issues: list[PlanValidationIssue] = Field(default_factory=list)
    validation_status: PlanValidationStatus = PlanValidationStatus.VALID
    execution_eligibility: PlanExecutionEligibility = PlanExecutionEligibility.ELIGIBLE
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskPlanDraft(PlanDraftBase):
    kind: Literal[PlanKind.TASK] = PlanKind.TASK
    task_title: str
    task_description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    execution_mode: TaskExecutionMode = TaskExecutionMode.AUTO
    assigned_team_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    assigned_team_name: Optional[str] = None
    assigned_agent_name: Optional[str] = None
    context_document_ids: list[str] = Field(default_factory=list, max_length=8)


class TeamPlanAgentDraft(BaseModel):
    name: str = Field(max_length=60)
    title: str = Field(max_length=100)
    specialization: str = Field(max_length=80)
    goal: str = Field(default="", max_length=180)
    backstory: str = Field(default="", max_length=220)
    is_lead: bool = False
    model_tier: ModelTier


class TeamPlanTeamDraft(BaseModel):
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=180)
    domain: str = Field(default="", max_length=80)
    agents: list[TeamPlanAgentDraft] = Field(default_factory=list, max_length=4)


class TeamPlanProjectDraft(BaseModel):
    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=700)
    domain: str = Field(default="", max_length=100)
    short_term_goal: str = Field(default="", max_length=240)


class TeamPlanDraft(PlanDraftBase):
    kind: Literal[PlanKind.TEAM] = PlanKind.TEAM
    project: TeamPlanProjectDraft = Field(default_factory=TeamPlanProjectDraft)
    teams: list[TeamPlanTeamDraft] = Field(default_factory=list)


PlanDraft = Annotated[Union[TaskPlanDraft, TeamPlanDraft], Field(discriminator="kind")]


class PlanSessionState(BaseModel):
    session_id: str
    kind: Optional[PlanKind] = None
    state: PlanState = PlanState.DISCOVERY
    form: Optional[PlanForm] = None
    draft: Optional[PlanDraft] = None
    last_error: Optional[str] = None
