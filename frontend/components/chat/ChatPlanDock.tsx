"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { SectionPanel } from "@/components/layout/SectionPanel";

interface ChatPlanDockProps {
  eyebrow: string;
  title: string;
  description: string;
  phaseLabel: string;
  backendState: string | null;
  attachedDocumentCount: number;
  children: ReactNode;
}

export function ChatPlanDock({
  eyebrow,
  title,
  description,
  phaseLabel,
  backendState,
  attachedDocumentCount,
  children,
}: ChatPlanDockProps) {
  return (
    <SectionPanel
      eyebrow={eyebrow}
      title={title}
      description={description}
      tone="subtle"
      actions={
        <>
          <Badge variant="outline">{phaseLabel}</Badge>
          {backendState ? <Badge variant="outline">{backendState}</Badge> : null}
          {attachedDocumentCount > 0 ? (
            <Badge variant="outline">{attachedDocumentCount} source{attachedDocumentCount > 1 ? "s" : ""}</Badge>
          ) : null}
        </>
      }
      className="h-full rounded-none border-0 bg-transparent shadow-none"
      contentClassName="px-0 py-0"
    >
      {children}
    </SectionPanel>
  );
}
