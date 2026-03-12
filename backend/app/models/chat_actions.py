from copy import deepcopy
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.models.plan import PlanField, PlanKind, TeamPlanProjectDraft, TeamPlanTeamDraft
from app.models.task import TaskExecutionMode, TaskPriority


class StartTeamBuilderAction(BaseModel):
    action: Literal["start_team_builder"] = "start_team_builder"


class GatherInfoAction(BaseModel):
    action: Literal["gather_info"] = "gather_info"
    title: str = Field(max_length=120)
    description: str = Field(default="", max_length=240)
    fields: list[PlanField] = Field(default_factory=list)


class TaskPlanProposalAction(BaseModel):
    action: Literal["plan_task", "plan_mode", "create_task"] = "plan_task"
    kind: Literal[PlanKind.TASK] = PlanKind.TASK
    title: str = Field(max_length=120)
    description: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=160)
    plan_rationale: str = Field(default="", max_length=220)
    questions: list[str] = Field(default_factory=list, max_length=3)
    blocking_questions: list[str] = Field(default_factory=list, max_length=3)
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    execution_mode: TaskExecutionMode = TaskExecutionMode.AUTO
    context_document_ids: list[str] = Field(default_factory=list, max_length=8)


class TeamPlanProposalAction(BaseModel):
    action: Literal["plan_team", "plan_mode", "create_team_direct"] = "plan_team"
    kind: Literal[PlanKind.TEAM] = PlanKind.TEAM
    title: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=180)
    plan_rationale: str = Field(default="", max_length=220)
    questions: list[str] = Field(default_factory=list, max_length=3)
    blocking_questions: list[str] = Field(default_factory=list, max_length=3)
    project: TeamPlanProjectDraft = Field(default_factory=TeamPlanProjectDraft)
    teams: list[TeamPlanTeamDraft] = Field(default_factory=list)


class TriggerLearningAction(BaseModel):
    action: Literal["trigger_learning"] = "trigger_learning"
    agent_ids: list[str] = Field(default_factory=list, max_length=8)
    team_ids: list[str] = Field(default_factory=list, max_length=8)
    agent_names: list[str] = Field(default_factory=list, max_length=8)
    team_names: list[str] = Field(default_factory=list, max_length=8)
    reason: str = Field(default="", max_length=180)


AssistantAction = Union[
    StartTeamBuilderAction,
    GatherInfoAction,
    TaskPlanProposalAction,
    TeamPlanProposalAction,
    TriggerLearningAction,
]


_TOOL_REGISTRY: dict[str, tuple[type[BaseModel], dict[str, Any], str]] = {
    "start_team_builder": (
        StartTeamBuilderAction,
        {"action": "start_team_builder"},
        "Use when the user explicitly wants to switch to the dedicated team-building workspace.",
    ),
    "gather_info": (
        GatherInfoAction,
        {"action": "gather_info"},
        "Collect structured answers from the user with a form instead of continuing in free-form chat.",
    ),
    "propose_task_plan": (
        TaskPlanProposalAction,
        {"action": "plan_task", "kind": PlanKind.TASK.value},
        "Propose a task plan draft for user validation. Do not execute the task.",
    ),
    "propose_team_plan": (
        TeamPlanProposalAction,
        {"action": "plan_team", "kind": PlanKind.TEAM.value},
        "Propose a team design draft for user validation. Do not create the team.",
    ),
    "trigger_learning": (
        TriggerLearningAction,
        {"action": "trigger_learning"},
        "Trigger a learning refresh for one or more existing agents or teams when necessary.",
    ),
}


def _tool_input_schema(model: type[BaseModel], *, excluded_fields: set[str]) -> dict[str, Any]:
    schema = deepcopy(model.model_json_schema())
    properties = schema.get("properties", {})
    for field_name in excluded_fields:
        properties.pop(field_name, None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [field for field in required if field not in excluded_fields]
    return schema


def build_assistant_action_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name, (model, defaults, description) in _TOOL_REGISTRY.items():
        excluded_fields = set(defaults.keys())
        tools.append(
            {
                "name": name,
                "description": description,
                "input_schema": _tool_input_schema(model, excluded_fields=excluded_fields),
            }
        )
    return tools


def action_from_tool_use(tool_name: str, tool_input: dict[str, Any] | None) -> AssistantAction:
    tool_spec = _TOOL_REGISTRY.get(tool_name)
    if not tool_spec:
        raise ValueError(f"Unsupported assistant tool: {tool_name}")
    model, defaults, _ = tool_spec
    payload = {**defaults, **(tool_input or {})}
    return model.model_validate(payload)


def action_from_payload(payload: dict[str, Any]) -> AssistantAction:
    action_name = str(payload.get("action") or "").strip()
    if action_name == "gather_info":
        return GatherInfoAction.model_validate(payload)
    if action_name == "start_team_builder":
        return StartTeamBuilderAction.model_validate(payload)
    if action_name == "trigger_learning":
        return TriggerLearningAction.model_validate(payload)
    if action_name in {"plan_task", "plan_mode", "create_task"}:
        normalized = {**payload}
        normalized.setdefault("kind", PlanKind.TASK.value)
        if normalized.get("kind") == PlanKind.TASK.value:
            return TaskPlanProposalAction.model_validate(normalized)
    if action_name in {"plan_team", "plan_mode", "create_team_direct"}:
        normalized = {**payload}
        normalized.setdefault("kind", PlanKind.TEAM.value)
        if normalized.get("kind") == PlanKind.TEAM.value:
            return TeamPlanProposalAction.model_validate(normalized)
    raise ValueError(f"Unsupported assistant action payload: {action_name or 'missing action'}")
