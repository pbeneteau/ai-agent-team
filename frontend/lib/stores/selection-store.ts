/**
 * Text selection state store.
 *
 * Ref: TDD-05 Section 4.2 (AD-21)
 * Manages text selection for contextual commenting.
 * Native browser Selection API — floating toolbar on selection.
 * Not persisted. Cleared on navigation.
 */

import { create } from "zustand";

interface SelectionState {
  selectedText: string | null;
  selectionRange: { start: number; end: number } | null;
  selectionRect: { top: number; left: number; width: number; height: number } | null;
  filePath: string | null;

  setSelection: (
    text: string,
    range: { start: number; end: number },
    rect: { top: number; left: number; width: number; height: number },
    filePath: string | null,
  ) => void;
  clearSelection: () => void;
}

export const useSelectionStore = create<SelectionState>()((set) => ({
  selectedText: null,
  selectionRange: null,
  selectionRect: null,
  filePath: null,

  setSelection: (text, range, rect, filePath) =>
    set({ selectedText: text, selectionRange: range, selectionRect: rect, filePath }),

  clearSelection: () =>
    set({ selectedText: null, selectionRange: null, selectionRect: null, filePath: null }),
}));
