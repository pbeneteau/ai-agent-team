/**
 * Theme management utilities.
 *
 * Ref: TDD-05 Section 2.5
 * Dark mode via class strategy on <html>.
 * Persisted to localStorage.
 */

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "theme";

export function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "system";
  return (localStorage.getItem(STORAGE_KEY) as Theme) ?? "system";
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  const isDark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  root.classList.toggle("dark", isDark);
  localStorage.setItem(STORAGE_KEY, theme);
}

export function getResolvedTheme(theme: Theme): "light" | "dark" {
  if (theme === "system") {
    if (typeof window === "undefined") return "light";
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return theme;
}
