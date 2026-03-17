import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface EmptyStateProps {
  title?: string;
  description: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "rounded-[18px] border border-dashed border-[var(--ops-border-strong)] bg-[color:rgba(252,251,247,0.86)] px-5 py-5 text-sm text-[var(--ops-muted-ink)]",
        className,
      )}
    >
      {title ? <p className="text-sm font-semibold text-[var(--ops-ink)]">{title}</p> : null}
      <p className={cn("leading-6", title ? "mt-2" : "")}>{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
