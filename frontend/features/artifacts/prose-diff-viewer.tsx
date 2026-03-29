"use client";

/**
 * Prose diff viewer — react-diff-viewer-continued with custom theme.
 *
 * Ref: TDD-05 Section 11
 * - Custom theme tokens mapped to design system oklch variables
 * - Unified/side-by-side toggle persisted in Zustand UIStore
 * - Lazy-loaded via next/dynamic (heavy dependency)
 * - Diffs computed on frontend (AD-6)
 */

import { useMemo } from "react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, Columns2, AlignJustify } from "lucide-react";
import { useUIStore } from "@/lib/stores/ui-store";
import { useArtifactFile } from "@/lib/hooks/use-artifacts";

/**
 * Custom diff theme mapped to design system CSS variables.
 * Both light and dark use the same var() references — the variables
 * themselves switch between modes via tokens.css.
 *
 * Ref: TDD-05 Section 11.4
 */
const diffStyles = {
  variables: {
    light: {
      diffViewerBackground: "var(--color-bg-primary)",
      addedBackground: "var(--color-diff-added-bg)",
      addedColor: "var(--color-diff-added-text)",
      removedBackground: "var(--color-diff-removed-bg)",
      removedColor: "var(--color-diff-removed-text)",
      wordAddedBackground: "var(--color-success-subtle)",
      wordRemovedBackground: "var(--color-danger-subtle)",
      gutterBackground: "var(--color-bg-secondary)",
      gutterColor: "var(--color-text-tertiary)",
      codeFoldBackground: "var(--color-bg-tertiary)",
    },
    dark: {
      diffViewerBackground: "var(--color-bg-primary)",
      addedBackground: "var(--color-diff-added-bg)",
      addedColor: "var(--color-diff-added-text)",
      removedBackground: "var(--color-diff-removed-bg)",
      removedColor: "var(--color-diff-removed-text)",
      wordAddedBackground: "var(--color-success-subtle)",
      wordRemovedBackground: "var(--color-danger-subtle)",
      gutterBackground: "var(--color-bg-secondary)",
      gutterColor: "var(--color-text-tertiary)",
      codeFoldBackground: "var(--color-bg-tertiary)",
    },
  },
  line: {
    padding: "4px 8px",
    fontSize: "13px",
    fontFamily: "var(--font-mono)",
  },
};

interface ProseDiffViewerProps {
  artifactId: string;
  oldVersion: number;
  newVersion: number;
  /** First file path in the manifest (prose artifacts typically have one file) */
  filePath: string;
  onBack: () => void;
}

export function ProseDiffViewer({
  artifactId,
  oldVersion,
  newVersion,
  filePath,
  onBack,
}: ProseDiffViewerProps) {
  const diffMode = useUIStore((s) => s.diffMode);
  const setDiffMode = useUIStore((s) => s.setDiffMode);

  const { data: oldContent, isLoading: oldLoading } = useArtifactFile(
    artifactId,
    oldVersion,
    filePath,
  );
  const { data: newContent, isLoading: newLoading } = useArtifactFile(
    artifactId,
    newVersion,
    filePath,
  );

  const isLoading = oldLoading || newLoading;

  // Detect dark mode by checking the html class
  const isDark = useMemo(() => {
    if (typeof document === "undefined") return false;
    return document.documentElement.classList.contains("dark");
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
            Back to review
          </Button>
          <span className="text-sm text-[var(--color-text-secondary)]">
            Comparing v{oldVersion} &rarr; v{newVersion}
          </span>
        </div>

        {/* Mode toggle */}
        <div className="flex rounded-[var(--radius-md)] border border-[var(--color-border-primary)] p-0.5">
          <Button
            variant={diffMode === "unified" ? "secondary" : "ghost"}
            size="xs"
            onClick={() => setDiffMode("unified")}
          >
            <AlignJustify className="h-3.5 w-3.5" />
            Unified
          </Button>
          <Button
            variant={diffMode === "side-by-side" ? "secondary" : "ghost"}
            size="xs"
            onClick={() => setDiffMode("side-by-side")}
          >
            <Columns2 className="h-3.5 w-3.5" />
            Side by Side
          </Button>
        </div>
      </div>

      {/* Diff viewer */}
      <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--color-border-primary)]">
        <ReactDiffViewer
          oldValue={oldContent ?? ""}
          newValue={newContent ?? ""}
          splitView={diffMode === "side-by-side"}
          useDarkTheme={isDark}
          styles={diffStyles}
          compareMethod={DiffMethod.WORDS}
          leftTitle={`v${oldVersion}`}
          rightTitle={`v${newVersion}`}
        />
      </div>
    </div>
  );
}
