"use client";

import type { PlanDraft, PlanForm, PlanState } from "./plan-types";

export type PlanPanelPhase =
  | "idle"
  | "form"
  | "review"
  | "revising"
  | "executing"
  | "failed"
  | "cancelled"
  | "completed";

export interface PlanUiState {
  phase: PlanPanelPhase;
  sessionId: string | null;
  backendState: PlanState | null;
  form: PlanForm | null;
  formValues: Record<string, string>;
  draft: PlanDraft | null;
  revisionText: string;
  clarificationValues: Record<string, string>;
  error: string | null;
}

export type PlanUiAction =
  | { type: "show_form"; sessionId: string | null; form: PlanForm | null }
  | { type: "update_form_value"; fieldId: string; value: string }
  | { type: "submit_form" }
  | {
      type: "show_draft";
      sessionId: string | null;
      backendState: PlanState | null;
      draft: PlanDraft | null;
      error?: string | null;
    }
  | { type: "set_revision_text"; value: string }
  | { type: "update_clarification_value"; fieldPath: string; value: string }
  | { type: "request_confirm" }
  | { type: "revising"; backendState: PlanState | null }
  | { type: "executing"; backendState: PlanState | null }
  | { type: "failed"; backendState: PlanState | null; error: string; draft?: PlanDraft | null }
  | { type: "completed" }
  | { type: "cancelled"; backendState: PlanState | null }
  | { type: "reset" };

export function createInitialPlanState(): PlanUiState {
  return {
    phase: "idle",
    sessionId: null,
    backendState: null,
    form: null,
    formValues: {},
    draft: null,
    revisionText: "",
    clarificationValues: {},
    error: null,
  };
}

function buildClarificationValues(draft: PlanDraft | null): Record<string, string> {
  return Object.fromEntries(
    (draft?.validation_issues ?? [])
      .filter((issue) => issue.requires_user_input)
      .map((issue) => [issue.field_path, issue.current_value ?? ""]),
  );
}

export function planReducer(state: PlanUiState, action: PlanUiAction): PlanUiState {
  switch (action.type) {
    case "show_form":
      return {
        ...state,
        phase: "form",
        sessionId: action.sessionId,
        backendState: "discovery",
        form: action.form,
        formValues: {},
        draft: null,
        revisionText: "",
        clarificationValues: {},
        error: null,
      };
    case "update_form_value":
      return {
        ...state,
        formValues: { ...state.formValues, [action.fieldId]: action.value },
      };
    case "submit_form":
      return {
        ...state,
        phase: "idle",
        form: null,
        formValues: {},
        clarificationValues: {},
        error: null,
      };
    case "show_draft":
      return {
        ...state,
        phase: "review",
        sessionId: action.sessionId,
        backendState: action.backendState,
        form: null,
        draft: action.draft,
        clarificationValues: buildClarificationValues(action.draft),
        error: action.error ?? null,
      };
    case "set_revision_text":
      return {
        ...state,
        revisionText: action.value,
      };
    case "update_clarification_value":
      return {
        ...state,
        clarificationValues: {
          ...state.clarificationValues,
          [action.fieldPath]: action.value,
        },
      };
    case "request_confirm":
      return {
        ...state,
        phase: "review",
        error: null,
      };
    case "revising":
      return {
        ...state,
        phase: "revising",
        backendState: action.backendState,
        error: null,
      };
    case "executing":
      return {
        ...state,
        phase: "executing",
        backendState: action.backendState,
        error: null,
      };
    case "failed":
      return {
        ...state,
        phase: "failed",
        backendState: action.backendState,
        draft: action.draft ?? state.draft,
        error: action.error,
      };
    case "completed":
      return {
        ...createInitialPlanState(),
        phase: "completed",
      };
    case "cancelled":
      return {
        ...createInitialPlanState(),
        phase: "cancelled",
        backendState: action.backendState,
      };
    case "reset":
      return createInitialPlanState();
    default:
      return state;
  }
}
