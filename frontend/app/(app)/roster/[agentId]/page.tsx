"use client";

/**
 * Agent detail page with tabs.
 * Ref: TDD-05 Section 14.2
 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgentDetail } from "@/lib/hooks/use-roster";
import { AgentDetailTabs } from "@/features/roster/agent-detail-tabs";

export default function AgentDetailPage() {
  const params = useParams<{ agentId: string }>();
  const { data: agent, isLoading } = useAgentDetail(params.agentId);

  if (isLoading || !agent) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Link
          href="/roster"
          className="inline-flex items-center gap-1 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
        >
          <ArrowLeft className="h-3 w-3" /> Roster
        </Link>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">{agent.name}</h1>
          <Badge variant="outline">{agent.specialization}</Badge>
        </div>
      </div>
      <AgentDetailTabs agent={agent} />
    </div>
  );
}
