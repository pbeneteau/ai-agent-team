import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface StatBlockProps {
  label: string;
  value: string | number;
  description?: string;
  icon?: ReactNode;
  tone?: "default" | "accent" | "positive" | "warning" | "danger";
  className?: string;
}

const toneClassNames: Record<NonNullable<StatBlockProps["tone"]>, string> = {
  default: "bg-[var(--ops-surface-strong)] text-[var(--ops-ink)]",
  accent: "bg-[color:rgba(79,70,229,0.06)] text-[var(--ops-ink)]",
  positive: "bg-[var(--ops-signal-positive-bg)] text-[var(--ops-signal-positive-ink)]",
  warning: "bg-[var(--ops-signal-warning-bg)] text-[var(--ops-signal-warning-ink)]",
  danger: "bg-[var(--ops-signal-danger-bg)] text-[var(--ops-signal-danger-ink)]",
};

export function StatBlock({
  label,
  value,
  description,
  icon,
  tone = "default",
  className,
}: StatBlockProps) {
  return (
    <div
      className={cn(
        "rounded-[18px] border border-[var(--ops-border)] px-4 py-3.5",
        toneClassNames[tone],
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--ops-soft-ink)]">
            {label}
          </p>
          <p className="mt-1.5 text-[1.75rem] font-semibold tracking-tight">{value}</p>
          {description ? (
            <p className="mt-1 text-xs leading-5 text-[var(--ops-muted-ink)]">{description}</p>
          ) : null}
        </div>
        {icon ? (
          <div className="flex size-9 shrink-0 items-center justify-center rounded-[14px] bg-white/72 text-[var(--ops-ink)]">
            {icon}
          </div>
        ) : null}
      </div>
    </div>
  );
}
