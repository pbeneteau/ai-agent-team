import asyncio
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from app.agents.specialists.templates import AGENT_TEMPLATES, TEAM_TEMPLATES
from app.core.agent_factory import get_agent_factory
from app.core.learning import run_learning_phase_for_team
from app.core.orchestrator import get_orchestrator
from app.memory.project_context import get_project_context_store
from app.models.chat_actions import GatherInfoAction, TaskPlanProposalAction, TeamPlanProposalAction
from app.models.plan import (
    PlanExecutionEligibility,
    PlanDraft,
    PlanField,
    PlanForm,
    PlanKind,
    PlanSessionState,
    PlanState,
    PlanValidationIssue,
    PlanValidationSeverity,
    PlanValidationStatus,
    TaskPlanDraft,
    TeamPlanAgentDraft,
    TeamPlanDraft,
    TeamPlanProjectDraft,
    TeamPlanTeamDraft,
)
from app.models.task import TaskExecutionMode, TaskPriority


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class PlanClarificationRequiredError(ValueError):
    def __init__(self, message: str, *, draft: PlanDraft):
        super().__init__(message)
        self.draft = draft


def _dedupe_issue_options(options: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for option in options:
        value = str(option or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _blocking_issue(
    *,
    issue_id: str,
    field_path: str,
    label: str,
    message: str,
    requires_user_input: bool = False,
    input_type: str = "text",
    options: list[str] | None = None,
    current_value: str | None = None,
) -> PlanValidationIssue:
    return PlanValidationIssue(
        id=issue_id,
        field_path=field_path,
        label=label,
        message=message,
        severity=PlanValidationSeverity.BLOCKING,
        requires_user_input=requires_user_input,
        input_type=input_type,
        options=_dedupe_issue_options(options or []),
        current_value=(current_value or "").strip() or None,
    )


def _legacy_blocking_issues(blocking_questions: list[str]) -> list[PlanValidationIssue]:
    issues: list[PlanValidationIssue] = []
    for index, question in enumerate(blocking_questions):
        text = str(question or "").strip()
        if not text:
            continue
        issues.append(
            _blocking_issue(
                issue_id=f"blocking_question:{index}",
                field_path="draft",
                label="Point bloquant",
                message=text,
            )
        )
    return issues


def _finalize_validated_draft(draft: PlanDraft, *, issues: list[PlanValidationIssue], updates: dict[str, Any]) -> PlanDraft:
    deduped: dict[str, PlanValidationIssue] = {}
    for issue in issues:
        if issue.id in deduped:
            continue
        deduped[issue.id] = issue
    final_issues = list(deduped.values())
    blocking_issues = [issue for issue in final_issues if issue.severity == PlanValidationSeverity.BLOCKING]
    blocking_questions = [issue.message for issue in blocking_issues]
    if not blocking_issues:
        validation_status = PlanValidationStatus.VALID
        execution_eligibility = PlanExecutionEligibility.ELIGIBLE
    elif any(issue.requires_user_input for issue in blocking_issues):
        validation_status = PlanValidationStatus.NEEDS_CLARIFICATION
        execution_eligibility = PlanExecutionEligibility.CLARIFICATION_REQUIRED
    else:
        validation_status = PlanValidationStatus.INVALID
        execution_eligibility = PlanExecutionEligibility.INELIGIBLE

    return draft.model_copy(
        update={
            **updates,
            "validation_issues": final_issues,
            "validation_status": validation_status,
            "execution_eligibility": execution_eligibility,
            "blocking_questions": blocking_questions,
        }
    )


@dataclass
class UniversalPlanSession:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    state: PlanState = PlanState.DISCOVERY
    kind: Optional[PlanKind] = None
    form: Optional[PlanForm] = None
    draft: Optional[PlanDraft] = None
    last_error: Optional[str] = None
    execution_draft_id: Optional[str] = None
    completed_draft_id: Optional[str] = None
    completed_payload: Optional[dict[str, Any]] = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def export(self) -> PlanSessionState:
        return PlanSessionState(
            session_id=self.session_id,
            kind=self.kind,
            state=self.state,
            form=self.form,
            draft=self.draft,
            last_error=self.last_error,
        )

    def _reset_execution_state(self):
        self.last_error = None
        self.execution_draft_id = None
        self.completed_draft_id = None
        self.completed_payload = None

    def _next_revision(self) -> int:
        if not self.draft:
            return 1
        return self.draft.revision + 1

    def _set_draft(self, draft: PlanDraft) -> PlanDraft:
        synchronized = draft.model_copy(update={"state": self.state})
        self.draft = synchronized
        self.updated_at = _now_iso()
        return synchronized

    def set_form(self, *, title: str, description: str = "", fields: list[PlanField | dict[str, Any]]) -> PlanForm:
        self.kind = None
        self.state = PlanState.DISCOVERY
        self._reset_execution_state()
        self.draft = None
        self.form = PlanForm(
            title=title,
            description=description,
            fields=[
                field if isinstance(field, PlanField) else PlanField.model_validate(field)
                for field in fields
            ],
        )
        self.updated_at = _now_iso()
        return self.form

    def set_form_from_action(self, action: GatherInfoAction) -> PlanForm:
        return self.set_form(
            title=action.title,
            description=action.description,
            fields=action.fields,
        )

    def set_task_draft(
        self,
        action: TaskPlanProposalAction | dict[str, Any],
        tagged_doc_ids: list[str] | None = None,
    ) -> TaskPlanDraft:
        normalized_action = (
            action
            if isinstance(action, TaskPlanProposalAction)
            else TaskPlanProposalAction.model_validate(action)
        )
        tagged = tagged_doc_ids or []
        title = normalized_action.title.strip() or "Nouvelle tâche"
        description = normalized_action.description.strip()
        draft = TaskPlanDraft(
            id=uuid4().hex,
            session_id=self.session_id,
            state=PlanState.AWAITING_CONFIRMATION,
            revision=self._next_revision(),
            title=title,
            summary=normalized_action.summary or description[:240],
            description=normalized_action.plan_rationale,
            questions=list(normalized_action.questions),
            blocking_questions=list(normalized_action.blocking_questions),
            task_title=title,
            task_description=description,
            priority=normalized_action.priority,
            execution_mode=normalized_action.execution_mode,
            assigned_team_id=normalized_action.team_id,
            assigned_agent_id=normalized_action.agent_id,
            assigned_team_name=normalized_action.team_name,
            assigned_agent_name=normalized_action.agent_name,
            context_document_ids=list(normalized_action.context_document_ids or tagged),
            metadata={
                "needs_confirmation": True,
                "source_action": normalized_action.action,
                "source_blocking_questions": list(normalized_action.blocking_questions),
            },
        )
        self.kind = PlanKind.TASK
        self.state = PlanState.AWAITING_CONFIRMATION
        self.form = None
        self._reset_execution_state()
        validated = validate_task_draft(draft)
        return self._set_draft(validated)

    def set_team_draft(self, action: TeamPlanProposalAction | dict[str, Any]) -> TeamPlanDraft:
        if isinstance(action, TeamPlanProposalAction):
            project = action.project
            teams = action.teams
            summary = action.summary
            plan_rationale = action.plan_rationale
            questions = list(action.questions)
            blocking_questions = list(action.blocking_questions)
            source_action = action.action
        else:
            project = TeamPlanProjectDraft.model_validate(action.get("project", {}) or {})
            teams = action.get("teams", []) or []
            summary = str(action.get("summary", "") or "")
            plan_rationale = str(action.get("plan_rationale", "") or "")
            questions = list(action.get("questions") or [])
            blocking_questions = list(action.get("blocking_questions") or [])
            source_action = str(action.get("action") or "plan_team")
        normalized_teams: list[TeamPlanTeamDraft] = []
        for team_spec in teams:
            if isinstance(team_spec, dict) and team_spec.get("template") in TEAM_TEMPLATES and "agents" not in team_spec:
                template_key = team_spec["template"]
                template = TEAM_TEMPLATES[template_key]
                agents = [
                    TeamPlanAgentDraft(
                        name=agent_template.get("title", "Agent"),
                        title=agent_template.get("title", ""),
                        specialization=agent_template.get("specialization", ""),
                        goal=agent_template.get("goal", ""),
                        backstory=agent_template.get("backstory", ""),
                        is_lead=index == 0,
                        model_tier="sonnet",
                    )
                    for index, role in enumerate(template.get("agent_roles", []))
                    for agent_template in [AGENT_TEMPLATES[role]]
                ]
                normalized_teams.append(
                    TeamPlanTeamDraft(
                        name=template.get("name", "Team"),
                        description=template.get("description", ""),
                        domain=template.get("domain", ""),
                        agents=agents,
                    )
                )
                continue

            normalized_teams.append(
                team_spec if isinstance(team_spec, TeamPlanTeamDraft) else TeamPlanTeamDraft.model_validate(team_spec)
            )

        project_name = project.name.strip() or "Unnamed Project"
        draft = TeamPlanDraft(
            id=uuid4().hex,
            session_id=self.session_id,
            state=PlanState.AWAITING_CONFIRMATION,
            revision=self._next_revision(),
            title=project_name,
            summary=summary or project.description[:240],
            description=plan_rationale,
            questions=questions,
            blocking_questions=blocking_questions,
            project=TeamPlanProjectDraft(
                name=project_name,
                description=project.description,
                domain=project.domain,
                short_term_goal=project.short_term_goal,
            ),
            teams=normalized_teams,
            metadata={
                "needs_confirmation": True,
                "source_action": source_action,
                "source_blocking_questions": list(blocking_questions),
            },
        )
        self.kind = PlanKind.TEAM
        self.state = PlanState.AWAITING_CONFIRMATION
        self.form = None
        self._reset_execution_state()
        validated = validate_team_draft(draft)
        return self._set_draft(validated)

    def cancel(self):
        self.kind = None
        self.form = None
        self.draft = None
        self.state = PlanState.CANCELLED
        self._reset_execution_state()
        self.updated_at = _now_iso()

    def mark_revising(self):
        self.state = PlanState.DISCOVERY
        self.form = None
        self.draft = None
        self.last_error = None
        self.execution_draft_id = None
        self.updated_at = _now_iso()

    def mark_executing(self, draft_id: str):
        self.state = PlanState.EXECUTING
        self.execution_draft_id = draft_id
        self.last_error = None
        if self.draft:
            self.draft = self.draft.model_copy(update={"state": self.state})
        self.updated_at = _now_iso()

    def mark_completed(self, draft_id: str, payload: dict[str, Any]):
        self.state = PlanState.COMPLETED
        self.completed_draft_id = draft_id
        self.completed_payload = payload
        self.execution_draft_id = None
        if self.draft:
            self.draft = self.draft.model_copy(update={"state": self.state})
        self.updated_at = _now_iso()

    def mark_failed(self, error: str):
        self.state = PlanState.FAILED
        self.last_error = error
        self.execution_draft_id = None
        if self.draft:
            self.draft = self.draft.model_copy(update={"state": self.state})
        self.updated_at = _now_iso()

    def mark_clarification_required(self, draft: PlanDraft, error: str):
        self.state = PlanState.AWAITING_CONFIRMATION
        self.last_error = error
        self.execution_draft_id = None
        self._set_draft(draft)

    def apply_clarification_values(self, values: dict[str, str]) -> PlanDraft:
        if not self.draft or not self.kind:
            raise ValueError("No plan draft available")
        if not values:
            return self.draft

        if isinstance(self.draft, TaskPlanDraft):
            updated = _apply_task_clarification_values(self.draft, values)
            validated = validate_task_draft(updated)
        elif isinstance(self.draft, TeamPlanDraft):
            updated = _apply_team_clarification_values(self.draft, values)
            validated = validate_team_draft(updated)
        else:
            raise ValueError("Unsupported plan draft type")

        self.state = PlanState.AWAITING_CONFIRMATION
        self.last_error = None
        return self._set_draft(validated)

    def can_confirm(self, *, session_id: str, draft_id: str) -> tuple[bool, Optional[dict[str, Any]]]:
        if session_id != self.session_id:
            raise ValueError("Plan session obsolete")
        if self.completed_draft_id == draft_id and self.completed_payload is not None:
            return False, self.completed_payload
        if self.state == PlanState.EXECUTING and self.execution_draft_id == draft_id:
            raise ValueError("Plan execution already in progress")
        if self.state != PlanState.AWAITING_CONFIRMATION:
            raise ValueError("Plan is not awaiting confirmation")
        if not self.draft or not self.kind:
            raise ValueError("No plan draft available")
        if self.draft.id != draft_id:
            raise ValueError("Plan draft obsolete")
        if self.draft.execution_eligibility != PlanExecutionEligibility.ELIGIBLE:
            raise ValueError("Plan is not eligible for confirmation")
        return True, None

    def validate_before_execute(self):
        if not self.draft or not self.kind:
            raise ValueError("No plan draft available")
        if self.kind == PlanKind.TASK and not isinstance(self.draft, TaskPlanDraft):
            raise ValueError("Task plan draft is invalid")
        if self.kind == PlanKind.TEAM and not isinstance(self.draft, TeamPlanDraft):
            raise ValueError("Team plan draft is invalid")
        if isinstance(self.draft, TaskPlanDraft):
            validated = validate_task_draft(self.draft)
        else:
            validated = validate_team_draft(self.draft)
        self.state = PlanState.AWAITING_CONFIRMATION
        self._set_draft(validated)
        if validated.execution_eligibility != PlanExecutionEligibility.ELIGIBLE:
            blocking = [i for i in validated.validation_issues if i.severity == "blocking"]
            if blocking:
                details = "; ".join(i.message for i in blocking[:3])
                raise PlanClarificationRequiredError(
                    f"Le plan nécessite des clarifications avant d'être lancé : {details}",
                    draft=validated,
                )
            raise PlanClarificationRequiredError(
                "Le plan nécessite des clarifications avant d'être lancé.", draft=validated
            )


def _match_by_name(items: list[Any], name: str) -> Any | None:
    normalized = name.strip().lower()
    for item in items:
        if getattr(item, "name", "").strip().lower() == normalized:
            return item
    return None


def _apply_task_clarification_values(draft: TaskPlanDraft, values: dict[str, str]) -> TaskPlanDraft:
    factory = get_agent_factory()
    update: dict[str, Any] = {}
    for field_path, raw_value in values.items():
        value = str(raw_value or "").strip()
        if not value:
            continue
        if field_path == "assigned_target":
            team = _match_by_name(factory.list_teams(), value)
            if team:
                update["assigned_team_id"] = team.id
                update["assigned_team_name"] = team.name
                update["assigned_agent_id"] = None
                update["assigned_agent_name"] = None
                continue
            agent = _match_by_name(factory.list_agents(), value)
            if agent:
                update["assigned_agent_id"] = agent.id
                update["assigned_agent_name"] = agent.name
                update["assigned_team_id"] = agent.team_id
                team = factory.get_team(agent.team_id) if agent.team_id else None
                update["assigned_team_name"] = team.name if team else None
                continue
        elif field_path == "assigned_team_name":
            update["assigned_team_name"] = value
            update["assigned_team_id"] = None
        elif field_path == "assigned_agent_name":
            update["assigned_agent_name"] = value
            update["assigned_agent_id"] = None
        elif field_path in {"task_title", "task_description", "title", "summary", "description"}:
            update[field_path] = value
    return draft.model_copy(update=update)


def _apply_team_clarification_values(draft: TeamPlanDraft, values: dict[str, str]) -> TeamPlanDraft:
    project = draft.project.model_copy(deep=True)
    teams = [team.model_copy(deep=True) for team in draft.teams]
    for field_path, raw_value in values.items():
        value = str(raw_value or "").strip()
        if not value:
            continue
        if field_path.startswith("project."):
            attr = field_path.split(".", 1)[1]
            if hasattr(project, attr):
                project = project.model_copy(update={attr: value})
            continue
        team_match = re.match(r"^teams\[(\d+)\]\.(.+)$", field_path)
        if not team_match:
            continue
        team_index = int(team_match.group(1))
        if team_index >= len(teams):
            continue
        suffix = team_match.group(2)
        team = teams[team_index]
        if suffix in {"name", "description", "domain"}:
            teams[team_index] = team.model_copy(update={suffix: value})
            continue
        if suffix == "lead":
            normalized = value.lower()
            updated_agents = []
            for agent in team.agents:
                updated_agents.append(agent.model_copy(update={"is_lead": agent.name.strip().lower() == normalized}))
            teams[team_index] = team.model_copy(update={"agents": updated_agents})
            continue
        agent_match = re.match(r"^agents\[(\d+)\]\.(.+)$", suffix)
        if not agent_match:
            continue
        agent_index = int(agent_match.group(1))
        agent_attr = agent_match.group(2)
        if agent_index >= len(team.agents):
            continue
        if agent_attr not in {"name", "title", "specialization", "goal", "backstory"}:
            continue
        updated_agents = list(team.agents)
        updated_agents[agent_index] = updated_agents[agent_index].model_copy(update={agent_attr: value})
        teams[team_index] = team.model_copy(update={"agents": updated_agents})
    return draft.model_copy(update={"project": project, "teams": teams})


def validate_task_draft(draft: TaskPlanDraft) -> TaskPlanDraft:
    factory = get_agent_factory()
    assigned_team_id = draft.assigned_team_id
    assigned_agent_id = draft.assigned_agent_id
    assigned_team_name = draft.assigned_team_name
    assigned_agent_name = draft.assigned_agent_name
    issues = _legacy_blocking_issues(list(draft.metadata.get("source_blocking_questions") or []))
    teams = factory.list_teams()
    target_options = _dedupe_issue_options(
        [team.name for team in teams]
        + [
            agent.name
            for agent in factory.list_agents()
            if getattr(getattr(agent, "role", None), "value", None) != "associate"
        ]
    )

    if assigned_team_id:
        team = factory.get_team(assigned_team_id)
        if not team:
            issues.append(
                _blocking_issue(
                    issue_id="assigned_team",
                    field_path="assigned_team_name",
                    label="Équipe cible",
                    message="L'équipe sélectionnée n'est plus disponible.",
                    requires_user_input=True,
                    options=[team.name for team in teams],
                    current_value=assigned_team_name or assigned_team_id,
                )
            )
            assigned_team_id = None
        else:
            assigned_team_name = assigned_team_name or team.name
    elif assigned_team_name:
        team = _match_by_name(factory.list_teams(), assigned_team_name)
        if not team:
            issues.append(
                _blocking_issue(
                    issue_id="assigned_team",
                    field_path="assigned_team_name",
                    label="Équipe cible",
                    message="L'équipe indiquée ne peut pas être résolue.",
                    requires_user_input=True,
                    options=[team.name for team in teams],
                    current_value=assigned_team_name,
                )
            )
        else:
            assigned_team_id = team.id
            assigned_team_name = team.name

    if assigned_agent_id:
        agent = factory.get_agent(assigned_agent_id)
        if not agent:
            issues.append(
                _blocking_issue(
                    issue_id="assigned_agent",
                    field_path="assigned_agent_name",
                    label="Agent cible",
                    message="L'agent sélectionné n'est plus disponible.",
                    requires_user_input=True,
                    options=target_options,
                    current_value=assigned_agent_name or assigned_agent_id,
                )
            )
            assigned_agent_id = None
        else:
            assigned_agent_name = assigned_agent_name or agent.name
    elif assigned_agent_name:
        agent = _match_by_name(factory.list_agents(), assigned_agent_name)
        if not agent:
            issues.append(
                _blocking_issue(
                    issue_id="assigned_agent",
                    field_path="assigned_agent_name",
                    label="Agent cible",
                    message="L'agent indiqué ne peut pas être résolu.",
                    requires_user_input=True,
                    options=target_options,
                    current_value=assigned_agent_name,
                )
            )
        else:
            assigned_agent_id = agent.id
            assigned_agent_name = agent.name

    if assigned_team_id and assigned_agent_id:
        agent = factory.get_agent(assigned_agent_id)
        if not agent or agent.team_id != assigned_team_id:
            issues.append(
                _blocking_issue(
                    issue_id="assigned_target_consistency",
                    field_path="assigned_target",
                    label="Cible d'exécution",
                    message="L'agent sélectionné n'appartient pas à l'équipe choisie.",
                    requires_user_input=True,
                    input_type="select",
                    options=target_options,
                    current_value=assigned_agent_name or assigned_team_name,
                )
            )

    if not assigned_team_id and not assigned_agent_id:
        if len(teams) == 1:
            assigned_team_id = teams[0].id
            assigned_team_name = teams[0].name
        else:
            issues.append(
                _blocking_issue(
                    issue_id="assigned_target",
                    field_path="assigned_target",
                    label="Cible d'exécution",
                    message="La tâche doit cibler une équipe ou un agent valide avant confirmation.",
                    requires_user_input=True,
                    input_type="select",
                    options=target_options,
                )
            )

    return _finalize_validated_draft(
        draft,
        issues=issues,
        updates={
            "assigned_team_id": assigned_team_id,
            "assigned_team_name": assigned_team_name,
            "assigned_agent_id": assigned_agent_id,
            "assigned_agent_name": assigned_agent_name,
        },
    )


def validate_team_draft(draft: TeamPlanDraft) -> TeamPlanDraft:
    issues = _legacy_blocking_issues(list(draft.metadata.get("source_blocking_questions") or []))
    if not draft.project.name.strip():
        issues.append(
            _blocking_issue(
                issue_id="project_name",
                field_path="project.name",
                label="Nom du projet",
                message="Le nom du projet est requis.",
                requires_user_input=True,
                current_value=draft.project.name,
            )
        )
    if not draft.teams:
        issues.append(
            _blocking_issue(
                issue_id="teams_missing",
                field_path="teams",
                label="Équipes",
                message="Le plan d'équipe doit inclure au moins une équipe.",
            )
        )

    for team_index, team in enumerate(draft.teams):
        team_label = team.name or f"équipe {team_index + 1}"
        if not team.name.strip():
            issues.append(
                _blocking_issue(
                    issue_id=f"team_name:{team_index}",
                    field_path=f"teams[{team_index}].name",
                    label=f"Nom de l'équipe {team_index + 1}",
                    message="Chaque équipe doit avoir un nom.",
                    requires_user_input=True,
                    current_value=team.name,
                )
            )
        if not team.agents:
            issues.append(
                _blocking_issue(
                    issue_id=f"team_agents:{team_index}",
                    field_path=f"teams[{team_index}].agents",
                    label=f"Agents de {team_label}",
                    message=f"L'équipe '{team_label}' doit inclure au moins un agent.",
                )
            )
        lead_count = sum(1 for agent in team.agents if agent.is_lead)
        if lead_count != 1:
            issues.append(
                _blocking_issue(
                    issue_id=f"team_lead:{team_index}",
                    field_path=f"teams[{team_index}].lead",
                    label=f"Lead de {team_label}",
                    message=f"L'équipe '{team_label}' doit inclure exactement un lead.",
                    requires_user_input=bool(team.agents),
                    input_type="select",
                    options=[agent.name for agent in team.agents],
                    current_value=next((agent.name for agent in team.agents if agent.is_lead), None),
                )
            )
        for agent_index, agent in enumerate(team.agents):
            if not agent.name.strip() or not agent.title.strip():
                if not agent.name.strip():
                    issues.append(
                        _blocking_issue(
                            issue_id=f"team_agent_name:{team_index}:{agent_index}",
                            field_path=f"teams[{team_index}].agents[{agent_index}].name",
                            label=f"Nom de l'agent {agent_index + 1}",
                            message=f"L'équipe '{team_label}' contient un agent sans nom.",
                            requires_user_input=True,
                            current_value=agent.name,
                        )
                    )
                if not agent.title.strip():
                    issues.append(
                        _blocking_issue(
                            issue_id=f"team_agent_title:{team_index}:{agent_index}",
                            field_path=f"teams[{team_index}].agents[{agent_index}].title",
                            label=f"Titre de {agent.name or f'agent {agent_index + 1}'}",
                            message=f"L'équipe '{team_label}' contient un agent sans titre.",
                            requires_user_input=True,
                            current_value=agent.title,
                        )
                    )

    return _finalize_validated_draft(draft, issues=issues, updates={})


class TaskPlanExecutor:
    async def execute(self, draft: TaskPlanDraft, broadcast) -> Any:
        orchestrator = get_orchestrator()
        validated_draft = validate_task_draft(draft)
        if validated_draft.execution_eligibility != PlanExecutionEligibility.ELIGIBLE:
            blocking = [i for i in validated_draft.validation_issues if i.severity == "blocking"]
            if blocking:
                details = "; ".join(i.message for i in blocking[:3])
                raise PlanClarificationRequiredError(
                    f"Le plan de tâche nécessite des clarifications : {details}",
                    draft=validated_draft,
                )
            raise PlanClarificationRequiredError(
                "Le plan de tâche nécessite des clarifications avant d'être lancé.", draft=validated_draft
            )
        task = orchestrator.create_task(
            title=validated_draft.task_title,
            description=validated_draft.task_description,
            priority=validated_draft.priority,
            team_id=validated_draft.assigned_team_id,
            assigned_agent_id=validated_draft.assigned_agent_id,
            execution_mode=validated_draft.execution_mode,
            context_document_ids=validated_draft.context_document_ids,
        )
        await broadcast({"type": "task_created", "data": task.model_dump()})
        asyncio.create_task(orchestrator.execute_task(task.id, broadcast=broadcast))
        return task


class TeamPlanExecutor:
    async def execute(self, draft: TeamPlanDraft, broadcast) -> dict[str, Any]:
        factory = get_agent_factory()
        ctx_store = get_project_context_store()
        validated_draft = validate_team_draft(draft)
        if validated_draft.execution_eligibility != PlanExecutionEligibility.ELIGIBLE:
            blocking = [i for i in validated_draft.validation_issues if i.severity == "blocking"]
            if blocking:
                details = "; ".join(i.message for i in blocking[:3])
                raise PlanClarificationRequiredError(
                    f"Le plan d'équipe nécessite des clarifications : {details}",
                    draft=validated_draft,
                )
            raise PlanClarificationRequiredError(
                "Le plan d'équipe nécessite des clarifications avant d'être lancé.", draft=validated_draft
            )

        current_context = ctx_store.load_context() or {}
        ctx_store.publish_context(
            {
                **current_context,
                "name": validated_draft.project.name,
                "description": validated_draft.project.description,
                "domain": validated_draft.project.domain,
                "short_term_goal": validated_draft.project.short_term_goal,
            }
        )

        created_teams = []
        created_agents = []
        new_team_ids: list[str] = []

        for team_spec in validated_draft.teams:
            team, agents = factory.create_custom_team(
                name=team_spec.name,
                description=team_spec.description,
                domain=team_spec.domain or validated_draft.project.domain,
                agent_specs=[agent.model_dump() for agent in team_spec.agents],
            )
            created_teams.append(team.model_dump())
            created_agents.extend([agent.model_dump() for agent in agents])
            new_team_ids.append(team.id)

        for team_id in new_team_ids:
            asyncio.create_task(run_learning_phase_for_team(team_id, broadcast_callback=broadcast))

        result = {
            "project": validated_draft.project.model_dump(),
            "teams": created_teams,
            "agents": created_agents,
        }
        await broadcast({"type": "team_created", "data": result})
        return result
