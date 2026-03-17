"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { WorkspaceShellArchetype } from "@/components/layout/page-archetypes";

interface WorkspacePageShellProps {
  eyebrow?: ReactNode;
  title: string;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  archetype?: WorkspaceShellArchetype;
  headerMode?: "default" | "compact";
  bodyWidth?: "wide" | "content";
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
  archetype = "command-center",
  headerMode = "default",
  bodyWidth = "wide",
}: WorkspacePageShellProps) {
  const compactHeader = headerMode === "compact";
  const isCollection = archetype === "collection";
  const isDetail = archetype === "detail";

  return (
    <div
      data-page-archetype={archetype}
      className={cn("relative flex h-full min-h-0 flex-col overflow-hidden bg-[var(--ops-canvas)]", className)}
    >
      <div
        className={cn(
          "min-h-0 flex-1",
          isDetail ? "px-4 py-4 md:px-5 md:py-5" : "px-3 py-3 md:px-4 md:py-4 lg:px-5 lg:py-5",
        )}
      >
        <div
          className={cn(
            "mx-auto flex h-full max-w-[1600px] flex-col overflow-hidden border",
            isCollection
              ? "rounded-[20px] border-[var(--ops-border)] bg-[var(--ops-surface)] shadow-[0_10px_22px_-20px_rgba(15,23,42,0.12)]"
              : isDetail
                ? "rounded-[20px] border-[var(--ops-border)] bg-[var(--ops-surface)] shadow-[0_10px_24px_-22px_rgba(15,23,42,0.12)]"
                : "rounded-[22px] border-[var(--ops-border)] bg-[var(--ops-surface)] shadow-[0_12px_28px_-24px_rgba(15,23,42,0.14)]",
          )}
        >
          <div
            className={cn(
              "border-b border-[var(--ops-border)] bg-[var(--ops-surface-strong)]",
              compactHeader ? "px-5 py-4 md:px-6" : "px-5 py-4 md:px-6 md:py-5",
            )}
          >
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0 space-y-2.5">
                {eyebrow ? <div className="flex flex-wrap items-center gap-2">{eyebrow}</div> : null}
                <div className={cn(compactHeader ? "space-y-1" : "space-y-1.5")}>
                  <h1
                    className={cn(
                      "font-semibold tracking-tight text-[var(--ops-ink)]",
              compactHeader ? "text-[1.6rem] md:text-[1.78rem]" : "text-[1.95rem] md:text-[2.1rem]",
                    )}
                  >
                    {title}
                  </h1>
                  {description ? (
                    <p
                      className={cn(
                        "max-w-3xl text-[var(--ops-muted-ink)]",
                        compactHeader ? "text-sm leading-6" : "text-sm leading-6",
                      )}
                    >
                      {description}
                    </p>
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

          <div
            className={cn(
              "min-h-0 flex-1 overflow-y-auto",
              isCollection
                ? "bg-[var(--ops-surface-muted)]"
                : "bg-[color:rgba(249,247,241,0.92)]",
            )}
          >
            <div
              className={cn(
                "mx-auto space-y-5 px-5 py-5 md:px-6",
                bodyWidth === "content" ? "max-w-5xl" : "max-w-7xl",
                isDetail ? "space-y-4" : "",
                contentClassName,
              )}
            >
              {children}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
