"use client";

/**
 * Sidebar navigation.
 *
 * Ref: TDD-05 Section 3.3, Section 18.2 (responsive)
 * Items: Projects, Agency Roster, Settings
 * Collapsible via Zustand UIStore.
 * < md: hidden (handled by layout). md-lg: icon-only. > lg: full.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Code2, Users, Settings, ChevronLeft, ChevronRight, Terminal } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/lib/stores/ui-store";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

const navItems: NavItem[] = [
  { label: "Repos", href: "/projects", icon: Code2 },
  { label: "Team", href: "/roster", icon: Users },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  // On md screens, force icon-only. On lg+, user controls.
  const isIconOnly = collapsed;

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r border-[var(--color-border-primary)] bg-[var(--color-bg-secondary)] transition-[width] duration-200 motion-reduce:transition-none",
        isIconOnly ? "w-16" : "w-16 lg:w-[260px]",
      )}
      aria-label="Main navigation"
    >
      {/* Logo / Brand */}
      <div className="flex h-14 items-center gap-2 border-b border-[var(--color-border-primary)] px-4">
        <Terminal className="h-5 w-5 shrink-0 text-[var(--color-accent)]" />
        {!isIconOnly && (
          <span className="hidden truncate text-sm font-semibold text-[var(--color-text-primary)] lg:block">
            Code Factory
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2 py-3">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href || pathname.startsWith(item.href + "/");

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-[var(--radius-md)] px-3 py-2 text-sm transition-colors motion-reduce:transition-none",
                isActive
                  ? "bg-[var(--color-accent-subtle)] text-[var(--color-accent)] font-medium"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)]",
                "justify-center px-2 lg:justify-start lg:px-3",
                isIconOnly && "justify-center px-2",
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!isIconOnly && <span className="hidden lg:block">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle (only visible on lg+) */}
      <div className="hidden border-t border-[var(--color-border-primary)] p-2 lg:block">
        <button
          onClick={toggleSidebar}
          className="flex w-full items-center justify-center rounded-[var(--radius-md)] py-2 text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)] transition-colors motion-reduce:transition-none"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>
    </aside>
  );
}
