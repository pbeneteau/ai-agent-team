"use client";

/**
 * Settings layout with tab navigation.
 */

import { usePathname } from "next/navigation";
import Link from "next/link";
import { Settings, GitBranch, Plug, BarChart3, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";

const tabs = [
  { label: "Workspace", href: "/settings/workspace", icon: Building2 },
  { label: "Git Providers", href: "/settings/git", icon: GitBranch },
  { label: "MCP", href: "/settings/mcp", icon: Plug },
  { label: "Usage", href: "/settings/usage", icon: BarChart3 },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Settings className="h-6 w-6 text-[var(--color-accent)]" />
        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">Settings</h1>
      </div>

      <nav className="flex gap-1 border-b border-[var(--color-border-primary)]">
        {tabs.map((tab) => {
          const isActive = pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "relative flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "text-[var(--color-text-primary)]"
                  : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]",
              )}
            >
              <tab.icon className="h-3.5 w-3.5" />
              {tab.label}
              {isActive && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--color-accent)]" />}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
