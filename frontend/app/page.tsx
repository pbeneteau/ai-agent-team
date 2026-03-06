"use client";

import { useEffect, useState, useCallback } from "react";
import { api, Team, Task, Agent } from "@/lib/api";
import { useWsEvent } from "@/lib/ws-context";
import { AgentCard } from "@/components/agents/AgentCard";
import { TaskCard } from "@/components/tasks/TaskCard";
import { Card, CardContent } from "@/components/ui/card";
import {
  Users,
  CheckCircle,
  Bot,
  ArrowRight,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function DashboardPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [t, tk, a] = await Promise.all([
        api.getTeams(),
        api.getTasks(),
        api.getAgents(),
      ]);
      setTeams(t);
      setTasks(tk);
      setAgents(a);
      setError(null);
    } catch (err) {
      setError("Impossible de charger les données. Le backend est-il démarré ?");
      console.error("[Dashboard] Failed to load data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Refresh on relevant WS broadcast events instead of polling
  useWsEvent((msg) => {
    if (
      msg.type === "agent_status" ||
      msg.type === "task_update" ||
      msg.type === "task_created" ||
      msg.type === "team_created"
    ) {
      load();
    }
  }, [load]);

  const readyAgents = agents.filter((a) => a.status === "ready").length;
  const completedTasks = tasks.filter((t) => t.status === "completed").length;
  const runningTasks = tasks.filter((t) => t.status === "running").length;

  const recentTasks = tasks.slice(-4).reverse();
  const allAgents = agents.filter((a) => a.role !== "associate").slice(0, 6);

  return (
    <div className="h-full overflow-y-auto p-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-500 mt-1">Vue d&apos;ensemble de votre équipe IA</p>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          {
            label: "Équipes",
            value: teams.length,
            icon: <Users className="w-5 h-5 text-indigo-500" />,
            bg: "bg-indigo-50",
          },
          {
            label: "Agents actifs",
            value: readyAgents,
            icon: <Bot className="w-5 h-5 text-violet-500" />,
            bg: "bg-violet-50",
          },
          {
            label: "Tâches terminées",
            value: completedTasks,
            icon: <CheckCircle className="w-5 h-5 text-green-500" />,
            bg: "bg-green-50",
          },
          {
            label: "En cours",
            value: runningTasks,
            icon: <Loader2 className={`w-5 h-5 text-blue-500 ${runningTasks > 0 ? "animate-spin" : ""}`} />,
            bg: "bg-blue-50",
          },
        ].map(({ label, value, icon, bg }) => (
          <Card key={label}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">{label}</p>
                  <p className="text-3xl font-bold text-slate-900 mt-1">{value}</p>
                </div>
                <div className={`w-12 h-12 ${bg} rounded-xl flex items-center justify-center`}>
                  {icon}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {teams.length === 0 && !loading ? (
        /* Empty state */
        <Card className="border-dashed border-2 border-slate-200">
          <CardContent className="p-12 text-center">
            <div className="text-7xl mb-4">🚀</div>
            <h2 className="text-xl font-bold text-slate-800 mb-2">
              Démarrez votre aventure
            </h2>
            <p className="text-slate-500 mb-6 max-w-md mx-auto">
              Vous n&apos;avez pas encore d&apos;équipe. Parlez à Alex pour créer votre première équipe d&apos;agents IA.
            </p>
            <div className="flex gap-3 justify-center">
              <Link href="/team-builder">
                <Button className="bg-indigo-600 hover:bg-indigo-700 gap-2">
                  <Users className="w-4 h-4" />
                  Créer une équipe
                </Button>
              </Link>
              <Link href="/chat">
                <Button variant="outline" className="gap-2">
                  <Bot className="w-4 h-4" />
                  Parler à Alex
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-8">
          {/* Agents */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-slate-800">Vos agents</h2>
              <Link href="/team" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
                Voir tout <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {allAgents.map((a) => (
                  <AgentCard key={a.id} agent={a} />
                ))}
              </div>
            )}
          </div>

          {/* Tasks */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-slate-800">Tâches récentes</h2>
              <Link href="/tasks" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
                Voir tout <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
              </div>
            ) : recentTasks.length === 0 ? (
              <Card>
                <CardContent className="p-8 text-center text-slate-500 text-sm">
                  Aucune tâche. Parlez à Alex pour en créer une.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {recentTasks.map((t) => (
                  <TaskCard key={t.id} task={t} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
