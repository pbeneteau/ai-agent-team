"use client";

import { useEffect, useState, useCallback } from "react";
import { api, Team, Agent } from "@/lib/api";
import { useWsEvent } from "@/lib/ws-context";
import { AgentCard } from "@/components/agents/AgentCard";
import { OrgChart } from "@/components/organigramme/OrgChart";
import { WorkspacePanel } from "@/components/agents/WorkspacePanel";
import { ProjectContextPanel } from "@/components/team/ProjectContextPanel";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Loader2, RefreshCw, Trash2, X, MessageSquare, Zap, Code, Megaphone, BarChart2, Package } from "lucide-react";
import Link from "next/link";

const TEMPLATES = [
  { key: "dev", label: "Dev Team", desc: "PM + Frontend + Backend", icon: <Code className="w-4 h-4" />, color: "text-blue-600 bg-blue-50 border-blue-200" },
  { key: "marketing", label: "Marketing", desc: "Lead + Content + Social", icon: <Megaphone className="w-4 h-4" />, color: "text-pink-600 bg-pink-50 border-pink-200" },
  { key: "business", label: "Business", desc: "Finance & stratégie", icon: <BarChart2 className="w-4 h-4" />, color: "text-green-600 bg-green-50 border-green-200" },
  { key: "product", label: "Product", desc: "Designer & UX", icon: <Package className="w-4 h-4" />, color: "text-violet-600 bg-violet-50 border-violet-200" },
] as const;

export default function TeamPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"list" | "chart">("chart");
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [orgRefreshKey, setOrgRefreshKey] = useState(0);
  const [templateLoading, setTemplateLoading] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const t = await api.getTeams();
      setTeams(t);
      setError(null);
    } catch (err) {
      setError("Impossible de charger les équipes.");
      console.error("[TeamPage] Failed to load teams:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Refresh on WS events (agent learning, team creation)
  useWsEvent((msg) => {
    if (msg.type === "agent_status" || msg.type === "team_created") {
      load();
      setOrgRefreshKey((k) => k + 1);
    }
  }, [load]);

  async function handleReset() {
    if (!confirm("Réinitialiser toutes les équipes ? Cette action est irréversible.")) return;
    try {
      await api.resetAll();
      load();
    } catch {
      setError("Erreur lors de la réinitialisation.");
    }
  }

  async function handleCreateFromTemplate(template: string) {
    setTemplateLoading(template);
    try {
      await api.createTeamFromTemplate(template);
      load();
    } catch {
      setError("Erreur lors de la création de l'équipe.");
    } finally {
      setTemplateLoading(null);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Mon Équipe</h1>
          <p className="text-slate-500 mt-1">Gérez vos équipes et vos agents</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} className="gap-2">
            <RefreshCw className="w-3.5 h-3.5" />
            Actualiser
          </Button>
          {teams.length > 0 && (
            <Button variant="outline" size="sm" onClick={handleReset} className="gap-2 text-red-600 hover:text-red-700">
              <Trash2 className="w-3.5 h-3.5" />
              Réinitialiser
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Project context */}
      <ProjectContextPanel />

      {/* Quick-add templates */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Zap className="w-4 h-4 text-amber-500" />
          <p className="text-sm font-semibold text-slate-700">Créer une équipe en un clic</p>
        </div>
        <div className="grid grid-cols-4 gap-3">
          {TEMPLATES.map((t) => (
            <button
              key={t.key}
              onClick={() => handleCreateFromTemplate(t.key)}
              disabled={templateLoading === t.key}
              className={`flex items-center gap-2 p-3 rounded-lg border text-left transition-all hover:shadow-sm disabled:opacity-60 ${t.color}`}
            >
              {templateLoading === t.key ? (
                <Loader2 className="w-4 h-4 animate-spin shrink-0" />
              ) : (
                t.icon
              )}
              <div className="min-w-0">
                <p className="text-sm font-semibold truncate">{t.label}</p>
                <p className="text-xs opacity-70 truncate">{t.desc}</p>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b">
        {(["chart", "list"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {tab === "chart" ? "Organigramme" : "Liste des équipes"}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      ) : activeTab === "chart" ? (
        <div className="h-[600px] rounded-xl border bg-white overflow-hidden">
          <OrgChart
            refreshKey={orgRefreshKey}
            onAgentClick={(agentId, agentName) => {
              const found = teams.flatMap((t) => t.agents).find((a) => a.id === agentId);
              setSelectedAgent(found ?? ({ id: agentId, name: agentName } as Agent));
            }}
          />
        </div>
      ) : teams.length === 0 ? (
        <div className="text-center py-20 text-slate-500">
          <p className="text-lg mb-2">Aucune équipe créée.</p>
          <p className="text-sm text-slate-400 mb-6">
            Discutez avec Alex dans le chat pour créer votre équipe d&apos;agents.
          </p>
          <Link href="/chat">
            <Button className="bg-indigo-600 hover:bg-indigo-700 gap-2">
              <MessageSquare className="w-4 h-4" />
              Parler à Alex
            </Button>
          </Link>
        </div>
      ) : (
        <div className="space-y-6">
          {teams.map((team) => (
            <Card key={team.id}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-slate-900">{team.name}</h3>
                    <p className="text-sm text-slate-500">{team.description}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="capitalize">
                      {team.domain}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-slate-400 hover:text-red-600 h-7 w-7 p-0"
                      title="Supprimer cette équipe"
                      onClick={async () => {
                        if (!confirm(`Supprimer l'équipe "${team.name}" et tous ses agents ?`)) return;
                        try {
                          await api.deleteTeam(team.id);
                          load();
                        } catch {
                          setError("Erreur lors de la suppression.");
                        }
                      }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-3">
                  {team.agents.map((agent) => (
                    <div
                      key={agent.id}
                      onClick={() => setSelectedAgent(agent)}
                      className="cursor-pointer"
                    >
                      <AgentCard agent={agent} />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Workspace side panel */}
      {selectedAgent && (
        <div className="fixed inset-y-0 right-0 w-[480px] bg-white border-l shadow-2xl z-50 flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <p className="font-semibold text-slate-800 text-sm">
              Workspace de {selectedAgent.name}
            </p>
            <Button variant="ghost" size="sm" onClick={() => setSelectedAgent(null)}>
              <X className="w-4 h-4" />
            </Button>
          </div>
          <WorkspacePanel
            agentId={selectedAgent.id}
            agentName={selectedAgent.name}
          />
        </div>
      )}
    </div>
  );
}
