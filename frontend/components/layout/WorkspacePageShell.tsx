"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface WorkspacePageShellProps {
  eyebrow?: ReactNode;
  title: string;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}

export function WorkspacePageShell({
  eyebrow,
  title,
  description,
  meta,
  actions,
  children,
  className,
  contentClassName,
}: WorkspacePageShellProps) {
  return (
    <div className={cn("relative flex h-full min-h-0 flex-col overflow-hidden bg-[var(--ops-canvas)]", className)}>
      <div className="min-h-0 flex-1 p-3 md:p-4 lg:p-5">
        <div className="mx-auto flex h-full max-w-[1600px] flex-col overflow-hidden rounded-[30px] border border-[var(--ops-border)] bg-[var(--ops-surface)] shadow-[var(--ops-shadow)] backdrop-blur">
          <div className="border-b border-[var(--ops-border)] bg-[color:rgba(255,254,249,0.76)] px-5 py-4 backdrop-blur md:px-7 md:py-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0 space-y-2.5">
                {eyebrow ? <div className="flex flex-wrap items-center gap-2">{eyebrow}</div> : null}
                <div className="space-y-1.5">
                  <h1 className="text-2xl font-semibold tracking-tight text-[var(--ops-ink)] md:text-[1.95rem]">
                    {title}
                  </h1>
                  {description ? (
                    <p className="max-w-3xl text-sm leading-6 text-[var(--ops-muted-ink)]">{description}</p>
                  ) : null}
                </div>
                {meta ? (
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--ops-muted-ink)]">
                    {meta}
                  </div>
                ) : null}
              </div>

              {actions ? <div className="flex flex-wrap items-center gap-2 xl:justify-end">{actions}</div> : null}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top,rgba(255,255,253,0.98),rgba(247,244,237,0.92))]">
            <div className={cn("mx-auto max-w-7xl space-y-5 px-5 py-5 md:px-7", contentClassName)}>{children}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
