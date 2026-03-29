"use client";

/**
 * Floating comment toolbar — appears above selected text.
 *
 * Ref: TDD-05 Section 12.2
 * Positioned using selectionRect from SelectionStore.
 * Clicking "Comment" opens an inline form to submit iteration feedback.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { MessageSquare, Send, X, Loader2 } from "lucide-react";
import { useSelectionStore } from "@/lib/stores/selection-store";
import { useIterateArtifact } from "@/lib/hooks/use-artifacts";

interface FloatingCommentToolbarProps {
  artifactId: string;
}

export function FloatingCommentToolbar({ artifactId }: FloatingCommentToolbarProps) {
  const selectedText = useSelectionStore((s) => s.selectedText);
  const selectionRange = useSelectionStore((s) => s.selectionRange);
  const selectionRect = useSelectionStore((s) => s.selectionRect);
  const clearSelection = useSelectionStore((s) => s.clearSelection);

  const [showForm, setShowForm] = useState(false);
  const [instruction, setInstruction] = useState("");
  const iterateArtifact = useIterateArtifact(artifactId);
  const formRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);

  // Portal mount check
  useEffect(() => {
    setMounted(true);
  }, []);

  // Close on Escape
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setShowForm(false);
        setInstruction("");
        clearSelection();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [clearSelection]);

  // Close form when selection is cleared externally
  useEffect(() => {
    if (!selectedText) {
      setShowForm(false);
      setInstruction("");
    }
  }, [selectedText]);

  const handleSubmit = useCallback(() => {
    if (!instruction.trim() || !selectedText || !selectionRange) return;
    iterateArtifact.mutate(
      {
        instruction: instruction.trim(),
        highlighted_text: selectedText,
        highlight_start: selectionRange.start,
        highlight_end: selectionRange.end,
      },
      {
        onSuccess: () => {
          toast.success("Iteration started");
          setShowForm(false);
          setInstruction("");
          clearSelection();
          window.getSelection()?.removeAllRanges();
        },
        onError: (error) => toast.error(error.message || "Failed to submit comment"),
      },
    );
  }, [instruction, selectedText, selectionRange, iterateArtifact, clearSelection]);

  if (!mounted || !selectedText || !selectionRect) return null;

  // Position: centered above the selection, with flip-below if near viewport top
  const toolbarWidth = 200;
  const gap = 8;
  const left = selectionRect.left + selectionRect.width / 2 - toolbarWidth / 2;
  const aboveTop = selectionRect.top - gap;
  const belowTop = selectionRect.top + selectionRect.height + gap;
  const flipBelow = aboveTop < 60; // flip if too close to top
  const top = flipBelow ? belowTop : aboveTop;

  return createPortal(
    <div
      ref={formRef}
      className="fixed z-[100]"
      style={{
        top: `${top}px`,
        left: `${Math.max(8, left)}px`,
        transform: flipBelow ? "translateY(0)" : "translateY(-100%)",
      }}
    >
      {!showForm ? (
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-bg-inverse)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-inverse)] shadow-[var(--shadow-lg)] transition-colors hover:opacity-90"
        >
          <MessageSquare className="h-3.5 w-3.5" />
          Comment
        </button>
      ) : (
        <div className="w-72 rounded-[var(--radius-lg)] border border-[var(--color-border-primary)] bg-[var(--color-bg-secondary)] p-3 shadow-[var(--shadow-lg)]">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--color-text-primary)]">Add comment</span>
            <button
              onClick={() => {
                setShowForm(false);
                setInstruction("");
                clearSelection();
              }}
              className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="mb-2 line-clamp-2 rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] px-2 py-1 text-[10px] italic text-[var(--color-text-secondary)]">
            &ldquo;{selectedText.slice(0, 80)}{selectedText.length > 80 ? "..." : ""}&rdquo;
          </p>
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="Describe what should change..."
            className="mb-2 w-full resize-none rounded-[var(--radius-sm)] border border-[var(--color-border-primary)] bg-transparent p-2 text-xs outline-none placeholder:text-[var(--color-text-tertiary)] focus-visible:border-[var(--color-accent)] focus-visible:ring-1 focus-visible:ring-[var(--color-accent)]"
            rows={2}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
            }}
          />
          <Button
            size="xs"
            className="w-full"
            onClick={handleSubmit}
            disabled={!instruction.trim() || iterateArtifact.isPending}
          >
            {iterateArtifact.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Send className="h-3 w-3" />
            )}
            Submit Feedback
          </Button>
        </div>
      )}
    </div>,
    document.body,
  );
}
