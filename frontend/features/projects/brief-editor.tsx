"use client";

/**
 * Project brief editor with auto-save (debounced 1s) and publish.
 *
 * Ref: TDD-05 Section 15.2, TDD-01 Journey J5 Steps 4-6
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Loader2, Save, Upload } from "lucide-react";
import { useProjectContext, useSaveDraft, usePublishBrief } from "@/lib/hooks/use-projects";

interface BriefEditorProps {
  projectId: string;
}

export function BriefEditor({ projectId }: BriefEditorProps) {
  const { data: context, isLoading } = useProjectContext(projectId);
  const saveDraft = useSaveDraft(projectId);
  const publishBrief = usePublishBrief(projectId);

  const [content, setContent] = useState("");
  const [initialized, setInitialized] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initialize content from server
  useEffect(() => {
    if (context && !initialized) {
      setContent(context.draft ?? context.published ?? "");
      setInitialized(true);
    }
  }, [context, initialized]);

  // Auto-save with 1s debounce
  const debouncedSave = useCallback(
    (value: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        saveDraft.mutate(value, {
          onSuccess: () => setLastSaved(new Date()),
          onError: () => toast.error("Failed to save draft"),
        });
      }, 1000);
    },
    [saveDraft],
  );

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setContent(value);
    debouncedSave(value);
  };

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handlePublish = () => {
    // Flush any pending save first
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }

    saveDraft.mutate(content, {
      onSuccess: () => {
        publishBrief.mutate(undefined, {
          onSuccess: () => {
            toast.success("Brief published. All agents have been rebriefed.");
            setLastSaved(new Date());
          },
          onError: (error) => {
            toast.error(error.message || "Failed to publish brief");
          },
        });
      },
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const isDraft = content !== (context?.published ?? "");
  const hasPublished = !!context?.published;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Project Brief</h2>
          {hasPublished && !isDraft && (
            <Badge variant="outline" className="bg-[var(--color-success-subtle)] text-[var(--color-success)]">
              Published
            </Badge>
          )}
          {isDraft && (
            <Badge variant="outline" className="bg-[var(--color-warning-subtle)] text-[var(--color-warning)]">
              Draft
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {lastSaved && (
            <span className="text-xs text-[var(--color-text-tertiary)]">
              <Save className="mr-1 inline h-3 w-3" />
              Saved
            </span>
          )}
          {saveDraft.isPending && (
            <span className="text-xs text-[var(--color-text-tertiary)]">
              <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />
              Saving...
            </span>
          )}
        </div>
      </div>

      <Textarea
        value={content}
        onChange={handleChange}
        placeholder="Write the project-level context that all agents will be briefed on. E.g., company background, goals, constraints, key stakeholders..."
        className="min-h-[300px]"
      />

      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--color-text-tertiary)]">
          {hasPublished && context?.published_at
            ? `Last published: ${new Date(context.published_at).toLocaleDateString()}`
            : "Not yet published"}
        </p>
        <Button
          onClick={handlePublish}
          disabled={publishBrief.isPending || !content.trim()}
        >
          {publishBrief.isPending ? (
            <>
              <Loader2 className="animate-spin" />
              Publishing...
            </>
          ) : (
            <>
              <Upload className="h-4 w-4" />
              Publish Brief
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
