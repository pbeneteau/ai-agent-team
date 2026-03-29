"use client";

/**
 * Project detail — artifact list tab.
 *
 * Ref: TDD-05 Section 15.2
 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { Plus, FileText, Code } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useArtifactList } from "@/lib/hooks/use-artifacts";
import { formatDistanceToNow } from "date-fns";
import type { ArtifactStatus } from "@/lib/types/api";

const statusVariant: Record<ArtifactStatus, "default" | "secondary" | "outline" | "destructive"> = {
  drafting: "secondary",
  in_review: "outline",
  approved: "default",
  cancelled: "destructive",
};

export default function ProjectArtifactsPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;
  const { data, isLoading } = useArtifactList(projectId);

  const artifacts = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Artifacts</h2>
        <Link href={`/projects/${projectId}/artifacts/new`}>
          <Button>
            <Plus className="h-4 w-4" />
            New Deliverable
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-[var(--radius-md)]" />
          ))}
        </div>
      ) : artifacts.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <FileText className="h-8 w-8 text-[var(--color-text-tertiary)]" />
          <p className="text-sm text-[var(--color-text-secondary)]">
            No deliverables yet. Create one to start working.
          </p>
          <Link href={`/projects/${projectId}/artifacts/new`}>
            <Button variant="outline">
              <Plus className="h-4 w-4" />
              New Deliverable
            </Button>
          </Link>
        </div>
      ) : (
        <div className="divide-y divide-[var(--color-border-primary)] rounded-[var(--radius-lg)] border border-[var(--color-border-primary)]">
          {artifacts.map((artifact) => (
            <Link
              key={artifact.id}
              href={`/projects/${projectId}/artifacts/${artifact.id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-[var(--color-bg-tertiary)] transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                {artifact.artifact_type === "code" ? (
                  <Code className="h-4 w-4 shrink-0 text-[var(--color-text-secondary)]" />
                ) : (
                  <FileText className="h-4 w-4 shrink-0 text-[var(--color-text-secondary)]" />
                )}
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                    {artifact.title}
                  </p>
                  <p className="text-xs text-[var(--color-text-tertiary)]">
                    v{artifact.current_version} &middot; ${artifact.total_cost_usd.toFixed(2)}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <Badge variant={statusVariant[artifact.status]}>
                  {artifact.status.replace("_", " ")}
                </Badge>
                <span className="text-xs text-[var(--color-text-tertiary)]">
                  {formatDistanceToNow(new Date(artifact.created_at), { addSuffix: true })}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
