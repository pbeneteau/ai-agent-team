"use client";

/**
 * Artifact review shell — routes to prose or code review based on artifact type.
 *
 * Ref: TDD-05 Section 10.1-10.3
 * Handles version selection, file fetching, and layout.
 */

import { useState, useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { VersionSwitcher } from "./version-switcher";
import { ArtifactActions } from "./artifact-actions";
import { ProseViewer } from "./prose-viewer";
import { ReviewSidebar } from "./review-sidebar";
import { CodeArtifactReview } from "./code-artifact-review";
import { FloatingCommentToolbar } from "@/features/comments/floating-comment-toolbar";
import { useArtifactVersions, useArtifactFile } from "@/lib/hooks/use-artifacts";
import type { ArtifactResponse, ArtifactStatus } from "@/lib/types/api";

const statusLabel: Record<ArtifactStatus, string> = {
  drafting: "Drafting",
  in_review: "In Review",
  approved: "Approved",
  cancelled: "Cancelled",
};

const statusVariant: Record<ArtifactStatus, "default" | "secondary" | "outline" | "destructive"> = {
  drafting: "secondary",
  in_review: "outline",
  approved: "default",
  cancelled: "destructive",
};

interface ArtifactReviewProps {
  artifact: ArtifactResponse;
  onShowDiff: (oldVersion: number, newVersion: number) => void;
}

export function ArtifactReview({ artifact, onShowDiff }: ArtifactReviewProps) {
  const { data: versionsData, isLoading: versionsLoading } = useArtifactVersions(artifact.id);
  const versions = versionsData?.items ?? [];

  const [selectedVersion, setSelectedVersion] = useState<number>(artifact.current_version || 1);

  const currentVersionData = useMemo(
    () => versions.find((v) => v.version_number === selectedVersion) ?? null,
    [versions, selectedVersion],
  );

  // Get first file path for prose artifacts
  const firstFilePath = currentVersionData?.file_manifest?.[0]?.path ?? "";

  const { data: fileContent, isLoading: fileLoading } = useArtifactFile(
    artifact.id,
    selectedVersion,
    firstFilePath,
  );

  // When versions load and our selection doesn't exist, snap to latest
  const latestVersion = versions.length > 0 ? Math.max(...versions.map((v) => v.version_number)) : 1;
  if (versions.length > 0 && !versions.some((v) => v.version_number === selectedVersion)) {
    setSelectedVersion(latestVersion);
  }

  const canShowDiff = versions.length >= 2;
  const previousVersion = selectedVersion > 1 ? selectedVersion - 1 : null;

  if (versionsLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  // Code artifacts use a different layout
  if (artifact.artifact_type === "code") {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Badge variant={statusVariant[artifact.status]}>
              {statusLabel[artifact.status]}
            </Badge>
            <span className="text-sm text-[var(--color-text-secondary)]">
              v{selectedVersion} &middot; ${artifact.total_cost_usd.toFixed(2)}
            </span>
          </div>
          {artifact.status === "in_review" && (
            <ArtifactActions artifactId={artifact.id} artifactType="code" />
          )}
        </div>
        <CodeArtifactReview artifact={artifact} version={currentVersionData} />
      </div>
    );
  }

  // Prose artifact review
  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <VersionSwitcher
            versions={versions}
            selectedVersion={selectedVersion}
            onSelectVersion={setSelectedVersion}
          />
          {canShowDiff && previousVersion && (
            <Button
              variant="ghost"
              size="xs"
              onClick={() => onShowDiff(previousVersion, selectedVersion)}
            >
              Diff: v{previousVersion} &rarr; v{selectedVersion}
            </Button>
          )}
          <Badge variant={statusVariant[artifact.status]}>
            {statusLabel[artifact.status]}
          </Badge>
        </div>
        {artifact.status === "in_review" && (
          <ArtifactActions artifactId={artifact.id} artifactType="prose" />
        )}
      </div>

      {/* Main content + sidebar */}
      <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
        <div className="min-w-0">
          {fileLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-full" />
            </div>
          ) : (
            <ProseViewer content={fileContent ?? ""} />
          )}
        </div>
        <aside className="lg:border-l lg:border-[var(--color-border-primary)] lg:pl-6">
          <ReviewSidebar version={currentVersionData} />
        </aside>
      </div>

      {/* Floating comment toolbar — only in review status */}
      {artifact.status === "in_review" && (
        <FloatingCommentToolbar artifactId={artifact.id} />
      )}
    </div>
  );
}
