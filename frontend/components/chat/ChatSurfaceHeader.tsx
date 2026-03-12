"use client";

import Link from "next/link";
import { BookOpenText, FileText, Plus, Wifi, WifiOff } from "lucide-react";

import { getWorkspaceLinks, type ChatPanelMode } from "@/components/chat/chat-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface ChatSurfaceHeaderProps {
  mode: ChatPanelMode;
  contextLabel: string;
  isConnected: boolean;
  showDocs: boolean;
  documentCount: number;
  attachedDocumentCount: number;
  onToggleDocs: () => void;
  onResetConversation: () => void;
}

export function ChatSurfaceHeader({
  mode,
  contextLabel,
  isConnected,
  showDocs,
  documentCount,
  attachedDocumentCount,
  onToggleDocs,
  onResetConversation,
}: ChatSurfaceHeaderProps) {
  const documentCountLabel =
    documentCount > 0 ? `${documentCount} doc${documentCount > 1 ? "s" : ""}` : null;
  const memoryScopeLabel =
    mode === "team-builder"
      ? "Local memory dedicated to team design"
      : "Local memory dedicated to orchestration";

  return (
    <div className="border-b border-[var(--ops-border)] bg-[color:rgba(255,254,249,0.76)] px-5 py-4 backdrop-blur md:px-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="border-[var(--ops-border)] bg-[var(--ops-surface-strong)] text-[11px] tracking-wide text-[var(--ops-muted-ink)]">
              {contextLabel}
            </Badge>
            <Badge
              variant="outline"
              className={
                isConnected
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }
            >
              {isConnected ? <Wifi className="size-3" /> : <WifiOff className="size-3" />}
              {isConnected ? "Connected" : "Reconnecting"}
            </Badge>
          </div>

          <div className="flex flex-wrap gap-2">
            {getWorkspaceLinks().map((link) => {
              const isActive = link.mode === mode;
              return (
                <Link key={link.href} href={link.href}>
                  <Button
                    variant={isActive ? "secondary" : "outline"}
                    size="sm"
                    className="rounded-full gap-2"
                  >
                    <link.Icon className="size-3.5" />
                    {link.label}
                  </Button>
                </Link>
              );
            })}
          </div>
        </div>

        <div className="flex flex-col gap-2 xl:items-end">
          <div className="flex flex-wrap items-center gap-2 xl:justify-end">
            <Link href="/project-context">
              <Button variant="outline" size="sm" className="rounded-full gap-2">
                <BookOpenText className="size-3.5" />
                Brief & Docs
              </Button>
            </Link>

            <Button
              variant={showDocs ? "secondary" : "outline"}
              size="sm"
              onClick={onToggleDocs}
              aria-expanded={showDocs}
              className="rounded-full gap-2"
            >
              <FileText className="size-3.5" />
              Sources
              {documentCountLabel ? (
                <span className="rounded-full bg-white px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                  {documentCountLabel}
                </span>
              ) : null}
            </Button>

            <Button variant="default" size="sm" onClick={onResetConversation} className="rounded-full gap-2 shadow-sm">
              <Plus className="size-3.5" />
              New session
            </Button>
          </div>

          <p className="text-xs leading-5 text-[var(--ops-muted-ink)] xl:text-right">
            {memoryScopeLabel}. {attachedDocumentCount > 0 ? `${attachedDocumentCount} source(s) attached right now.` : "No sources attached for this turn."}
          </p>
        </div>
      </div>
    </div>
  );
}
