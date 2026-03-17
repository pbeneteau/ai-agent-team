"use client";

import Link from "next/link";
import { ArrowRight, FileText, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { Task } from "@/lib/api";
import {
  EXECUTION_MODE_LABELS,
  PRIORITY_CONFIG,
  STATUS_CONFIG,
} from "@/components/tasks/task-ui";

export function TaskCard({
  task,
}: {
  task: Task;
  onRetry?: () => void;
}) {
  const status = STATUS_CONFIG[task.status];
  const priority = PRIORITY_CONFIG[task.priority];
  const planNodes = task.execution_plan.nodes;
  const completedNodes = planNodes.filter((node) => node.status === "completed").length;
  const activeProgressEntry =
    task.progress_log.length > 0 ? task.progress_log[task.progress_log.length - 1] : null;
  const reviewItems = task.warnings.length + task.assumptions.length;
  const deliverableCount = task.deliverables.length;
  const blockerCount = task.execution_blockers.length;
  const progressLabel = planNodes.length > 0 ? `${completedNodes}/${planNodes.length}` : "No nodes";
  const operatorSignal =
    task.status === "failed"
      ? {
          label: "Failure",
          text: task.error ?? "Execution failed before a consolidated result was produced.",
          className: "border-red-100 bg-red-50 text-red-800",
        }
      : task.execution_eligibility !== "eligible"
        ? {
            label: "Clarification required",
            text: task.execution_blockers[0] ?? "Execution is waiting on blocking clarification.",
            className: "ops-signal-warning",
          }
        : task.status === "running" && activeProgressEntry
          ? {
              label: "Live signal",
              text: activeProgressEntry.message,
              className: "ops-signal-info",
            }
          : task.result
            ? {
                label: "Useful output",
                text: task.result,
                className: "ops-signal-positive",
              }
            : null;

  return (
    <Link href={`/tasks/${task.id}`} className="block">
      <Card className="group cursor-pointer transition-colors hover:border-[var(--ops-border-strong)] hover:bg-[var(--ops-surface-elevated)]">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className={`text-[11px] gap-1 ${status.className}`}>
                  <status.Icon className={`w-3.5 h-3.5${task.status === "running" ? " animate-spin" : ""}`} />
                  {status.label}
                </Badge>
                <Badge variant="outline" className={`text-[11px] ${priority.className}`}>
                  {priority.label}
                </Badge>
                <Badge variant="secondary" className="text-[10px]">
                  {EXECUTION_MODE_LABELS[task.execution_mode]}
                </Badge>
              </div>
              <p className="line-clamp-2 text-sm font-semibold leading-tight text-slate-900">{task.title}</p>
              <p className="text-[11px] text-slate-500">
                Updated {new Date(task.updated_at).toLocaleString("en-US")}
              </p>
            </div>
            <ArrowRight className="mt-0.5 size-4 shrink-0 text-slate-300 transition-colors group-hover:text-slate-500" />
          </div>
        </CardHeader>
        <CardContent className="space-y-3 pt-0">
          <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
            <SignalTile label="Progress" value={progressLabel} />
            <SignalTile label="Deliverables" value={deliverableCount} />
            <SignalTile label="Sources" value={task.sources.length} />
            <SignalTile
              label={task.execution_eligibility !== "eligible" ? "Blockers" : "Review"}
              value={task.execution_eligibility !== "eligible" ? blockerCount : reviewItems}
              tone={task.execution_eligibility !== "eligible" || task.status === "failed" ? "warning" : "default"}
            />
          </div>

          <p className="line-clamp-2 text-sm leading-6 text-slate-600">{task.description}</p>

          {operatorSignal ? (
            <div className={`rounded-[14px] border px-3 py-2.5 text-xs leading-5 ${operatorSignal.className}`}>
              <p className="font-semibold uppercase tracking-[0.14em]">{operatorSignal.label}</p>
              <p className="mt-1 line-clamp-3">{operatorSignal.text}</p>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {task.execution_eligibility !== "eligible" ? (
              <Badge variant="warning" className="gap-1 text-[10px]">
                <TriangleAlert className="w-2.5 h-2.5" />
                Clarification required
              </Badge>
            ) : null}
            {deliverableCount > 0 ? (
              <Badge variant="positive" className="gap-1 text-[10px]">
                <FileText className="w-2.5 h-2.5" />
                {deliverableCount} deliverable{deliverableCount > 1 ? "s" : ""}
              </Badge>
            ) : null}
            {reviewItems > 0 ? (
              <Badge variant="warning" className="text-[10px]">
                {reviewItems} review item{reviewItems > 1 ? "s" : ""}
              </Badge>
            ) : null}
          </div>

          <div className="flex items-center justify-between pt-1 text-xs font-medium text-primary">
            <span>Open task</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function SignalTile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: "default" | "warning";
}) {
  return (
    <div
      className={`rounded-2xl border px-3 py-2 ${
        tone === "warning"
          ? "border-[var(--ops-signal-warning-border)] bg-[var(--ops-signal-warning-bg)] text-[var(--ops-signal-warning-ink)]"
          : "border-[var(--ops-border)] bg-[var(--ops-surface-muted)] text-slate-900"
      }`}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-semibold">{value}</p>
    </div>
  );
}
