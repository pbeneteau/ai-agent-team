"use client";

import { useEffect, useState, useCallback } from "react";
import { api, Task, Team } from "@/lib/api";
import { useWsEvent } from "@/lib/ws-context";
import { TaskCard } from "@/components/tasks/TaskCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { AlertTriangle, Loader2, Plus, RefreshCw, X } from "lucide-react";

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    priority: "medium" as "low" | "medium" | "high",
    assigned_team_id: "",
  });
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [t, te] = await Promise.all([api.getTasks(), api.getTeams()]);
      setTasks(t.slice().reverse());
      setTeams(te);
      setError(null);
    } catch (err) {
      setError("Impossible de charger les tâches.");
      console.error("[TasksPage] Failed to load tasks:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // WS events drive live updates — no polling needed
  useWsEvent((msg) => {
    if (msg.type === "task_update" || msg.type === "task_created") {
      load();
    }
  }, [load]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim() || !form.description.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createTask({
        title: form.title,
        description: form.description,
        priority: form.priority,
        assigned_team_id: form.assigned_team_id || undefined,
      });
      setForm({ title: "", description: "", priority: "medium", assigned_team_id: "" });
      setShowForm(false);
      load();
    } catch {
      setError("Erreur lors de la création de la tâche. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Tâches</h1>
          <p className="text-slate-500 mt-1">Suivez et gérez les tâches de votre équipe</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} className="gap-2">
            <RefreshCw className="w-3.5 h-3.5" />
            Actualiser
          </Button>
          <Button
            size="sm"
            className="gap-2 bg-indigo-600 hover:bg-indigo-700"
            onClick={() => setShowForm(!showForm)}
          >
            {showForm ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
            {showForm ? "Annuler" : "Nouvelle tâche"}
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Create task form */}
      {showForm && (
        <Card>
          <CardHeader className="pb-3">
            <h3 className="font-semibold">Créer une tâche</h3>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                placeholder="Titre de la tâche"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                required
              />
              <Textarea
                placeholder="Description détaillée…"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                className="min-h-[80px]"
                required
              />
              <div className="flex gap-3">
                <select
                  value={form.priority}
                  onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value as "low" | "medium" | "high" }))}
                  className="flex-1 border rounded-md px-3 py-2 text-sm"
                >
                  <option value="low">Priorité faible</option>
                  <option value="medium">Priorité moyenne</option>
                  <option value="high">Priorité haute</option>
                </select>
                <select
                  value={form.assigned_team_id}
                  onChange={(e) => setForm((f) => ({ ...f, assigned_team_id: e.target.value }))}
                  className="flex-1 border rounded-md px-3 py-2 text-sm"
                >
                  <option value="">Toutes les équipes</option>
                  {teams.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>
              <Button
                type="submit"
                disabled={submitting}
                className="bg-indigo-600 hover:bg-indigo-700 gap-2"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Créer et lancer
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Tasks list */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-20 text-slate-500">
          <p className="text-lg mb-2">Aucune tâche pour l&apos;instant.</p>
          <p className="text-sm">Parlez à Alex ou créez une tâche manuellement.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} onRetry={load} />
          ))}
        </div>
      )}
    </div>
  );
}
