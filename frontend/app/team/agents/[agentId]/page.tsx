"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Loader2, MessageSquare, RefreshCw } from "lucide-react";

import { AgentStatusBadge } from "@/components/agents/AgentStatusBadge";
import { WorkspacePanel } from "@/components/agents/WorkspacePanel";
import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, type Agent, type Team } from "@/lib/api";

const ROLE_LABELS: Record<Agent["role"], string> = {
  associate: "AI associate",
  team_lead: "Team lead",
  specialist: "Specialist",
};

export default function AgentWorkspacePage() {
  const params = useParams<{ agentId: string }>();
  const agentId = typeof params?.agentId === "string" ? params.agentId : "";
  const [agent, setAgent] = useState<Agent | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!agentId) {
      setError("Unable to identify this agent.");
      setLoading(false);
      return;
    }
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const [nextAgent, nextTeams] = await Promise.all([api.getAgent(agentId), api.getTeams()]);
      setAgent(nextAgent);
      setTeams(nextTeams);
      setError(null);
    } catch (loadError) {
      console.error("[AgentWorkspacePage] Failed to load agent:", loadError);
      setError("Unable to load this agent.");
      setAgent(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [agentId]);

  useEffect(() => {
    load();
  }, [load]);

  const teamName = useMemo(
    () => teams.find((team) => team.agents.some((item) => item.id === agent?.id))?.name ?? "Unassigned",
    [agent?.id, teams],
  );

  return (
    <WorkspacePageShell
      eyebrow={agent ? <Badge variant="outline">{ROLE_LABELS[agent.role]}</Badge> : undefined}
      title={agent?.name ?? "Agent"}
      description={agent?.title ?? "Full inspection of this agent's workspace, knowledge, and files."}
      meta={
        agent ? (
          <>
            <span>Team {teamName}</span>
            <span>Specialization {agent.specialization.replace(/_/g, " ")}</span>
          </>
        ) : undefined
      }
      actions={
        <>
          <Link href="/team">
            <Button variant="outline" className="rounded-full gap-2">
              <ArrowLeft className="size-4" />
              Back to Teams & Agents
            </Button>
          </Link>
          <Link href="/chat">
            <Button variant="outline" className="rounded-full gap-2">
              <MessageSquare className="size-4" />
              Open Alex
            </Button>
          </Link>
          <Button variant="outline" className="rounded-full gap-2" onClick={() => load(true)}>
            {refreshing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            Refresh
          </Button>
        </>
      }
    >
      {error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="size-6 animate-spin text-slate-400" />
        </div>
      ) : agent ? (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Card className="border-black/5 bg-white/92 shadow-none">
              <CardContent className="p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Team</p>
                <p className="mt-3 text-sm font-semibold text-slate-900">{teamName}</p>
              </CardContent>
            </Card>
            <Card className="border-black/5 bg-white/92 shadow-none">
              <CardContent className="p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Status</p>
                <div className="mt-3">
                  <AgentStatusBadge status={agent.status} occupancyStatus={agent.occupancy_status} />
                </div>
              </CardContent>
            </Card>
            <Card className="border-black/5 bg-white/92 shadow-none">
              <CardContent className="p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Model</p>
                <p className="mt-3 text-sm font-semibold text-slate-900">
                  Claude {agent.model_tier === "opus" ? "Opus" : "Sonnet"}
                </p>
              </CardContent>
            </Card>
            <Card className="border-black/5 bg-white/92 shadow-none">
              <CardContent className="p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Tools</p>
                <p className="mt-3 text-sm font-semibold text-slate-900">{agent.tools.length}</p>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <Card className="border-black/5 bg-white/92 shadow-none">
              <CardContent className="p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Mission</p>
                <p className="mt-3 text-sm leading-6 text-slate-700">{agent.goal || "No mission recorded."}</p>
              </CardContent>
            </Card>
            <Card className="border-black/5 bg-white/92 shadow-none">
              <CardContent className="p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Operator context</p>
                {agent.occupancy_status !== "idle" ? (
                  <div className="mt-3 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3">
                    <p className="text-sm font-semibold text-blue-900">{agent.current_task_title ?? "Current task"}</p>
                    {agent.current_node_title ? (
                      <p className="mt-1 text-xs text-blue-700">Step: {agent.current_node_title}</p>
                    ) : null}
                  </div>
                ) : (
                  <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                    Agent available for a new execution.
                  </div>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  {agent.tools.slice(0, 6).map((tool) => (
                    <Badge key={tool} variant="outline">
                      {tool.replace(/_/g, " ")}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          <Card className="overflow-hidden border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
            <CardContent className="p-0">
              <WorkspacePanel agentId={agent.id} agentName={agent.name} />
            </CardContent>
          </Card>
        </div>
      ) : (
        <Card className="border-black/5 bg-white/92 shadow-none">
          <CardContent className="p-8 text-center text-sm text-slate-500">
            This agent is no longer available.
          </CardContent>
        </Card>
      )}
    </WorkspacePageShell>
  );
}
