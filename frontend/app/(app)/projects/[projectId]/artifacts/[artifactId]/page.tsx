"use client";

/**
 * Artifact detail page — conditionally renders heartbeat or review.
 *
 * Ref: TDD-05 Sections 9-12, TDD-01 Journeys J2/J3
 *
 * Status routing:
 * - drafting → HeartbeatPanel (3s polling)
 * - in_review → ArtifactReview (prose or code)
 * - approved/cancelled → ArtifactReview (read-only)
 *
 * Transition: when status changes from drafting → in_review, a CSS fade
 * animation plays, queries are invalidated, and the review UI loads.
 *
 * Diff mode: toggled via a state flag; lazy-loads ProseDiffViewer.
 */

import { useState, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useArtifactDetail, useArtifactStatus, useArtifactVersions } from "@/lib/hooks/use-artifacts";
import { HeartbeatPanel } from "@/features/artifacts/heartbeat-panel";
import { ArtifactReview } from "@/features/artifacts/artifact-review";

// Lazy-load the diff viewer (heavy dependency)
const ProseDiffViewer = dynamic(
  () => import("@/features/artifacts/prose-diff-viewer").then((m) => ({ default: m.ProseDiffViewer })),
  {
    loading: () => (
      <div className="space-y-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    ),
    ssr: false,
  },
);

export default function ArtifactDetailPage() {
  const params = useParams<{ projectId: string; artifactId: string }>();
  const artifactId = params.artifactId;

  const { data: artifact, isLoading: artifactLoading } = useArtifactDetail(artifactId);
  const { data: statusData } = useArtifactStatus(artifactId);
  const { data: versionsData } = useArtifactVersions(artifactId);

  // Diff view state
  const [diffState, setDiffState] = useState<{ old: number; new: number } | null>(null);

  const handleShowDiff = useCallback((oldVersion: number, newVersion: number) => {
    setDiffState({ old: oldVersion, new: newVersion });
  }, []);

  const handleBackFromDiff = useCallback(() => {
    setDiffState(null);
  }, []);

  // Determine the first file path for diff viewer
  const versions = versionsData?.items ?? [];
  const firstFilePath = useMemo(() => {
    if (versions.length === 0) return "";
    const latest = versions.find((v) => v.version_number === (diffState?.new ?? artifact?.current_version ?? 1));
    return latest?.file_manifest?.[0]?.path ?? "";
  }, [versions, diffState, artifact]);

  if (artifactLoading || !artifact) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  const currentStatus = statusData?.status ?? artifact.status;
  const isDrafting = currentStatus === "drafting";
  const isTerminal = currentStatus === "approved" || currentStatus === "cancelled";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">{artifact.title}</h1>
        <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
          <span className="capitalize">{artifact.artifact_type}</span>
          <span>&middot;</span>
          <span>${artifact.total_cost_usd.toFixed(2)}</span>
          {isTerminal && (
            <>
              <span>&middot;</span>
              <Badge
                variant={currentStatus === "approved" ? "default" : "destructive"}
              >
                {currentStatus === "approved" ? "Approved" : "Cancelled"}
              </Badge>
            </>
          )}
        </div>
      </div>

      {/* Content — heartbeat or review */}
      <div
        className="transition-opacity duration-300"
        style={{ opacity: 1 }}
      >
        {isDrafting && statusData ? (
          <HeartbeatPanel
            artifactId={artifact.id}
            title={artifact.title}
            status={statusData}
          />
        ) : diffState ? (
          <ProseDiffViewer
            artifactId={artifact.id}
            oldVersion={diffState.old}
            newVersion={diffState.new}
            filePath={firstFilePath}
            onBack={handleBackFromDiff}
          />
        ) : (
          <ArtifactReview artifact={artifact} onShowDiff={handleShowDiff} />
        )}
      </div>
    </div>
  );
}
