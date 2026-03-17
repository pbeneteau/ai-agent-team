import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface SectionPanelProps {
  title?: string;
  description?: string;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  tone?: "default" | "muted" | "subtle";
}

const toneClassNames: Record<NonNullable<SectionPanelProps["tone"]>, string> = {
  default: "border-[var(--ops-border)] bg-[var(--ops-surface-strong)] shadow-none",
  muted: "border-[var(--ops-border)] bg-[var(--ops-surface-strong)] shadow-none",
  subtle: "border-[var(--ops-border)] bg-[color:rgba(255,255,251,0.84)] shadow-none",
};

export function SectionPanel({
  title,
  description,
  eyebrow,
  actions,
  children,
  className,
  contentClassName,
  tone = "default",
}: SectionPanelProps) {
  return (
    <section
      className={cn(
        "rounded-[20px] border",
        toneClassNames[tone],
        className,
      )}
    >
      {(eyebrow || title || description || actions) && (
        <div className="flex flex-col gap-3 border-b border-[var(--ops-border)] px-5 py-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0 space-y-1.5">
            {eyebrow ? (
              <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--ops-soft-ink)]">
                {eyebrow}
              </div>
            ) : null}
            {title ? <h2 className="text-[15px] font-semibold tracking-tight text-[var(--ops-ink)]">{title}</h2> : null}
            {description ? (
              <p className="max-w-3xl text-sm leading-6 text-[var(--ops-muted-ink)]">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      )}

      <div className={cn("px-5 py-4", contentClassName)}>{children}</div>
    </section>
  );
}
