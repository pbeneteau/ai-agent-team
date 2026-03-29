"use client";

/**
 * Agent card for the roster grid.
 *
 * Ref: TDD-05 Section 14.1
 */

import Link from "next/link";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AgentListItem, AgentRole, AgentStatus, ProgressionLevel } from "@/lib/types/api";

const statusConfig: Record<AgentStatus, { label: string; className: string }> = {
  learning: { label: "Learning", className: "bg-[var(--color-accent-subtle)] text-[var(--color-accent)]" },
  ready: { label: "Ready", className: "bg-[var(--color-success-subtle)] text-[var(--color-success)]" },
  working: { label: "Working", className: "bg-[var(--color-warning-subtle)] text-[var(--color-warning)]" },
  reflecting: { label: "Reflecting", className: "bg-[var(--color-accent-subtle)] text-purple-600 dark:text-purple-400" },
};

const roleConfig: Record<AgentRole, { label: string; className: string }> = {
  lead: { label: "Lead", className: "bg-[var(--color-accent-subtle)] text-[var(--color-accent)] ring-1 ring-[var(--color-accent)]/20" },
  worker: { label: "Worker", className: "bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]" },
};

const levelLabels: Record<ProgressionLevel, string> = {
  "apprenti": "Apprenti",
  "opérationnel": "Opérationnel",
  "expert": "Expert",
};

interface AgentCardProps {
  agent: AgentListItem;
}

export function AgentCard({ agent }: AgentCardProps) {
  const status = statusConfig[agent.status];
  const role = roleConfig[agent.role] ?? roleConfig.worker;
  const readiness = agent.readiness_score;
  const readinessColor =
    readiness < 40 ? "bg-[var(--color-danger)]" : readiness < 70 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]";

  return (
    <Link href={`/roster/${agent.id}`}>
      <Card className="h-full cursor-pointer transition-shadow hover:shadow-[var(--shadow-md)]">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="truncate">{agent.name}</CardTitle>
            <span
              className={cn("inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-medium", status.className)}
              aria-label={`Status: ${status.label}`}
            >
              {agent.status === "learning" && <span className="mr-1 h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
              {status.label}
            </span>
          </div>
          <CardDescription className="truncate">{agent.specialization}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {/* Readiness bar */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-[var(--color-text-secondary)]">Readiness</span>
                <span className="tabular-nums text-[var(--color-text-primary)]">{readiness}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-bg-tertiary)]">
                <div
                  className={cn("h-full rounded-full transition-all", readinessColor)}
                  style={{ width: `${readiness}%` }}
                  role="progressbar"
                  aria-valuenow={readiness}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`Readiness: ${readiness}%`}
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Badge variant="outline" className="text-[10px]">
                  {levelLabels[agent.progression_level]}
                </Badge>
                <span
                  className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium", role.className)}
                  aria-label={`Role: ${role.label}`}
                >
                  {role.label}
                </span>
              </div>
              <span className="text-xs text-[var(--color-text-tertiary)]">
                {agent.completed_artifacts} task{agent.completed_artifacts !== 1 ? "s" : ""}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
