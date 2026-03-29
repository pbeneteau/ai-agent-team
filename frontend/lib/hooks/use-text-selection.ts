"use client";

/**
 * Text selection hook — native Selection API.
 *
 * Ref: TDD-05 Section 12.1
 * Monitors `selectionchange` events within a container element.
 * Captures selected text, character offsets, and bounding rect.
 * Stores in SelectionStore for the floating comment toolbar.
 */

import { useEffect, type RefObject } from "react";
import { useSelectionStore } from "@/lib/stores/selection-store";

export function useTextSelection(containerRef: RefObject<HTMLElement | null>) {
  const setSelection = useSelectionStore((s) => s.setSelection);
  const clearSelection = useSelectionStore((s) => s.clearSelection);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    function handleSelectionChange() {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.rangeCount) {
        clearSelection();
        return;
      }

      const range = selection.getRangeAt(0);

      // Ensure selection is within our container
      if (!container!.contains(range.commonAncestorContainer)) {
        clearSelection();
        return;
      }

      const text = selection.toString().trim();
      if (text.length < 3) {
        clearSelection();
        return;
      }

      // Compute character offsets relative to the container's text content
      const preRange = document.createRange();
      preRange.selectNodeContents(container!);
      preRange.setEnd(range.startContainer, range.startOffset);
      const start = preRange.toString().length;
      const end = start + text.length;

      // Get selection position for floating toolbar
      const domRect = range.getBoundingClientRect();
      const rect = {
        top: domRect.top,
        left: domRect.left,
        width: domRect.width,
        height: domRect.height,
      };

      setSelection(text, { start, end }, rect, null);
    }

    document.addEventListener("selectionchange", handleSelectionChange);
    return () => document.removeEventListener("selectionchange", handleSelectionChange);
  }, [containerRef, setSelection, clearSelection]);
}
