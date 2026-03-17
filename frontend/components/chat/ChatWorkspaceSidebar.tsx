"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { ArrowRight, FileText, Layers3 } from "lucide-react";

import type { Document } from "@/lib/api";
import type { ChatPanelMode } from "@/components/chat/chat-shell";
import { getWorkspaceLinks } from "@/components/chat/chat-shell";
import { isProductNavItemActive } from "@/lib/config/product-navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ChatWorkspaceSidebarProps {
  mode: ChatPanelMode;
  title: string;
  description: string;
  contextLabel: string;
  showDocs: boolean;
  documents: Document[];
  attachedDocuments: Document[];
}

export function ChatWorkspaceSidebar({
  mode,
  title,
  description,
  contextLabel,
  showDocs,
  documents,
  attachedDocuments,
}: ChatWorkspaceSidebarProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const workflowSummary =
    description ||
    (mode === "design-team"
      ? "Team design stays inside Alex with explicit review before creation."
      : "Context and attached sources stay available without taking over the conversation.");

  return (
    <aside className="hidden h-full w-[244px] shrink-0 flex-col border-r border-[var(--ops-border)] bg-[var(--ops-surface)] 2xl:flex">
      <div className="border-b border-[var(--ops-border)] px-4 py-4">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-[12px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)]">
              <Layers3 className="size-4 text-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--ops-ink)]">{title}</p>
              <p className="text-[11px] text-[var(--ops-muted-ink)]">{contextLabel}</p>
            </div>
          </div>
          <p className="text-sm leading-6 text-[var(--ops-muted-ink)]">{workflowSummary}</p>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="text-[11px]">
              {attachedDocuments.length} attached
            </Badge>
            <Badge variant="outline" className="text-[11px]">
              {documents.length} shared sources
            </Badge>
          </div>
        </div>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
        <section className="space-y-3">
          <div className="px-1 text-[11px] font-medium uppercase tracking-[0.24em] text-muted-foreground">
            Alex modes
          </div>
          <div className="space-y-2">
            {getWorkspaceLinks().map((link) => {
              const isActive = isProductNavItemActive(link, pathname, searchParams);
              return (
                <Link
                  key={link.id}
                  href={link.href}
                  className={cn(
                    "flex items-start gap-3 rounded-[14px] border px-3 py-2.5 transition-colors",
                    isActive
                      ? "border-[var(--ops-border)] bg-[var(--ops-surface-elevated)]"
                      : "border-transparent bg-transparent hover:border-[var(--ops-border-soft)] hover:bg-[var(--ops-control-hover)]",
                  )}
                >
                  <div
                    className={cn(
                      "mt-0.5 flex size-7 items-center justify-center rounded-[12px]",
                      isActive ? "bg-primary/10 text-primary" : "bg-[var(--ops-control)] text-muted-foreground",
                    )}
                  >
                    <link.Icon className="size-4" />
                  </div>

                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-foreground">{link.label}</p>
                      {isActive ? (
                        <Badge variant="secondary" className="text-[10px]">
                          Active
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </section>

        <section className="space-y-3">
          <div className="px-1 text-[11px] font-medium uppercase tracking-[0.24em] text-muted-foreground">
            Attached sources
          </div>
          <Card className="gap-0">
            <CardContent className="space-y-3 p-4">
              {attachedDocuments.length === 0 ? (
                <p className="text-sm leading-6 text-muted-foreground">No source attached to this turn.</p>
              ) : (
                attachedDocuments.map((document) => (
                  <div
                    key={document.id}
                    className="flex items-start gap-3 rounded-[14px] border border-[var(--ops-border)] bg-[var(--ops-surface-muted)] px-3 py-3"
                  >
                    <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-[12px] bg-primary/8 text-primary">
                      <FileText className="size-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">{document.filename}</p>
                      <p className="mt-1 text-xs text-muted-foreground">Attached to the current workflow</p>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </section>

        {showDocs ? (
          <section className="space-y-3">
            <div className="px-1 text-[11px] font-medium uppercase tracking-[0.24em] text-muted-foreground">
              Available sources
            </div>

            <Card className="gap-0">
              <CardContent className="space-y-4 p-4">
                <p className="text-xs leading-5 text-muted-foreground">Use <code>@document-name</code> in the composer to attach a source.</p>

                {documents.length === 0 ? (
                  <div className="rounded-[14px] border border-dashed border-[var(--ops-border-strong)] bg-[var(--ops-surface-muted)] px-3 py-4 text-sm text-muted-foreground">
                    No shared documents yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {documents.slice(0, 6).map((document) => (
                      <div
                        key={document.id}
                        className="flex items-start gap-3 rounded-[14px] border border-[var(--ops-border)] bg-[var(--ops-surface-muted)] px-3 py-3"
                      >
                        <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-[12px] bg-primary/8 text-primary">
                          <FileText className="size-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground">{document.filename}</p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            @{document.filename} · {document.chunk_count} chunk{document.chunk_count > 1 ? "s" : ""}
                          </p>
                          {document.description ? (
                            <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
                              {document.description}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <Link href="/project-context?section=documents">
                  <Button variant="outline" className="w-full gap-2">
                    Open Context
                    <ArrowRight className="size-4" />
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </section>
        ) : null}
      </div>
    </aside>
  );
}
