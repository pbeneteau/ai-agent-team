"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowRight, FileText, Layers3 } from "lucide-react";

import type { Document } from "@/lib/api";
import type { ChatPanelMode } from "@/components/chat/chat-shell";
import { getWorkspaceLinks } from "@/components/chat/chat-shell";
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
  const memoryScopeLabel =
    mode === "team-builder"
      ? "Local memory for team design"
      : "Local orchestration memory";

  return (
    <aside className="hidden h-full w-[272px] shrink-0 flex-col border-r border-[var(--ops-border)] bg-[color:rgba(252,251,246,0.86)] xl:flex">
      <div className="border-b border-[var(--ops-border)] px-5 py-5">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="flex size-10 items-center justify-center rounded-2xl border border-[var(--ops-border)] bg-[var(--ops-surface-strong)] shadow-[0_10px_30px_-20px_rgba(15,23,42,0.24)]">
              <Layers3 className="size-4 text-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--ops-ink)]">{title}</p>
              <p className="text-xs text-[var(--ops-muted-ink)]">{contextLabel}</p>
            </div>
          </div>
          <p className="text-sm leading-6 text-[var(--ops-muted-ink)]">{description}</p>
          <div className="rounded-2xl border border-[var(--ops-border)] bg-[var(--ops-surface-strong)] px-3 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--ops-muted-ink)]">
              Memory scope
            </p>
            <p className="mt-2 text-sm text-[var(--ops-ink)]">{memoryScopeLabel}</p>
            <p className="mt-1 text-xs leading-5 text-[var(--ops-muted-ink)]">
              The global brief and shared documents live in Brief & Documents. Alex consumes them, but does not replace them.
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-4 py-5">
        <section className="space-y-3">
          <div className="px-1 text-[11px] font-medium uppercase tracking-[0.24em] text-muted-foreground">
            Alex modes
          </div>
          <div className="space-y-2">
            {getWorkspaceLinks().map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "flex items-start gap-3 rounded-2xl border px-3 py-3 transition-all",
                    isActive
                      ? "border-black/6 bg-white shadow-[0_16px_32px_-24px_rgba(15,23,42,0.24)]"
                      : "border-transparent bg-transparent hover:border-black/5 hover:bg-white/80",
                  )}
                >
                  <div
                    className={cn(
                      "mt-0.5 flex size-9 items-center justify-center rounded-2xl",
                      isActive ? "bg-primary/10 text-primary" : "bg-muted/50 text-muted-foreground",
                    )}
                  >
                    <link.Icon className="size-4" />
                  </div>

                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-foreground">{link.label}</p>
                      {link.mode === mode ? (
                        <Badge variant="outline" className="border-black/8 bg-white text-[10px] text-muted-foreground">
                          Active
                        </Badge>
                      ) : null}
                    </div>
                    <p className="text-xs leading-5 text-muted-foreground">{link.description}</p>
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
          <Card className="gap-0 border border-black/5 bg-white/92 shadow-none">
            <CardContent className="space-y-3 p-4">
              {attachedDocuments.length === 0 ? (
                <p className="text-sm leading-6 text-muted-foreground">
                  No document is attached to this turn. Alex keeps the session memory, but only uses documents that were explicitly cited.
                </p>
              ) : (
                attachedDocuments.map((document) => (
                  <div
                    key={document.id}
                    className="flex items-start gap-3 rounded-2xl border border-black/5 bg-[#fafaf7] px-3 py-3"
                  >
                    <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-2xl bg-primary/8 text-primary">
                      <FileText className="size-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">{document.filename}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Attached to the current conversation
                      </p>
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

            <Card className="gap-0 border border-black/5 bg-white/92 shadow-none">
              <CardContent className="space-y-4 p-4">
                <p className="text-sm leading-6 text-muted-foreground">
                  Alex can cite a shared document with <code>@document-name</code>. To add, preview, delete, or broadcast a document to agents, use Brief & Documents.
                </p>

                {documents.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-black/8 bg-muted/30 px-3 py-4 text-sm text-muted-foreground">
                    No shared documents yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {documents.slice(0, 6).map((document) => (
                      <div
                        key={document.id}
                        className="flex items-start gap-3 rounded-2xl border border-black/5 bg-[#fafaf7] px-3 py-3"
                      >
                        <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-2xl bg-primary/8 text-primary">
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

                <Link href="/project-context">
                  <Button variant="outline" className="w-full rounded-full gap-2">
                    Open Brief & Documents
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
