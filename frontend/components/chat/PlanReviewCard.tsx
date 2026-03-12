"use client";

import { AlertTriangle, Bot, Loader2 } from "lucide-react";

import type { PlanDraft } from "@/components/chat/plan-types";
import { TaskPlanPreview } from "@/components/chat/TaskPlanPreview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

interface PlanReviewCardProps {
  draft: PlanDraft;
  phase: "idle" | "form" | "review" | "revising" | "executing" | "failed" | "cancelled" | "completed";
  error: string | null;
  backendState: string | null;
  revisionText: string;
  clarificationValues: Record<string, string>;
  documentLabelsById?: Record<string, string>;
  onRevisionTextChange: (value: string) => void;
  onClarificationValueChange: (fieldPath: string, value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
  onRevise: () => void;
}

export function PlanReviewCard({
  draft,
  phase,
  error,
  backendState,
  revisionText,
  clarificationValues,
  documentLabelsById,
  onRevisionTextChange,
  onClarificationValueChange,
  onConfirm,
  onCancel,
  onRevise,
}: PlanReviewCardProps) {
  const hasBlockingQuestions = draft.validation_issues.some((issue) => issue.severity === "blocking");
  const targetedIssues = draft.validation_issues.filter((issue) => issue.requires_user_input);
  const isExecuting = phase === "executing";
  const isRevising = phase === "revising";
  const isFailed = phase === "failed";
  const statusLabel =
    phase === "executing"
      ? "Executing"
      : phase === "revising"
        ? "Revising"
        : phase === "failed"
          ? "Plan needs fixes"
          : backendState === "awaiting_confirmation"
            ? "Awaiting confirmation"
            : "Draft ready";
  const canConfirm =
    !isExecuting &&
    !isRevising &&
    draft.execution_eligibility === "eligible" &&
    targetedIssues.every((issue) => (clarificationValues[issue.field_path] ?? "").trim().length > 0 || !issue.current_value);

  return (
    <Card className="mx-auto max-w-4xl gap-5 bg-background/95 shadow-sm ring-foreground/8">
      <CardHeader className="gap-4 border-b border-border/60">
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Bot className="size-4" />
          </div>

          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-base">
                {draft.kind === "task" ? "Task plan to review" : "Team plan to review"}
              </CardTitle>
              <Badge variant="outline" className="border-border/70 bg-background text-muted-foreground">
                {statusLabel}
              </Badge>
              <Badge variant="secondary" className="bg-muted text-muted-foreground">
                Version {draft.revision}
              </Badge>
              <Badge variant="outline" className="border-border/70 bg-background text-muted-foreground">
                Validation {draft.validation_status}
              </Badge>
              <Badge variant="outline" className="border-border/70 bg-background text-muted-foreground">
                Execution {draft.execution_eligibility}
              </Badge>
            </div>

            {draft.summary ? (
              <p className="text-sm leading-6 text-muted-foreground">{draft.summary}</p>
            ) : null}

            {draft.description ? (
              <p className="text-sm leading-6 text-muted-foreground">{draft.description}</p>
            ) : null}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {draft.kind === "task" ? (
          <TaskPlanPreview draft={draft} documentLabelsById={documentLabelsById} />
        ) : (
          <div className="space-y-4">
            <Card size="sm" className="gap-3 bg-background/90 shadow-none ring-foreground/6">
              <CardHeader className="pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-sm">Project</CardTitle>
                  {draft.project.domain ? (
                    <Badge variant="outline" className="border-border/70 bg-background text-muted-foreground">
                      {draft.project.domain}
                    </Badge>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                <div>
                  <h4 className="text-base font-semibold text-foreground">{draft.project.name}</h4>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                    {draft.project.description}
                  </p>
                </div>
                {draft.project.short_term_goal ? (
                  <div className="rounded-2xl border border-border/60 bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">Short-term goal:</span>{" "}
                    {draft.project.short_term_goal}
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <div className="space-y-3">
              {draft.teams.map((team) => (
                <Card key={team.name} size="sm" className="gap-3 bg-background/90 shadow-none ring-foreground/6">
                  <CardHeader className="pb-0">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-1">
                        <CardTitle className="text-sm">{team.name}</CardTitle>
                        <p className="text-sm leading-6 text-muted-foreground">{team.description}</p>
                      </div>
                      {team.domain ? (
                        <Badge variant="outline" className="border-border/70 bg-background text-muted-foreground">
                          {team.domain}
                        </Badge>
                      ) : null}
                    </div>
                  </CardHeader>

                  <CardContent className="grid gap-2 pt-0 sm:grid-cols-2">
                    {team.agents.map((agent) => (
                      <div
                        key={`${team.name}-${agent.name}`}
                        className="rounded-2xl border border-border/60 bg-muted/15 p-3"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{agent.name}</p>
                          {agent.is_lead ? (
                            <Badge variant="secondary" className="bg-primary/10 text-primary">
                              Lead
                            </Badge>
                          ) : null}
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{agent.title}</p>
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">{agent.goal}</p>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {draft.validation_issues.length > 0 ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">
              <AlertTriangle className="size-3.5" />
              Validation contract
            </div>
            <ul className="mt-3 space-y-2 text-sm text-amber-900">
              {draft.validation_issues.map((issue) => (
                <li key={issue.id}>
                  <span className="font-medium">{issue.label}:</span> {issue.message}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-amber-800">
              Confirmation stays blocked until the backend considers this draft eligible.
            </p>
          </div>
        ) : null}

        {targetedIssues.length > 0 ? (
          <div className="space-y-3 rounded-2xl border border-border/60 bg-background/80 p-4">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Targeted clarifications
            </div>
            {targetedIssues.map((issue) => {
              const value = clarificationValues[issue.field_path] ?? "";
              return (
                <div key={issue.id} className="space-y-2">
                  <label className="block text-sm font-medium text-foreground">{issue.label}</label>
                  {issue.input_type === "select" ? (
                    <select
                      className="flex h-11 w-full rounded-2xl border border-input bg-background px-3 text-sm"
                      value={value}
                      onChange={(event) => onClarificationValueChange(issue.field_path, event.target.value)}
                      disabled={isExecuting}
                    >
                      <option value="">Select…</option>
                      {issue.options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : issue.input_type === "textarea" ? (
                    <Textarea
                      rows={3}
                      className="rounded-2xl bg-background"
                      value={value}
                      onChange={(event) => onClarificationValueChange(issue.field_path, event.target.value)}
                      disabled={isExecuting}
                    />
                  ) : (
                    <input
                      className="flex h-11 w-full rounded-2xl border border-input bg-background px-3 text-sm"
                      value={value}
                      onChange={(event) => onClarificationValueChange(issue.field_path, event.target.value)}
                      disabled={isExecuting}
                    />
                  )}
                </div>
              );
            })}
          </div>
        ) : null}

        {draft.questions.length > 0 ? (
          <Card size="sm" className="gap-3 bg-background/90 shadow-none ring-foreground/6">
            <CardHeader className="pb-0">
              <CardTitle className="text-sm">Additional notes</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <ul className="space-y-2 text-sm text-muted-foreground">
                {draft.questions.map((question) => (
                  <li key={question}>• {question}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ) : null}

        {isFailed && error ? (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {isRevising ? (
          <div className="rounded-2xl border border-primary/15 bg-primary/5 px-4 py-3 text-sm text-primary">
            Alex is preparing a new version of the plan. The current draft stays visible until the revision arrives.
          </div>
        ) : null}

        <div className="space-y-2">
          <label className="block text-xs font-medium text-foreground">
            {hasBlockingQuestions ? "Answer the blocking questions" : "Optional revision"}
          </label>
          <Textarea
            rows={4}
            className="min-h-[108px] rounded-2xl bg-background"
            placeholder={
              hasBlockingQuestions
                ? "Example: maximum 12 slides, sober tone, include one competitor slide."
                : "Example: keep the team, but refocus the task on a more concise version."
            }
            value={revisionText}
            onChange={(event) => onRevisionTextChange(event.target.value)}
            disabled={isExecuting}
          />
        </div>
      </CardContent>

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border/60 bg-muted/20 px-4 py-3">
        <Button variant="ghost" onClick={onCancel} disabled={isExecuting}>
          Cancel
        </Button>
        <Button variant="outline" onClick={onRevise} disabled={isExecuting}>
          {hasBlockingQuestions ? "Revalidate draft" : "Revise plan"}
        </Button>
        <Button onClick={onConfirm} disabled={!canConfirm}>
          {isExecuting ? <Loader2 className="size-4 animate-spin" /> : null}
          {isExecuting
            ? "Executing…"
            : draft.execution_eligibility !== "eligible"
              ? "Confirmation blocked"
              : "Confirm and launch"}
        </Button>
      </div>
    </Card>
  );
}
