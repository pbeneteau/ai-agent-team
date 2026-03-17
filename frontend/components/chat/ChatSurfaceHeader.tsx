"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { BookOpenText, FileText, Plus, Wifi, WifiOff } from "lucide-react";

import { getWorkspaceLinks, type ChatPanelMode } from "@/components/chat/chat-shell";
import { isProductNavItemActive } from "@/lib/config/product-navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface ChatSurfaceHeaderProps {
  mode: ChatPanelMode;
  workflowLabel: string;
  statusLabel: string;
  isConnected: boolean;
  showDocs: boolean;
  documentCount: number;
  attachedDocumentCount: number;
  onToggleDocs: () => void;
  onResetConversation: () => void;
}

export function ChatSurfaceHeader({
  mode,
  workflowLabel,
  statusLabel,
  isConnected,
  showDocs,
  documentCount,
  attachedDocumentCount,
  onToggleDocs,
  onResetConversation,
}: ChatSurfaceHeaderProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const documentCountLabel =
    documentCount > 0 ? `${documentCount} doc${documentCount > 1 ? "s" : ""}` : null;
  const workflowDescription =
    mode === "design-team"
      ? "Shape and validate the team directly inside Alex."
      : workflowLabel === "Ask Alex"
        ? "Use Alex for direct operator guidance."
        : "Use Alex to scope and review execution before launch.";

  return (
    <div className="border-b border-[var(--ops-border)] bg-[var(--ops-surface-strong)] px-4 py-3 md:px-5">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="tracking-wide text-[11px]">
              {workflowLabel}
            </Badge>
            <Badge variant="secondary" className="text-[11px]">
              {statusLabel}
            </Badge>
            <Badge
              variant={isConnected ? "positive" : "warning"}
            >
              {isConnected ? <Wifi className="size-3" /> : <WifiOff className="size-3" />}
              {isConnected ? "Connected" : "Reconnecting"}
            </Badge>
            {attachedDocumentCount > 0 ? (
              <Badge variant="outline" className="text-[11px]">
                {attachedDocumentCount} attached
              </Badge>
            ) : null}
          </div>

          <p className="text-sm leading-6 text-[var(--ops-muted-ink)]">{workflowDescription}</p>

          <div className="flex flex-wrap gap-1.5">
            {getWorkspaceLinks().map((link) => {
              const isActive = isProductNavItemActive(link, pathname, searchParams);
              return (
                <Link key={link.id} href={link.href}>
                  <Button variant={isActive ? "secondary" : "ghost"} size="sm" className="gap-2">
                    <link.Icon className="size-3.5" />
                    {link.label}
                  </Button>
                </Link>
              );
            })}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 xl:justify-end">
          <Link href="/project-context?section=documents">
            <Button variant="outline" size="sm" className="gap-2">
              <BookOpenText className="size-3.5" />
              Context
            </Button>
          </Link>

          <Button
            variant={showDocs ? "secondary" : "outline"}
            size="sm"
            onClick={onToggleDocs}
            aria-expanded={showDocs}
            className="gap-2"
          >
            <FileText className="size-3.5" />
            Sources
            {documentCountLabel ? (
              <span className="rounded-full bg-[var(--ops-surface-elevated)] px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                {documentCountLabel}
              </span>
            ) : null}
          </Button>

          <Button variant="default" size="sm" onClick={onResetConversation} className="gap-2">
            <Plus className="size-3.5" />
            New session
          </Button>
        </div>
      </div>
    </div>
  );
}
