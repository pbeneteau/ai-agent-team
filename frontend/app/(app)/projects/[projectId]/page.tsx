"use client";

/**
 * Task list — code-aware issue tracker view.
 *
 * Phase 5 of CODE_FACTORY_UI_OVERHAUL.md
 */

import { useState, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Plus,
  Code,
  GitBranch,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useArtifactList } from "@/lib/hooks/use-artifacts";
import { formatDistanceToNow } from "date-fns";
import type { ArtifactStatus } from "@/lib/types/api";

// ---------------------------------------------------------------------------
// Status config
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<
  ArtifactStatus,
  { label: string; variant: "default" | "secondary" | "outline" | "destructive"; className?: string }
> = {
  drafting: { label: "Draft", variant: "secondary" },
  in_review: { label: "In Review", variant: "outline", className: "border-amber-500/50 text-amber-600" },
  approved: { label: "Merged", variant: "default", className: "bg-emerald-600 hover:bg-emerald-700" },
  cancelled: { label: "Cancelled", variant: "destructive" },
};

// Filter options
const FILTERS = [
  { value: "", label: "All" },
  { value: "drafting", label: "Draft" },
  { value: "in_review", label: "In Review" },
  { value: "approved", label: "Merged" },
] as const;

export default function ProjectTasksPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;
  const [statusFilter, setStatusFilter] = useState<ArtifactStatus | "">("");
  const { data, isLoading } = useArtifactList(
    projectId,
    statusFilter ? { status: statusFilter } : undefined,
  );

  const artifacts = data?.items ?? [];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Tasks</h2>
        <Link href={`/projects/${projectId}/artifacts/new`}>
          <Button>
            <Plus className="h-4 w-4" />
            New Task
          </Button>
        </Link>
      </div>

      {/* Filters */}
      <div className="flex gap-1">
        {FILTERS.map((filter) => (
          <button
            key={filter.value}
            onClick={() => setStatusFilter(filter.value)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              statusFilter === filter.value
                ? "bg-[var(--color-accent)] text-white"
                : "bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-[var(--radius-md)]" />
          ))}
        </div>
      ) : artifacts.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <Code className="h-8 w-8 text-[var(--color-text-tertiary)]" />
          <p className="text-sm text-[var(--color-text-secondary)]">
            {statusFilter ? "No tasks match this filter." : "No tasks yet. Create one to start building."}
          </p>
          {!statusFilter && (
            <Link href={`/projects/${projectId}/artifacts/new`}>
              <Button variant="outline">
                <Plus className="h-4 w-4" />
                New Task
              </Button>
            </Link>
          )}
        </div>
      ) : (
        <div className="divide-y divide-[var(--color-border-primary)] rounded-[var(--radius-lg)] border border-[var(--color-border-primary)]">
          {artifacts.map((artifact) => {
            const config = STATUS_CONFIG[artifact.status];
            return (
              <Link
                key={artifact.id}
                href={`/projects/${projectId}/artifacts/${artifact.id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-[var(--color-bg-tertiary)] transition-colors"
              >
                {/* Left: icon + title + git info */}
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <Code className="h-4 w-4 shrink-0 text-[var(--color-text-secondary)]" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                      {artifact.title}
                    </p>
                    <div className="flex items-center gap-2 text-xs text-[var(--color-text-tertiary)]">
                      {artifact.git_feature_branch && (
                        <span className="flex items-center gap-0.5 truncate max-w-[160px]">
                          <GitBranch className="h-3 w-3 shrink-0" />
                          {artifact.git_feature_branch}
                        </span>
                      )}
                      {artifact.git_pr_url && artifact.git_pr_number && (
                        <span
                          className="flex items-center gap-0.5 text-[var(--color-accent)] hover:underline"
                          onClick={(e) => {
                            e.preventDefault();
                            window.open(artifact.git_pr_url!, "_blank");
                          }}
                        >
                          <ExternalLink className="h-3 w-3" />
                          #{artifact.git_pr_number}
                        </span>
                      )}
                      {!artifact.git_feature_branch && !artifact.git_pr_url && (
                        <span>
                          v{artifact.current_version} &middot; ${artifact.total_cost_usd.toFixed(2)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Right: status + time */}
                <div className="flex items-center gap-3 shrink-0">
                  <Badge variant={config.variant} className={config.className}>
                    {config.label}
                  </Badge>
                  <span className="text-xs text-[var(--color-text-tertiary)] w-16 text-right">
                    {formatDistanceToNow(new Date(artifact.created_at), { addSuffix: true })}
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
