"use client";

import Link from "next/link";
import { ArrowRight, TriangleAlert } from "lucide-react";

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

  return (
    <Link href={`/tasks/${task.id}`} className="block">
      <Card className="cursor-pointer border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] transition-all hover:-translate-y-0.5 hover:border-black/8">
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1">
              <p className="font-semibold text-sm leading-tight text-slate-900">{task.title}</p>
              <p className="text-xs text-slate-500">
                Updated {new Date(task.updated_at).toLocaleString("en-US")}
              </p>
            </div>
            <div className="flex gap-1.5 flex-shrink-0 flex-wrap justify-end">
              <Badge variant="outline" className={`text-xs gap-1 ${status.className}`}>
                <status.Icon className={`w-3.5 h-3.5${task.status === "running" ? " animate-spin" : ""}`} />
                {status.label}
              </Badge>
              <Badge variant="outline" className={`text-xs ${priority.className}`}>
                {priority.label}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0 space-y-3">
          <p className="text-sm leading-6 text-slate-600 line-clamp-3">{task.description}</p>

          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] bg-slate-100 text-slate-700 rounded-full px-2 py-0.5 font-medium">
              {EXECUTION_MODE_LABELS[task.execution_mode]}
            </span>
            {planNodes.length > 0 ? (
              <span className="text-[10px] bg-violet-50 text-violet-700 rounded-full px-2 py-0.5 font-medium">
                {completedNodes}/{planNodes.length} node{planNodes.length > 1 ? "s" : ""}
              </span>
            ) : null}
            {task.execution_eligibility !== "eligible" ? (
              <span className="inline-flex items-center gap-1 text-[10px] bg-amber-50 text-amber-700 rounded-full px-2 py-0.5 font-medium">
                <TriangleAlert className="w-2.5 h-2.5" />
                Clarification required
              </span>
            ) : null}
            {task.sources.length > 0 ? (
              <span className="text-[10px] bg-blue-50 text-blue-700 rounded-full px-2 py-0.5 font-medium">
                {task.sources.length} source{task.sources.length > 1 ? "s" : ""}
              </span>
            ) : null}
            {reviewItems > 0 ? (
              <span className="text-[10px] bg-amber-50 text-amber-700 rounded-full px-2 py-0.5 font-medium">
                {reviewItems} item{reviewItems > 1 ? "s" : ""} to review
              </span>
            ) : null}
          </div>

          {task.status === "running" && activeProgressEntry ? (
            <div className="rounded-2xl bg-blue-50 px-3 py-2 text-xs text-blue-700">
              {activeProgressEntry.message}
            </div>
          ) : null}

          {task.status === "failed" && task.error ? (
            <div className="rounded-2xl bg-red-50 px-3 py-2 text-xs text-red-700 line-clamp-3">
              {task.error}
            </div>
          ) : null}

          {task.result ? (
            <div className="rounded-2xl bg-green-50 px-3 py-2 text-xs text-green-800 line-clamp-4">
              <span className="font-medium">Result:</span> {task.result}
            </div>
          ) : null}

          <div className="flex items-center justify-between pt-1 text-xs font-medium text-primary">
            <span>Open full readout</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
