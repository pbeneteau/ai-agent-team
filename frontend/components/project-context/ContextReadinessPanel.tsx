"use client";

import { Loader2, RefreshCw } from "lucide-react";

import type { GlobalKnowledgeReadiness } from "@/lib/api";
import { EmptyState } from "@/components/layout/EmptyState";
import { SectionPanel } from "@/components/layout/SectionPanel";
import { StatBlock } from "@/components/layout/StatBlock";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface ContextReadinessPanelProps {
  knowledgeReadiness: GlobalKnowledgeReadiness | null;
  knowledgeReadinessLoading: boolean;
  canExpandKnowledge: boolean;
  showFullKnowledge: boolean;
  topAgents: NonNullable<GlobalKnowledgeReadiness["agents"]>;
  topSharedGaps: NonNullable<GlobalKnowledgeReadiness["shared_gaps"]>;
  onToggleExpanded: () => void;
  onRefresh: () => void;
  onOpenAgent: (agentId: string) => void;
}

const readinessMeta: Record<
  NonNullable<GlobalKnowledgeReadiness["agents"][number]>["readiness_level"],
  { label: string; className: string }
> = {
  sufficient: { label: "Well briefed", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  partial: { label: "Partial", className: "bg-amber-50 text-amber-700 border-amber-200" },
  insufficient: { label: "Needs context", className: "bg-rose-50 text-rose-700 border-rose-200" },
};

export function ContextReadinessPanel({
  knowledgeReadiness,
  knowledgeReadinessLoading,
  canExpandKnowledge,
  showFullKnowledge,
  topAgents,
  topSharedGaps,
  onToggleExpanded,
  onRefresh,
  onOpenAgent,
}: ContextReadinessPanelProps) {
  return (
    <SectionPanel
      eyebrow="Diagnostic"
      title="Readiness"
      description="See which agents are under-briefed, what is missing, and where context would immediately improve reliability."
      actions={
        <>
          {canExpandKnowledge ? (
            <Button variant="outline" size="sm" className="rounded-full" onClick={onToggleExpanded}>
              {showFullKnowledge ? "Collapse" : "View full diagnostic"}
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            className="gap-2 rounded-full"
            onClick={onRefresh}
            disabled={knowledgeReadinessLoading}
          >
            {knowledgeReadinessLoading ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
            Refresh
          </Button>
        </>
      }
      contentClassName="space-y-5"
    >
      {knowledgeReadinessLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Agent context analysis in progress…
        </div>
      ) : !knowledgeReadiness ? (
        <EmptyState description="Unable to load the context diagnostic right now." />
      ) : (
        <>
          {knowledgeReadiness.has_fallback_results ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Part of this diagnostic comes from heuristic fallback, not the nominal structured channel.
            </div>
          ) : null}

          {knowledgeReadiness.generation_channel ? (
            <div className="flex flex-wrap gap-2">
              <Badge
                variant="outline"
                className={
                  knowledgeReadiness.generation_channel === "native_json_schema"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : knowledgeReadiness.generation_channel === "mixed"
                      ? "border-slate-200 bg-slate-100 text-slate-700"
                      : "border-amber-200 bg-amber-50 text-amber-800"
                }
              >
                {knowledgeReadiness.generation_channel === "native_json_schema"
                  ? "Native schema"
                  : knowledgeReadiness.generation_channel === "mixed"
                    ? "Mixed channel"
                    : "Heuristic fallback"}
              </Badge>
            </div>
          ) : null}

          <div className="grid gap-3 md:grid-cols-4">
            <StatBlock label="Tracked agents" value={knowledgeReadiness.total_agents} />
            <StatBlock label="Needs context" value={knowledgeReadiness.insufficient_agents} tone="danger" />
            <StatBlock label="Partial" value={knowledgeReadiness.partial_agents} tone="warning" />
            <StatBlock label="Well briefed" value={knowledgeReadiness.sufficient_agents} tone="positive" />
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Agents with the biggest gaps
              </p>
              {topAgents.length === 0 ? (
                <EmptyState description="No agent available for diagnostics." />
              ) : (
                topAgents.map((item) => (
                  <button
                    key={item.agent_id}
                    onClick={() => onOpenAgent(item.agent_id)}
                    className="w-full rounded-2xl border border-black/5 bg-white px-4 py-3 text-left transition-colors hover:border-primary/25 hover:bg-primary/5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900">{item.agent_name}</p>
                        <p className="mt-1 text-xs text-slate-500">{item.agent_title}</p>
                      </div>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <Badge variant="outline" className={readinessMeta[item.readiness_level].className}>
                          {readinessMeta[item.readiness_level].label}
                        </Badge>
                        <Badge variant="outline">{item.readiness_score}/100</Badge>
                      </div>
                    </div>
                    <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-slate-600">{item.summary}</p>
                    {item.missing_knowledge_summary.length > 0 ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {item.missing_knowledge_summary.slice(0, 3).map((gap) => (
                          <span
                            key={`${item.agent_id}-${gap}`}
                            className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700"
                          >
                            {gap}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </button>
                ))
              )}
            </div>

            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Shared gaps</p>
              {topSharedGaps.length === 0 ? (
                <EmptyState description="No notable shared gap right now." />
              ) : (
                topSharedGaps.map((gap) => (
                  <div key={gap.id} className="rounded-2xl border border-black/5 bg-white px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{gap.title}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {gap.can_be_found_on_web
                            ? "Can likely be covered with web research"
                            : "Probably requires an internal source"}
                        </p>
                      </div>
                      <Badge variant="outline">{gap.agent_count} agent{gap.agent_count > 1 ? "s" : ""}</Badge>
                    </div>
                    <p className="mt-3 line-clamp-2 text-xs text-slate-600">
                      {gap.affected_agent_names.join(", ")}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </SectionPanel>
  );
}
