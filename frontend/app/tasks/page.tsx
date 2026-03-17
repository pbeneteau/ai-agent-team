"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  PlayCircle,
  Plus,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import { DomainSecondaryNav } from "@/components/layout/DomainSecondaryNav";
import { EmptyState } from "@/components/layout/EmptyState";
import { SectionPanel } from "@/components/layout/SectionPanel";
import { StatBlock } from "@/components/layout/StatBlock";
import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { TaskCard } from "@/components/tasks/TaskCard";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, Task, TaskExecutionMode, Team } from "@/lib/api";
import { useWsEvent } from "@/lib/ws-context";

export default function TasksPage() {
  return (
    <Suspense fallback={<div className="h-full min-h-0 bg-[var(--ops-canvas)]" />}>
      <TasksPageContent />
    </Suspense>
  );
}

function TasksPageContent() {
  const searchParams = useSearchParams();
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
    if (!form.title.trim() || !form.description.trim()) {
      return;
    }
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

  const activeView = (() => {
    const view = searchParams.get("view");
    switch (view) {
      case "running":
      case "blocked":
      case "completed":
      case "all":
        return view;
      default:
        return "all";
    }
  })();

  const visibleTasks = tasks.filter((task) => {
    switch (activeView) {
      case "running":
        return task.status === "running";
      case "blocked":
        return task.status === "failed" || task.execution_eligibility !== "eligible";
      case "completed":
        return task.status === "completed";
      default:
        return true;
    }
  });

  const emptyStateDescription =
    activeView === "running"
      ? "No execution is currently in flight."
      : activeView === "blocked"
        ? "No blocked or failed task needs operator attention right now."
        : activeView === "completed"
          ? "No completed task is visible yet."
          : "Use Alex to scope and confirm the next task. Manual launch stays available as a secondary path when the scope is already fixed.";

  const runningCount = tasks.filter((task) => task.status === "running").length;
  const blockedCount = tasks.filter(
    (task) => task.status === "failed" || task.execution_eligibility !== "eligible",
  ).length;
  const completedCount = tasks.filter((task) => task.status === "completed").length;
  const reviewCount = tasks.filter((task) => task.warnings.length > 0 || task.assumptions.length > 0).length;

  const viewMeta = (() => {
    switch (activeView) {
      case "running":
        return {
          title: "Running executions",
          description: "Live work currently in flight. Keep progress, agent activity, and fresh signals easy to scan.",
        };
      case "blocked":
        return {
          title: "Blocked and failed work",
          description: "Tasks that need clarification, review, or a retry before execution can proceed cleanly.",
        };
      case "completed":
        return {
          title: "Completed executions",
          description: "Finished work with results and deliverables ready for review, export, or handoff.",
        };
      default:
        return {
          title: "Execution portfolio",
          description: "Scan the portfolio, then drill into live work, blockers, and finished output without mixing in the planning flow.",
        };
    }
  })();

  return (
    <WorkspacePageShell
      archetype="collection"
      headerMode="compact"
      title="Execution"
      description="Track the execution portfolio, inspect progress, and keep blockers and deliverables within reach."
      meta={
        lastUpdatedAt ? (
          <>
            <span>Last updated {new Date(lastUpdatedAt).toLocaleTimeString("en-US")}</span>
            <span>{visibleTasks.length} visible task(s)</span>
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
            onClick={() => setShowForm(true)}
          >
            <Plus className="w-3.5 h-3.5" />
            Manual launch
          </Button>
        </>
      }
    >
      {error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      ) : null}

      <DomainSecondaryNav domain="execution" />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatBlock label="Running" value={runningCount} icon={<PlayCircle className="size-4" />} tone="accent" />
        <StatBlock label="Blocked" value={blockedCount} icon={<ShieldAlert className="size-4" />} tone="warning" />
        <StatBlock label="Completed" value={completedCount} icon={<CheckCircle2 className="size-4" />} tone="positive" />
        <StatBlock label="Needs review" value={reviewCount} icon={<AlertTriangle className="size-4" />} tone="danger" />
      </div>

      <SectionPanel
        eyebrow={activeView === "all" ? "Portfolio" : "Filtered view"}
        title={viewMeta.title}
        description={viewMeta.description}
        tone="subtle"
        actions={
          activeView === "all" ? (
            <Button variant="outline" size="sm" className="rounded-full gap-2" onClick={() => setShowForm(true)}>
              <Plus className="size-3.5" />
              Manual launch
            </Button>
          ) : null
        }
      >
        <p className="text-sm leading-6 text-slate-600">
          Plan-first remains the nominal path. This surface is for execution oversight, and manual launch only exists for already-scoped work.
        </p>
      </SectionPanel>

      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Manual launch without plan review</DialogTitle>
            <DialogDescription>
              Use this only when the scope is already fixed and you intentionally need to bypass the normal plan confirmation flow.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            This path starts execution as soon as the task is created. If scoping or clarification is still open, go back to Alex first.
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
              className="min-h-[120px]"
              required
            />
            <div className="flex flex-col gap-3 lg:flex-row">
              <select
                value={form.priority}
                onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value as "low" | "medium" | "high" }))}
                className="flex-1 rounded-[12px] border border-[var(--ops-control-border)] bg-[var(--ops-control)] px-3 py-2 text-sm text-[var(--ops-ink)] outline-none focus-visible:border-[var(--ops-control-border-strong)] focus-visible:ring-3 focus-visible:ring-ring/30"
              >
                <option value="low">Low priority</option>
                <option value="medium">Medium priority</option>
                <option value="high">High priority</option>
              </select>
              <select
                value={form.assigned_team_id}
                onChange={(e) => setForm((f) => ({ ...f, assigned_team_id: e.target.value }))}
                className="flex-1 rounded-[12px] border border-[var(--ops-control-border)] bg-[var(--ops-control)] px-3 py-2 text-sm text-[var(--ops-ink)] outline-none focus-visible:border-[var(--ops-control-border-strong)] focus-visible:ring-3 focus-visible:ring-ring/30"
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
              className="w-full rounded-[12px] border border-[var(--ops-control-border)] bg-[var(--ops-control)] px-3 py-2 text-sm text-[var(--ops-ink)] outline-none focus-visible:border-[var(--ops-control-border-strong)] focus-visible:ring-3 focus-visible:ring-ring/30"
            >
              <option value="auto">Hybrid auto mode (default)</option>
              <option value="standalone">Isolated standalone mode</option>
              <option value="dependency_graph">Explicit dependency mode</option>
            </select>
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <Link href="/chat" className="text-sm font-medium text-primary hover:underline">
                Need scoping instead? Open Alex
              </Link>
              <Button type="submit" disabled={submitting} className="gap-2 rounded-full">
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Launch without plan review
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      ) : visibleTasks.length === 0 ? (
        <EmptyState
          title={activeView === "all" ? "No tasks yet." : "Nothing to show in this view."}
          description={emptyStateDescription}
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {visibleTasks.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
        </div>
      )}
    </WorkspacePageShell>
  );
}
