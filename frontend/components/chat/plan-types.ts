import type { ModelTier, TaskExecutionMode, TaskPriority } from "@/lib/api";

export type PlanKind = "task" | "team";
export type PlanState =
  | "discovery"
  | "draft"
  | "awaiting_confirmation"
  | "executing"
  | "completed"
  | "cancelled"
  | "failed";

export type PlanFieldType = "text" | "textarea" | "select";
export type PlanValidationSeverity = "info" | "warning" | "blocking";
export type PlanValidationStatus = "valid" | "needs_clarification" | "invalid";
export type PlanExecutionEligibility = "eligible" | "clarification_required" | "ineligible";

export interface PlanField {
  id: string;
  label: string;
  type: PlanFieldType;
  placeholder?: string;
  options?: string[];
  required?: boolean;
}

export interface PlanForm {
  title: string;
  description?: string;
  fields: PlanField[];
}

export interface PlanValidationIssue {
  id: string;
  field_path: string;
  label: string;
  message: string;
  severity: PlanValidationSeverity;
  requires_user_input: boolean;
  input_type: PlanFieldType;
  options: string[];
  current_value: string | null;
}

export interface TaskPlanDraft {
  id: string;
  session_id: string;
  kind: "task";
  state: PlanState;
  revision: number;
  title: string;
  summary: string;
  description: string;
  questions: string[];
  blocking_questions: string[];
  validation_issues: PlanValidationIssue[];
  validation_status: PlanValidationStatus;
  execution_eligibility: PlanExecutionEligibility;
  task_title: string;
  task_description: string;
  priority: TaskPriority;
  execution_mode: TaskExecutionMode;
  assigned_team_id: string | null;
  assigned_agent_id: string | null;
  assigned_team_name: string | null;
  assigned_agent_name: string | null;
  context_document_ids: string[];
}

export interface TeamPlanAgentDraft {
  name: string;
  title: string;
  specialization: string;
  goal: string;
  backstory: string;
  is_lead: boolean;
  model_tier: ModelTier;
}

export interface TeamPlanTeamDraft {
  name: string;
  description: string;
  domain: string;
  agents: TeamPlanAgentDraft[];
}

export interface TeamPlanProjectDraft {
  name: string;
  description: string;
  domain: string;
  short_term_goal: string;
}

export interface TeamPlanDraft {
  id: string;
  session_id: string;
  kind: "team";
  state: PlanState;
  revision: number;
  title: string;
  summary: string;
  description: string;
  questions: string[];
  blocking_questions: string[];
  validation_issues: PlanValidationIssue[];
  validation_status: PlanValidationStatus;
  execution_eligibility: PlanExecutionEligibility;
  project: TeamPlanProjectDraft;
  teams: TeamPlanTeamDraft[];
}

export type PlanDraft = TaskPlanDraft | TeamPlanDraft;

export interface PlanPreviewPayload {
  session_id: string;
  state: PlanState;
  kind: PlanKind;
  draft: PlanDraft;
  last_error?: string | null;
}
