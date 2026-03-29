"use client";

/**
 * Code artifact review — file tree + syntax-highlighted viewer + git context.
 *
 * Phase 6 of CODE_FACTORY_UI_OVERHAUL.md
 *
 * Layout:
 *   ┌─────────────────────────────────────────────┐
 *   │ Git context bar (branch, PR, file count)     │
 *   ├──────────────┬──────────────────────────────┤
 *   │ File tree    │ Code viewer                   │
 *   │ (sidebar)    │ (syntax highlighted)          │
 *   │              │                               │
 *   │              │                               │
 *   ├──────────────┴──────────────────────────────┤
 *   │ Feedback form                                │
 *   └─────────────────────────────────────────────┘
 */

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ExternalLink,
  GitBranch,
  FileCode,
  Send,
  Loader2,
  Info,
} from "lucide-react";
import { useIterateArtifact, useArtifactFile } from "@/lib/hooks/use-artifacts";
import { FileTree } from "./file-tree";
import { CodeViewer } from "./code-viewer";
import type { ArtifactResponse, VersionItem } from "@/lib/types/api";

interface CodeArtifactReviewProps {
  artifact: ArtifactResponse;
  version: VersionItem | null;
}

export function CodeArtifactReview({ artifact, version }: CodeArtifactReviewProps) {
  const fileManifest = version?.file_manifest ?? [];
  const [selectedFile, setSelectedFile] = useState(fileManifest[0]?.path ?? "");
  const [feedback, setFeedback] = useState("");
  const iterateArtifact = useIterateArtifact(artifact.id);

  const { data: fileContent, isLoading: fileLoading } = useArtifactFile(
    artifact.id,
    version?.version_number ?? 1,
    selectedFile,
  );

  const prUrl = artifact.git_pr_url;
  const prNumber = artifact.git_pr_number;
  const branch = artifact.git_feature_branch;
  const baseBranch = artifact.git_base_branch;

  const handleSubmitFeedback = useCallback(() => {
    if (!feedback.trim()) return;
    iterateArtifact.mutate(
      {
        instruction: feedback.trim(),
        file_path: selectedFile || undefined,
      },
      {
        onSuccess: () => {
          toast.success("Iteration started");
          setFeedback("");
        },
        onError: (error) => toast.error(error.message || "Failed to submit feedback"),
      },
    );
  }, [feedback, selectedFile, iterateArtifact]);

  const handleLineClick = useCallback(
    (lineNumber: number) => {
      if (artifact.status !== "in_review") return;
      // Pre-fill feedback with file + line context
      setFeedback(`[${selectedFile}:${lineNumber}] `);
    },
    [selectedFile, artifact.status],
  );

  // Compute total size
  const totalBytes = fileManifest.reduce((sum, f) => sum + f.size_bytes, 0);
  const totalKB = (totalBytes / 1024).toFixed(1);

  return (
    <div className="space-y-4">
      {/* Git context bar */}
      <div className="flex flex-wrap items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border-primary)] bg-[var(--color-bg-secondary)] px-4 py-2.5">
        {branch && (
          <span className="flex items-center gap-1.5 text-xs font-mono text-[var(--color-text-primary)]">
            <GitBranch className="h-3.5 w-3.5 text-[var(--color-text-secondary)]" />
            {branch}
          </span>
        )}
        {baseBranch && branch && (
          <span className="text-xs text-[var(--color-text-tertiary)]">
            &larr; {baseBranch}
          </span>
        )}
        {prUrl && prNumber && (
          <a
            href={prUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-[var(--color-accent)] hover:underline"
          >
            <ExternalLink className="h-3 w-3" />
            PR #{prNumber}
          </a>
        )}
        <span className="ml-auto flex items-center gap-1 text-xs text-[var(--color-text-tertiary)]">
          <FileCode className="h-3 w-3" />
          {fileManifest.length} file{fileManifest.length !== 1 ? "s" : ""} &middot; {totalKB} KB
        </span>
      </div>

      {/* File tree + code viewer */}
      {fileManifest.length > 0 ? (
        <div className="grid grid-cols-[220px_1fr] rounded-[var(--radius-lg)] border border-[var(--color-border-primary)] overflow-hidden min-h-[400px]">
          {/* File tree sidebar */}
          <div className="border-r border-[var(--color-border-primary)] bg-[var(--color-bg-secondary)] overflow-y-auto">
            <div className="px-3 py-2 text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wider">
              Files
            </div>
            <FileTree
              files={fileManifest}
              selectedPath={selectedFile}
              onSelectFile={setSelectedFile}
            />
          </div>

          {/* Code viewer */}
          <div className="overflow-auto bg-[#0d1117]">
            {!selectedFile ? (
              <div className="flex items-center justify-center h-full text-sm text-[var(--color-text-tertiary)]">
                Select a file to view
              </div>
            ) : fileLoading ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-5/6" />
              </div>
            ) : (
              <CodeViewer
                content={fileContent ?? ""}
                filePath={selectedFile}
                onLineClick={artifact.status === "in_review" ? handleLineClick : undefined}
              />
            )}
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center gap-2 rounded-[var(--radius-lg)] border border-[var(--color-border-primary)] py-16">
          <FileCode className="h-8 w-8 text-[var(--color-text-tertiary)]" />
          <p className="text-sm text-[var(--color-text-secondary)]">
            No files in this version yet.
          </p>
        </div>
      )}

      {/* Feedback form — only in review */}
      {artifact.status === "in_review" && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
            Feedback{" "}
            <span className="font-normal text-[var(--color-text-tertiary)]">
              (click a line number to reference it, or use GitHub)
            </span>
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
      )}

      {/* Auto-approval note */}
      {prUrl && (
        <div className="flex items-start gap-2 rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)] p-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-text-tertiary)]" />
          <p className="text-xs text-[var(--color-text-secondary)]">
            This task will be automatically approved when the PR is merged on GitHub.
          </p>
        </div>
      )}
    </div>
  );
}
