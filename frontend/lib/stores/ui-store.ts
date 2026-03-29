/**
 * UI state store.
 *
 * Ref: TDD-05 Section 4.2
 * Manages sidebar, theme, diff mode, and modals.
 * Persisted to localStorage: sidebarCollapsed, theme, diffMode.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Theme } from "@/lib/theme";

interface UIState {
  // Sidebar
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  // Theme
  theme: Theme;
  setTheme: (theme: Theme) => void;

  // Diff viewer
  diffMode: "unified" | "side-by-side";
  setDiffMode: (mode: "unified" | "side-by-side") => void;

  // Modals
  activeModal: string | null;
  modalProps: Record<string, unknown>;
  openModal: (id: string, props?: Record<string, unknown>) => void;
  closeModal: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // Sidebar
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

      // Theme
      theme: "system",
      setTheme: (theme) => set({ theme }),

      // Diff viewer
      diffMode: "unified",
      setDiffMode: (diffMode) => set({ diffMode }),

      // Modals — not persisted (handled by partialize below)
      activeModal: null,
      modalProps: {},
      openModal: (id, props = {}) => set({ activeModal: id, modalProps: props }),
      closeModal: () => set({ activeModal: null, modalProps: {} }),
    }),
    {
      name: "ui-store",
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        theme: state.theme,
        diffMode: state.diffMode,
      }),
    },
  ),
);
