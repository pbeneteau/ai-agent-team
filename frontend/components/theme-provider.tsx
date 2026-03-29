"use client";

/**
 * Theme provider — applies theme on mount, listens for system changes.
 *
 * Ref: TDD-05 Section 2.5
 */

import { useEffect } from "react";
import { applyTheme } from "@/lib/theme";
import { useUIStore } from "@/lib/stores/ui-store";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useUIStore((s) => s.theme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Listen for system preference changes when in "system" mode
  useEffect(() => {
    if (theme !== "system") return;

    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");

    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [theme]);

  return <>{children}</>;
}
