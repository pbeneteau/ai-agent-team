"use client";

import type { TaskPlanDraft } from "@/components/chat/plan-types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface TaskPlanPreviewProps {
  draft: TaskPlanDraft;
  documentLabelsById?: Record<string, string>;
}

export function TaskPlanPreview({ draft, documentLabelsById = {} }: TaskPlanPreviewProps) {
  const assignmentLabel = draft.assigned_team_name
    ? `Team: ${draft.assigned_team_name}`
    : draft.assigned_agent_name
      ? `Agent: ${draft.assigned_agent_name}`
      : "Selection to confirm";

  return (
    <div className="space-y-4">
      <Card size="sm" className="gap-3 bg-background/90 shadow-none ring-foreground/6">
        <CardHeader className="pb-0">
          <CardTitle className="text-sm">Proposed task</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 pt-0">
          <h4 className="text-base font-semibold text-foreground">{draft.task_title}</h4>
          <p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
            {draft.task_description}
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2">
        <Card size="sm" className="gap-3 bg-background/90 shadow-none ring-foreground/6">
          <CardHeader className="pb-0">
            <CardTitle className="text-sm">Assignment</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-sm text-muted-foreground">{assignmentLabel}</CardContent>
        </Card>

        <Card size="sm" className="gap-3 bg-background/90 shadow-none ring-foreground/6">
          <CardHeader className="pb-0">
            <CardTitle className="text-sm">Execution</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            <Badge variant="outline" className="border-border/70 bg-background capitalize text-foreground">
              {draft.execution_mode.replace("_", " ")}
            </Badge>
            <p className="text-sm capitalize text-muted-foreground">Priority {draft.priority}</p>
          </CardContent>
        </Card>
      </div>

      {draft.context_document_ids.length > 0 ? (
        <Card size="sm" className="gap-3 bg-background/90 shadow-none ring-foreground/6">
          <CardHeader className="pb-0">
            <CardTitle className="text-sm">Explicitly included documents</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2 pt-0">
            {draft.context_document_ids.map((docId) => (
              <Badge
                key={docId}
                variant="secondary"
                className="h-auto rounded-full bg-primary/10 px-2.5 py-1 text-primary"
              >
                {documentLabelsById[docId] || `Document ${docId.slice(0, 8)}`}
              </Badge>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
