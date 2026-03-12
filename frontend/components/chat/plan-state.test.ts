import { describe, expect, it } from "vitest";

import { createInitialPlanState, planReducer } from "./plan-state";
import type { TaskPlanDraft } from "./plan-types";

function makeDraft(overrides: Partial<TaskPlanDraft> = {}): TaskPlanDraft {
  return {
    id: "draft-1",
    session_id: "session-1",
    kind: "task",
    state: "awaiting_confirmation",
    revision: 1,
    title: "Draft task",
    summary: "Summary",
    description: "Description",
    questions: [],
    blocking_questions: [],
    validation_issues: [],
    validation_status: "valid",
    execution_eligibility: "eligible",
    task_title: "Draft task",
    task_description: "Do the thing",
    priority: "medium",
    execution_mode: "auto",
    assigned_team_id: "team-1",
    assigned_agent_id: null,
    assigned_team_name: "Team One",
    assigned_agent_name: null,
    context_document_ids: [],
    ...overrides,
  };
}

describe("planReducer", () => {
  it("preserves the current draft while a revision is pending", () => {
    const draft = makeDraft();
    const reviewState = planReducer(createInitialPlanState(), {
      type: "show_draft",
      sessionId: "session-1",
      backendState: "awaiting_confirmation",
      draft,
    });

    const revisingState = planReducer(reviewState, {
      type: "revising",
      backendState: "discovery",
    });

    expect(revisingState.phase).toBe("revising");
    expect(revisingState.draft?.id).toBe(draft.id);
  });

  it("keeps blocker errors contextualized with the active draft", () => {
    const draft = makeDraft({
      blocking_questions: ["Clarify the target audience"],
      validation_issues: [
        {
          id: "target",
          field_path: "assigned_target",
          label: "Target",
          message: "Clarify the target audience",
          severity: "blocking",
          requires_user_input: true,
          input_type: "text",
          options: [],
          current_value: "",
        },
      ],
      validation_status: "needs_clarification",
      execution_eligibility: "clarification_required",
    });
    const reviewState = planReducer(createInitialPlanState(), {
      type: "show_draft",
      sessionId: "session-1",
      backendState: "awaiting_confirmation",
      draft,
    });

    const failedState = planReducer(reviewState, {
      type: "failed",
      backendState: "awaiting_confirmation",
      error: "Plan still has blocking questions",
    });

    expect(failedState.phase).toBe("failed");
    expect(failedState.error).toContain("blocking questions");
    expect(failedState.draft?.blocking_questions).toHaveLength(1);
  });

  it("keeps preview mode when a draft comes back with clarification issues", () => {
    const draft = makeDraft({
      validation_issues: [
        {
          id: "team",
          field_path: "assigned_target",
          label: "Target",
          message: "Pick a team",
          severity: "blocking",
          requires_user_input: true,
          input_type: "select",
          options: ["Team One", "Team Two"],
          current_value: null,
        },
      ],
      validation_status: "needs_clarification",
      execution_eligibility: "clarification_required",
    });

    const reviewState = planReducer(createInitialPlanState(), {
      type: "show_draft",
      sessionId: "session-1",
      backendState: "awaiting_confirmation",
      draft,
      error: "Plan requires clarification before execution",
    });

    expect(reviewState.phase).toBe("review");
    expect(reviewState.error).toContain("clarification");
    expect(reviewState.clarificationValues.assigned_target).toBe("");
  });

  it("stores clarification field updates without jumping to executing", () => {
    const draft = makeDraft({
      validation_issues: [
        {
          id: "team",
          field_path: "assigned_target",
          label: "Target",
          message: "Pick a team",
          severity: "blocking",
          requires_user_input: true,
          input_type: "select",
          options: ["Team One"],
          current_value: null,
        },
      ],
      validation_status: "needs_clarification",
      execution_eligibility: "clarification_required",
    });
    const reviewState = planReducer(createInitialPlanState(), {
      type: "show_draft",
      sessionId: "session-1",
      backendState: "awaiting_confirmation",
      draft,
    });

    const updated = planReducer(reviewState, {
      type: "update_clarification_value",
      fieldPath: "assigned_target",
      value: "Team One",
    });
    const confirming = planReducer(updated, { type: "request_confirm" });

    expect(updated.clarificationValues.assigned_target).toBe("Team One");
    expect(confirming.phase).toBe("review");
    expect(confirming.backendState).toBe("awaiting_confirmation");
  });
});
