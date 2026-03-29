"use client";

/**
 * Code artifact review — PR link, file list, optional feedback form.
 *
 * Ref: TDD-05 Section 10.3, TDD-01 Journey J3 Steps 10-13
 *
 * Key differences from prose review:
 * - No in-app diff viewer — PR link is the primary CTA
 * - File list from file_manifest (not rendered in-app)
 * - Optional feedback form for in-app iteration
 * - No Approve button — approval is via PR merge (detected by webhook)
 */

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ExternalLink, FileCode, Send, Loader2, Info } from "lucide-react";
import { useIterateArtifact } from "@/lib/hooks/use-artifacts";
import { ReviewSidebar } from "./review-sidebar";
import type { ArtifactResponse, VersionItem } from "@/lib/types/api";

interface CodeArtifactReviewProps {
  artifact: ArtifactResponse;
  version: VersionItem | null;
}

export function CodeArtifactReview({ artifact, version }: CodeArtifactReviewProps) {
  const [feedback, setFeedback] = useState("");
  const iterateArtifact = useIterateArtifact(artifact.id);

  const fileManifest = version?.file_manifest ?? [];
  const prUrl = artifact.git_pr_url;
  const prNumber = artifact.git_pr_number;

  const handleSubmitFeedback = useCallback(() => {
    if (!feedback.trim()) return;
    iterateArtifact.mutate(
      { instruction: feedback.trim() },
      {
        onSuccess: () => {
          toast.success("Iteration started");
          setFeedback("");
        },
        onError: (error) => toast.error(error.message || "Failed to submit feedback"),
      },
    );
  }, [feedback, iterateArtifact]);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
      {/* Main panel */}
      <div className="space-y-6">
        {/* PR Link */}
        {prUrl && (
          <a
            href={prUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-accent)] bg-[var(--color-accent-subtle)] p-4 transition-colors hover:bg-[var(--color-accent-subtle)]/80"
          >
            <ExternalLink className="h-5 w-5 shrink-0 text-[var(--color-accent)]" />
            <div>
              <p className="text-sm font-medium text-[var(--color-accent)]">
                View Pull Request on GitHub
              </p>
              {prNumber && (
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {artifact.git_repo_url} #{prNumber}
                </p>
              )}
            </div>
          </a>
        )}

        {/* File list */}
        {fileManifest.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-medium text-[var(--color-text-primary)]">
              Files changed ({fileManifest.length})
            </h3>
            <div className="divide-y divide-[var(--color-border-primary)] rounded-[var(--radius-md)] border border-[var(--color-border-primary)]">
              {fileManifest.map((file) => (
                <div key={file.path} className="flex items-center gap-2 px-3 py-2">
                  <FileCode className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-tertiary)]" />
                  <span className="truncate font-mono text-xs text-[var(--color-text-primary)]">
                    {file.path}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <Separator />

        {/* Feedback form */}
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
            Feedback <span className="font-normal text-[var(--color-text-tertiary)]">(optional &mdash; or use GitHub)</span>
          </h3>
          <div className="flex gap-2">
            <Input
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Describe what should change..."
              onKeyDown={(e) => e.key === "Enter" && handleSubmitFeedback()}
            />
            <Button
              onClick={handleSubmitFeedback}
              disabled={!feedback.trim() || iterateArtifact.isPending}
            >
              {iterateArtifact.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Submit
            </Button>
          </div>
        </div>

        {/* Auto-approval note */}
        <div className="flex items-start gap-2 rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)] p-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-text-tertiary)]" />
          <p className="text-xs text-[var(--color-text-secondary)]">
            This artifact will be automatically approved when the PR is merged on GitHub.
          </p>
        </div>
      </div>

      {/* Sidebar */}
      <aside className="space-y-4">
        <ReviewSidebar version={version} />
      </aside>
    </div>
  );
}
