"use client";

import type { ReactNode } from "react";
import { Clock3, Loader2, SlidersHorizontal, Sparkles, Target, UserMinus2, UserPlus2, Users } from "lucide-react";

import type { Team, TeamChangeRecommendation, TeamRecommendation } from "@/lib/api";
import { EmptyState } from "@/components/layout/EmptyState";
import { SectionPanel } from "@/components/layout/SectionPanel";
import { StatBlock } from "@/components/layout/StatBlock";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface ContextRecommendationsPanelProps {
  teams: Team[];
  newTeamRecommendations: TeamRecommendation[];
  teamChangeRecommendations: TeamChangeRecommendation[];
  recommendationsLoading: boolean;
  recommendationSource: "llm" | "heuristic_fallback";
  recommendationChannel: string | null;
  recommendationIssue: string | null;
  showAdvancedRecommendations: boolean;
  recommendationLoading: string | null;
  teamChangeLoading: string | null;
  onToggleExpanded: () => void;
  onCreateRecommendation: (recommendation: TeamRecommendation) => void;
  onApplyTeamChange: (change: TeamChangeRecommendation) => void;
}

const urgencyMeta: Record<TeamRecommendation["urgency"], { label: string; className: string }> = {
  now: { label: "Now", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  soon: { label: "Soon", className: "bg-amber-50 text-amber-700 border-amber-200" },
  later: { label: "Later", className: "bg-slate-100 text-slate-700 border-slate-200" },
};

const changeTypeMeta: Record<TeamChangeRecommendation["change_type"], { label: string; icon: ReactNode; className: string }> = {
  add_specialist: {
    label: "Add a specialist",
    icon: <UserPlus2 className="w-3.5 h-3.5" />,
    className: "bg-blue-50 text-blue-700 border-blue-200",
  },
  remove_agent: {
    label: "Remove an agent",
    icon: <UserMinus2 className="w-3.5 h-3.5" />,
    className: "bg-rose-50 text-rose-700 border-rose-200",
  },
  adjust_scope: {
    label: "Adjust scope",
    icon: <SlidersHorizontal className="w-3.5 h-3.5" />,
    className: "bg-slate-100 text-slate-700 border-slate-200",
  },
};

export function ContextRecommendationsPanel({
  teams,
  newTeamRecommendations,
  teamChangeRecommendations,
  recommendationsLoading,
  recommendationSource,
  recommendationChannel,
  recommendationIssue,
  showAdvancedRecommendations,
  recommendationLoading,
  teamChangeLoading,
  onToggleExpanded,
  onCreateRecommendation,
  onApplyTeamChange,
}: ContextRecommendationsPanelProps) {
  return (
    <SectionPanel
      eyebrow="Secondary"
      title="Recommendations"
      description="Suggested staffing and structural moves derived from the current context. These stay secondary to the canonical brief."
      actions={
        <Button variant="outline" size="sm" className="rounded-full" onClick={onToggleExpanded}>
          {showAdvancedRecommendations ? "Collapse" : "View recommendations"}
        </Button>
      }
      contentClassName="space-y-5"
    >
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatBlock label="New teams" value={newTeamRecommendations.length} />
        <StatBlock label="Adjustments" value={teamChangeRecommendations.length} tone="warning" />
        <StatBlock label="Current teams" value={teams.length} />
        <StatBlock
          label="Immediate priority"
          value={newTeamRecommendations.filter((rec) => rec.urgency === "now").length}
          tone="positive"
        />
      </div>

      {recommendationSource === "heuristic_fallback" ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Displayed recommendations use heuristic fallback.
          {recommendationIssue ? ` Reason: ${recommendationIssue}` : ""}
        </div>
      ) : null}

      {recommendationChannel ? (
        <div className="flex flex-wrap gap-2">
          <Badge
            variant="outline"
            className={
              recommendationChannel === "native_json_schema"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-amber-200 bg-amber-50 text-amber-800"
            }
          >
            {recommendationChannel === "native_json_schema" ? "Native schema" : "Heuristic fallback"}
          </Badge>
        </div>
      ) : null}

      {showAdvancedRecommendations ? (
        <>
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-violet-500" />
              <p className="text-sm font-semibold text-slate-700">Recommended teams for this context</p>
            </div>
            {recommendationsLoading ? (
              <EmptyState description="Generating AI recommendations…" />
            ) : newTeamRecommendations.length === 0 ? (
              <EmptyState description="No additional team is strongly recommended right now." />
            ) : (
              <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
                {newTeamRecommendations.map((rec) => {
                  const isLoading = recommendationLoading === rec.id;
                  const urgency = urgencyMeta[rec.urgency];
                  return (
                    <button
                      key={rec.id}
                      onClick={() => onCreateRecommendation(rec)}
                      disabled={isLoading}
                      className="flex flex-col items-start gap-3 rounded-2xl border border-black/5 bg-white p-4 text-left transition-all hover:border-primary/25 hover:shadow-sm disabled:opacity-60"
                    >
                      <div className="flex w-full items-start justify-between gap-3">
                        <div className="flex min-w-0 items-start gap-3">
                          <div className="rounded-2xl bg-violet-50 p-2 text-violet-600">
                            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Users className="w-4 h-4" />}
                          </div>
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-slate-900">{rec.name}</p>
                            <p className="mt-1 text-xs text-slate-500">{rec.description}</p>
                          </div>
                        </div>
                        <Badge variant="outline" className="shrink-0">
                          {rec.score}/100
                        </Badge>
                      </div>

                      <p className="text-sm leading-relaxed text-slate-600">{rec.reason}</p>

                      <div className="flex flex-wrap gap-2">
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${urgency.className}`}>
                          <Clock3 className="mr-1 inline h-3 w-3" />
                          {urgency.label}
                        </span>
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                          <Target className="mr-1 inline h-3 w-3" />
                          {rec.domain}
                        </span>
                        <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-700">
                          {rec.agents.length} agent{rec.agents.length > 1 ? "s" : ""}
                        </span>
                      </div>

                      <div className="w-full rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                        {rec.agents.map((agent) => (
                          <div key={`${rec.id}-${agent.name}-${agent.title}`} className="truncate">
                            {agent.is_lead ? "Lead" : "Specialist"}: {agent.name} - {agent.title}
                          </div>
                        ))}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-sky-500" />
              <p className="text-sm font-semibold text-slate-700">Recommended adjustments to existing teams</p>
            </div>
            {recommendationsLoading ? (
              <EmptyState description="Analyzing existing teams…" />
            ) : teamChangeRecommendations.length === 0 ? (
              <EmptyState description="No team change is considered necessary right now." />
            ) : (
              <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
                {teamChangeRecommendations.map((change) => {
                  const urgency = urgencyMeta[change.urgency];
                  const meta = changeTypeMeta[change.change_type];
                  const isApplying = teamChangeLoading === change.id;

                  return (
                    <div key={change.id} className="flex flex-col gap-3 rounded-2xl border border-black/5 bg-white p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-slate-900">{change.team_name}</p>
                          <p className="mt-1 text-xs text-slate-500">{change.reason}</p>
                        </div>
                        <Badge variant="outline" className="shrink-0">
                          {change.score}/100
                        </Badge>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${meta.className}`}
                        >
                          {meta.icon}
                          {meta.label}
                        </span>
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${urgency.className}`}>
                          <Clock3 className="mr-1 inline h-3 w-3" />
                          {urgency.label}
                        </span>
                      </div>

                      {change.suggested_agent ? (
                        <div className="rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                          <p className="font-medium text-slate-700">Recommended profile</p>
                          <p className="mt-1">
                            {change.suggested_agent.name} - {change.suggested_agent.title}
                          </p>
                          <p className="text-slate-500">
                            {change.suggested_agent.specialization.replace(/_/g, " ")}
                          </p>
                        </div>
                      ) : null}

                      {change.target_agent_name ? (
                        <div className="rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                          Affected agent: {change.target_agent_name}
                        </div>
                      ) : null}

                      {change.scope_update ? (
                        <div className="rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                          New focus: {change.scope_update}
                        </div>
                      ) : null}

                      <Button
                        size="sm"
                        className="self-start gap-2"
                        disabled={isApplying}
                        onClick={() => onApplyTeamChange(change)}
                      >
                        {isApplying ? (
                          <>
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            Applying…
                          </>
                        ) : (
                          "Apply"
                        )}
                      </Button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      ) : (
        <EmptyState description="Open this section only if you want to explore staffing or team-adjustment recommendations." />
      )}
    </SectionPanel>
  );
}
