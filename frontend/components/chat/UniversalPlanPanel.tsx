"use client";

import type { PlanDraft, PlanForm, PlanState } from "@/components/chat/plan-types";
import { PlanFormCard } from "@/components/chat/PlanFormCard";
import { PlanReviewCard } from "@/components/chat/PlanReviewCard";

type PlanPanelPhase =
  | "idle"
  | "form"
  | "review"
  | "revising"
  | "executing"
  | "failed"
  | "cancelled"
  | "completed";

interface UniversalPlanPanelProps {
  phase: PlanPanelPhase;
  form: PlanForm | null;
  formValues: Record<string, string>;
  draft: PlanDraft | null;
  error: string | null;
  backendState: PlanState | null;
  revisionText: string;
  clarificationValues: Record<string, string>;
  documentLabelsById: Record<string, string>;
  onFieldChange: (fieldId: string, value: string) => void;
  onFormCancel: () => void;
  onFormSubmit: () => void;
  onRevisionTextChange: (value: string) => void;
  onClarificationValueChange: (fieldPath: string, value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
  onRevise: () => void;
}

export function UniversalPlanPanel({
  phase,
  form,
  formValues,
  draft,
  error,
  backendState,
  revisionText,
  clarificationValues,
  documentLabelsById,
  onFieldChange,
  onFormCancel,
  onFormSubmit,
  onRevisionTextChange,
  onClarificationValueChange,
  onConfirm,
  onCancel,
  onRevise,
}: UniversalPlanPanelProps) {
  if (draft) {
    return (
      <PlanReviewCard
        draft={draft}
        phase={phase}
        error={error}
        backendState={backendState}
        revisionText={revisionText}
        clarificationValues={clarificationValues}
        documentLabelsById={documentLabelsById}
        onRevisionTextChange={onRevisionTextChange}
        onClarificationValueChange={onClarificationValueChange}
        onConfirm={onConfirm}
        onCancel={onCancel}
        onRevise={onRevise}
      />
    );
  }

  if (form) {
    return (
      <PlanFormCard
        form={form}
        values={formValues}
        phase={phase}
        onChange={onFieldChange}
        onCancel={onFormCancel}
        onSubmit={onFormSubmit}
      />
    );
  }

  return null;
}
