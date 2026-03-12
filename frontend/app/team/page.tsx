"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ExternalLink, Loader2, MessageSquare, RefreshCw, Trash2, Users } from "lucide-react";

import { AgentCard } from "@/components/agents/AgentCard";
import { WorkspaceInspectorDrawer } from "@/components/layout/WorkspaceInspectorDrawer";
import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { OrgChart } from "@/components/organigramme/OrgChart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { api, type Agent, type Team } from "@/lib/api";
import { useWsEvent } from "@/lib/ws-context";

export default function TeamPage() {
  const router = useRouter();
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"list" | "chart">("list");
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [orgRefreshKey, setOrgRefreshKey] = useState(0);

  const load = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const nextTeams = await api.getTeams();
      setTeams(nextTeams);
      setLastUpdatedAt(new Date().toISOString());
      setError(null);
    } catch (err) {
      console.error("[TeamPage] Failed to load teams:", err);
      setError("Unable to load teams.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selectedAgent?.id) {
      return;
    }

    const refreshedAgent = teams
      .flatMap((team) => team.agents)
      .find((agent) => agent.id === selectedAgent.id);

    if (refreshedAgent) {
      setSelectedAgent((prev) => {
        if (!prev || prev.id !== refreshedAgent.id) {
          return refreshedAgent;
        }
        return { ...prev, ...refreshedAgent };
      });
    }
  }, [selectedAgent?.id, teams]);

  useWsEvent(
    (msg) => {
      if (msg.type === "agent_status" || msg.type === "team_created") {
        load(true);
        setOrgRefreshKey((current) => current + 1);
      }
    },
    [load],
  );

  async function handleReset() {
    if (!confirm("Reset all teams? This action cannot be undone.")) {
      return;
    }
    try {
      await api.resetAll();
      setSelectedAgent(null);
      load();
    } catch {
      setError("Error while resetting teams.");
    }
  }

  async function handleDeleteTeam(team: Team) {
    if (!confirm(`Delete team "${team.name}" and all of its agents?`)) {
      return;
    }
    try {
      await api.deleteTeam(team.id);
      setSelectedAgent((current) => {
        if (!current) {
          return null;
        }
        const isMember = team.agents.some((agent) => agent.id === current.id);
        return isMember ? null : current;
      });
      load();
    } catch {
      setError("Error while deleting the team.");
    }
  }

  async function handleSelectAgent(agent: Agent) {
    setSelectedAgent(agent);
    try {
      const fullAgent = await api.getAgent(agent.id);
      setSelectedAgent(fullAgent);
    } catch {
      // Keep the lightweight card data if the detailed fetch fails.
    }
  }

  function handleOpenAgentPage(agent: Agent) {
    router.push(`/team/agents/${agent.id}`);
  }

  const allAgents = teams.flatMap((team) => team.agents).filter((agent) => agent.role !== "associate");
  const readyAgents = allAgents.filter((agent) => agent.status === "ready" && agent.occupancy_status === "idle");
  const busyAgents = allAgents.filter((agent) => agent.occupancy_status === "busy");

  return (
    <>
      <WorkspacePageShell
        title="Teams & Agents"
        description="Review team structure, inspect agent workspaces, and spot readiness gaps before execution."
        meta={
          lastUpdatedAt ? (
            <>
              <span>Last updated {new Date(lastUpdatedAt).toLocaleTimeString("en-US")}</span>
              <span>{teams.length} active team(s)</span>
            </>
          ) : undefined
        }
        actions={
          <>
            <Link href="/project-context">
              <Button variant="outline" className="gap-2 rounded-full">
                <Users className="size-4" />
                Brief & Documents
              </Button>
            </Link>
            <Link href="/team-builder">
              <Button variant="outline" className="rounded-full">Design with Alex</Button>
            </Link>
            <Button variant="outline" className="gap-2 rounded-full" onClick={() => load(true)}>
              {refreshing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
              Refresh
            </Button>
          </>
        }
      >
        {error ? (
          <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <AlertTriangle className="size-4 shrink-0" />
            {error}
          </div>
        ) : null}

        <div className="grid gap-3 md:grid-cols-3">
          <Card className="border-black/5 bg-white/92 shadow-none">
            <CardContent className="p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Active teams</p>
              <p className="mt-3 text-2xl font-semibold text-slate-900">{loading ? "—" : teams.length}</p>
            </CardContent>
          </Card>
          <Card className="border-black/5 bg-white/92 shadow-none">
            <CardContent className="p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Available agents</p>
              <p className="mt-3 text-2xl font-semibold text-slate-900">{loading ? "—" : readyAgents.length}</p>
            </CardContent>
          </Card>
          <Card className="border-black/5 bg-white/92 shadow-none">
            <CardContent className="p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Busy agents</p>
              <p className="mt-3 text-2xl font-semibold text-slate-900">{loading ? "—" : busyAgents.length}</p>
            </CardContent>
          </Card>
        </div>

        <div className="flex gap-1 border-b border-black/6">
          {(["list", "chart"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab
                  ? "border-primary text-primary"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {tab === "list" ? "Operational view" : "Org chart"}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="size-6 animate-spin text-slate-400" />
          </div>
        ) : activeTab === "chart" ? (
          <div className="h-[520px] overflow-hidden rounded-2xl border border-black/5 bg-white xl:h-[600px]">
            <OrgChart
              refreshKey={orgRefreshKey}
              onAgentClick={(agentId) => {
                const found = teams.flatMap((team) => team.agents).find((agent) => agent.id === agentId);
                if (found) {
                  handleOpenAgentPage(found);
                  return;
                }
                router.push(`/team/agents/${agentId}`);
              }}
            />
          </div>
        ) : teams.length === 0 ? (
          <div className="rounded-2xl border border-black/5 bg-white px-6 py-16 text-center text-slate-500">
            <p className="text-lg font-medium text-slate-900">No team created</p>
            <p className="mt-2 text-sm text-slate-400">
              Launch Alex to compose the first team, then feed it from the brief and shared documents.
            </p>
            <div className="mt-6 flex justify-center gap-2">
              <Link href="/chat">
                <Button className="gap-2">
                  <MessageSquare className="size-4" />
                  Open Alex
                </Button>
              </Link>
              <Link href="/project-context">
                <Button variant="outline">Open Brief & Documents</Button>
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {teams.map((team) => {
              const leadAgents = team.agents.filter(
                (agent) => agent.id === team.lead_agent_id || agent.role === "team_lead",
              );
              const specialistAgents = team.agents.filter(
                (agent) => !leadAgents.some((lead) => lead.id === agent.id),
              );

              return (
                <Card key={team.id} className="overflow-hidden border-black/5 bg-white shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
                  <CardHeader className="border-b border-black/5 bg-slate-50/70 pb-4">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold text-slate-900">{team.name}</h3>
                        <Badge variant="outline" className="capitalize">
                          {team.domain}
                        </Badge>
                        <Badge variant="secondary">
                          {team.agents.length} member{team.agents.length > 1 ? "s" : ""}
                        </Badge>
                      </div>
                      <p className="max-w-3xl text-sm text-slate-500">{team.description}</p>
                    </div>
                  </CardHeader>

                  <CardContent className="pt-5">
                    <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Team lead</p>
                          <Badge variant="outline">{leadAgents.length}</Badge>
                        </div>

                        {leadAgents.length === 0 ? (
                          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-400">
                            No lead defined
                          </div>
                        ) : (
                          leadAgents.map((agent) => (
                            <div key={agent.id} className="space-y-2">
                              <AgentCard agent={agent} onOpen={handleOpenAgentPage} />
                              <Button variant="outline" size="sm" className="w-full rounded-full gap-2" onClick={() => handleSelectAgent(agent)}>
                                <ExternalLink className="size-3.5" />
                                Quick preview
                              </Button>
                            </div>
                          ))
                        )}
                      </div>

                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Specialists</p>
                          <Badge variant="outline">{specialistAgents.length}</Badge>
                        </div>

                        {specialistAgents.length === 0 ? (
                          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-400">
                            No specialist in this team
                          </div>
                        ) : (
                          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                            {specialistAgents.map((agent) => (
                              <div key={agent.id} className="space-y-2">
                                <AgentCard agent={agent} onOpen={handleOpenAgentPage} />
                                <Button variant="outline" size="sm" className="w-full rounded-full gap-2" onClick={() => handleSelectAgent(agent)}>
                                  <ExternalLink className="size-3.5" />
                                  Quick preview
                                </Button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="mt-5 flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-slate-400 hover:text-red-600"
                        onClick={() => handleDeleteTeam(team)}
                      >
                        Delete team
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}

            {teams.length > 0 ? (
              <Card className="border-black/5 bg-white/92 shadow-none">
                <CardContent className="flex flex-col gap-3 p-5 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Advanced zone</p>
                    <p className="mt-1 text-sm text-slate-500">
                      Destructive actions stay secondary and require confirmation.
                    </p>
                  </div>
                  <Button variant="outline" className="gap-2 rounded-full text-red-600 hover:text-red-700" onClick={handleReset}>
                    <Trash2 className="size-4" />
                    Reset all teams
                  </Button>
                </CardContent>
              </Card>
            ) : null}
          </div>
        )}
      </WorkspacePageShell>

      {selectedAgent ? (
        <WorkspaceInspectorDrawer
          agent={selectedAgent}
          onClose={() => setSelectedAgent(null)}
          showSpecialization
          showOccupancy
          showBackstory
        />
      ) : null}
    </>
  );
}
