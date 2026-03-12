"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api, Task, TaskExecutionMode, Team } from "@/lib/api";
import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
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
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    priority: "medium" as "low" | "medium" | "high",
    assigned_team_id: "",
    execution_mode: "auto" as TaskExecutionMode,
  });
  const [submitting, setSubmitting] = useState(false);

  const upsertTask = useCallback((incoming: Task) => {
    setTasks((prev) => {
      const next = [incoming, ...prev.filter((task) => task.id !== incoming.id)];
      return next.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    });
  }, []);

  const removeTask = useCallback((taskId: string) => {
    setTasks((prev) => prev.filter((task) => task.id !== taskId));
  }, []);

  const load = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    }
    try {
      const [t, te] = await Promise.all([api.getTasks(), api.getTeams()]);
      setTasks(t.slice().reverse());
      setTeams(te);
      setLastUpdatedAt(new Date().toISOString());
      setError(null);
    } catch (err) {
      setError("Unable to load tasks.");
      console.error("[TasksPage] Failed to load tasks:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // WS events drive live updates — no polling needed
  useWsEvent((msg) => {
    if (msg.type === "task_deleted") {
      const data = (msg.data ?? {}) as { id?: unknown };
      if (typeof data.id === "string") {
        removeTask(data.id);
        setLastUpdatedAt(new Date().toISOString());
      }
      return;
    }
    if (msg.type === "task_update" || msg.type === "task_created") {
      upsertTask(msg.data as Task);
      setLastUpdatedAt(new Date().toISOString());
    }
  }, [removeTask, upsertTask]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim() || !form.description.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const createdTask = await api.createTask({
        title: form.title,
        description: form.description,
        priority: form.priority,
        assigned_team_id: form.assigned_team_id || undefined,
        execution_mode: form.execution_mode,
      });
      await api.executeTask(createdTask.id);
      setForm({
        title: "",
        description: "",
        priority: "medium",
        assigned_team_id: "",
        execution_mode: "auto",
      });
      setShowForm(false);
      load();
    } catch {
      setError("Error while creating the task. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <WorkspacePageShell
      title="Tasks"
      description="Review the task portfolio, inspect in-flight execution, and keep deliverables within reach."
      meta={
        lastUpdatedAt ? (
          <>
            <span>Last updated {new Date(lastUpdatedAt).toLocaleTimeString("en-US")}</span>
            <span>{tasks.length} visible task(s)</span>
          </>
        ) : undefined
      }
      actions={
        <>
          <Link href="/chat">
            <Button size="sm" className="rounded-full gap-2">
              Plan with Alex
            </Button>
          </Link>
          <Button variant="outline" size="sm" onClick={() => load(true)} className="gap-2 rounded-full">
            {refreshing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Refresh
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-2 rounded-full"
            onClick={() => setShowForm(!showForm)}
          >
            {showForm ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
            {showForm ? "Hide quick execution" : "Quick execution"}
          </Button>
        </>
      }
    >
      {error && (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {showForm && (
        <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
          <CardHeader className="border-b border-black/5 pb-3">
            <div className="space-y-2">
              <h3 className="font-semibold text-slate-900">Quick execution without plan review</h3>
              <p className="text-sm leading-6 text-slate-500">
                Expert path: the task is created and executed immediately. Use Alex instead if you want to clarify, review, and confirm the plan before launch.
              </p>
            </div>
          </CardHeader>
          <CardContent className="pt-5">
            <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              This action bypasses explicit plan review and starts execution as soon as the task is created.
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                placeholder="Task title"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                required
              />
              <Textarea
                placeholder="Detailed description…"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                className="min-h-[96px]"
                required
              />
              <div className="flex flex-col gap-3 lg:flex-row">
                <select
                  value={form.priority}
                  onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value as "low" | "medium" | "high" }))}
                  className="flex-1 rounded-2xl border border-input bg-white px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <option value="low">Low priority</option>
                  <option value="medium">Medium priority</option>
                  <option value="high">High priority</option>
                </select>
                <select
                  value={form.assigned_team_id}
                  onChange={(e) => setForm((f) => ({ ...f, assigned_team_id: e.target.value }))}
                  className="flex-1 rounded-2xl border border-input bg-white px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <option value="">Auto-select (if only one team)</option>
                  {teams.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>
              <select
                value={form.execution_mode}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    execution_mode: e.target.value as TaskExecutionMode,
                  }))
                }
                className="w-full rounded-2xl border border-input bg-white px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <option value="auto">Hybrid auto mode (default)</option>
                <option value="standalone">Isolated standalone mode</option>
                <option value="dependency_graph">Explicit dependency mode</option>
              </select>
              <Button
                type="submit"
                disabled={submitting}
                className="gap-2 rounded-full"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Execute without plan review
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="rounded-2xl border border-black/5 bg-white px-6 py-16 text-center text-slate-500 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.12)]">
          <p className="text-lg font-medium text-slate-900">No tasks yet.</p>
          <p className="mt-2 text-sm">
            Use Alex to scope and confirm the next task, or use quick execution if you are comfortable proceeding without plan review.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
        </div>
      )}
    </WorkspacePageShell>
  );
}
