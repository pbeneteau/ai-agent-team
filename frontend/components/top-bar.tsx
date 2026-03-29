"use client";

/**
 * Top bar — workspace name, theme toggle, notification area.
 *
 * Ref: TDD-05 Section 3.2
 */

import { Sun, Moon, Monitor } from "lucide-react";
import { useUIStore } from "@/lib/stores/ui-store";
import type { Theme } from "@/lib/theme";

const themeOptions: { value: Theme; icon: React.ElementType; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "System" },
];

export function TopBar() {
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);

  const cycleTheme = () => {
    const order: Theme[] = ["light", "dark", "system"];
    const idx = order.indexOf(theme);
    setTheme(order[(idx + 1) % order.length]);
  };

  const currentOption = themeOptions.find((o) => o.value === theme) ?? themeOptions[2];
  const Icon = currentOption.icon;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-border-primary)] bg-[var(--color-bg-primary)] px-6">
      {/* Workspace name */}
      <div className="text-sm font-medium text-[var(--color-text-primary)]">Workspace</div>

      <div className="flex items-center gap-3">
        {/* Theme toggle */}
        <button
          onClick={cycleTheme}
          className="flex items-center gap-2 rounded-[var(--radius-md)] px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] transition-colors"
          aria-label={`Theme: ${currentOption.label}`}
        >
          <Icon className="h-4 w-4" />
          <span>{currentOption.label}</span>
        </button>
      </div>
    </header>
  );
}
