"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChevronRight,
  Sparkles,
} from "lucide-react";

import { SIDEBAR_NAV_ITEMS } from "@/lib/config/navigation";
import {
  OPERATOR_DESK_LABEL,
  OPERATOR_DESK_SUBTITLE,
  OPS_DESK_SUBTITLE,
  OPS_DESK_TITLE,
} from "@/lib/config/page-copy";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-[84px] shrink-0 flex-col border-r border-[var(--ops-border)] bg-[color:rgba(248,246,239,0.8)] px-3 py-4 lg:w-[216px]">
      <div className="flex items-center gap-3 px-2 pb-4">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-[18px] border border-[var(--ops-border)] bg-[var(--ops-surface-strong)] shadow-[0_18px_36px_-28px_rgba(15,23,42,0.3)]">
          <div className="flex size-8 items-center justify-center rounded-2xl bg-[radial-gradient(circle_at_top,rgba(120,119,255,0.5),rgba(15,23,42,0.98))] text-white">
            <Sparkles className="size-4" />
          </div>
        </div>
        <div className="hidden min-w-0 lg:block">
          <p className="text-sm font-semibold tracking-tight text-[var(--ops-ink)]">{OPS_DESK_TITLE}</p>
          <p className="mt-1 text-[11px] leading-5 text-[var(--ops-muted-ink)]">
            {OPS_DESK_SUBTITLE}
          </p>
        </div>
      </div>

      <nav className="mt-2 flex flex-1 flex-col gap-1.5">
        {SIDEBAR_NAV_ITEMS.map(({ href, icon: Icon, label, description, aliases }) => {
          const isActive = aliases.some((matcher) => matcher.test(pathname));
          return (
            <Link
              key={href}
              href={href}
              title={label}
              aria-label={label}
              className={cn(
                "group flex items-center gap-3 rounded-[18px] border px-3 py-2.5 transition-all duration-200",
                isActive
                  ? "border-[var(--ops-border)] bg-[var(--ops-surface-strong)] text-[var(--ops-ink)] shadow-[0_14px_28px_-24px_rgba(15,23,42,0.22)]"
                  : "border-transparent text-[var(--ops-muted-ink)] hover:border-[var(--ops-border)] hover:bg-[color:rgba(255,255,252,0.82)] hover:text-[var(--ops-ink)]"
              )}
            >
              <div
                className={cn(
                  "flex size-10 shrink-0 items-center justify-center rounded-[16px] border transition-colors",
                  isActive
                    ? "border-[var(--ops-border)] bg-primary/8 text-primary"
                    : "border-transparent bg-[var(--ops-surface-muted)] text-[var(--ops-muted-ink)] group-hover:border-[var(--ops-border)] group-hover:bg-[var(--ops-surface-strong)]"
                )}
              >
                <Icon className="size-4 shrink-0" />
              </div>

              <div className="hidden min-w-0 flex-1 lg:block">
                <p className="truncate text-sm font-medium">{label}</p>
                <p className="truncate text-[11px] text-[var(--ops-muted-ink)] opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100">
                  {description}
                </p>
              </div>

              <ChevronRight
                className={cn(
                  "hidden size-4 shrink-0 transition-all lg:block",
                  isActive
                    ? "translate-x-0 text-[var(--ops-ink)]/60"
                    : "-translate-x-1 text-transparent group-hover:translate-x-0 group-hover:text-[var(--ops-muted-ink)]"
                )}
              />
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto flex items-center gap-3 rounded-[18px] border border-[var(--ops-border)] bg-[color:rgba(255,255,252,0.72)] px-3 py-2.5">
        <button
          type="button"
          title="Profile"
          className="flex size-10 shrink-0 items-center justify-center rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-strong)] text-sm font-medium text-[var(--ops-ink)] shadow-[0_12px_24px_-24px_rgba(15,23,42,0.2)]"
        >
          PB
        </button>
        <div className="hidden min-w-0 lg:block">
          <p className="text-sm font-medium text-[var(--ops-ink)]">{OPERATOR_DESK_LABEL}</p>
          <p className="mt-1 text-[11px] text-[var(--ops-muted-ink)]">{OPERATOR_DESK_SUBTITLE}</p>
        </div>
      </div>
    </aside>
  );
}
