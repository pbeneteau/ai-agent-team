"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Loader2, MessageSquare, RefreshCw, Trash2 } from "lucide-react";

import { TaskDetailView } from "@/components/tasks/TaskDetailView";
import { STATUS_CONFIG } from "@/components/tasks/task-ui";
import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, extractApiErrorMessage, type Task } from "@/lib/api";
import { useToast } from "@/lib/ws-context";

function formatRelativeTime(value: string): string {
  const deltaMs = Date.now() - new Date(value).getTime();
  const deltaMinutes = Math.max(0, Math.round(deltaMs / 60000));
  if (deltaMinutes < 1) {
    return "just now";
  }
  if (deltaMinutes < 60) {
    return `${deltaMinutes} min ago`;
  }
  const deltaHours = Math.round(deltaMinutes / 60);
  if (deltaHours < 24) {
    return `${deltaHours} h ago`;
  }
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function TaskDetailPage() {
  const params = useParams<{ taskId: string }>();
  const router = useRouter();
  const taskId = typeof params?.taskId === "string" ? params.taskId : "";
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const { push } = useToast();

  const load = useCallback(async (silent = false) => {
    if (!taskId) {
      setError("Unable to identify this task.");
      setLoading(false);
      return;
    }
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const nextTask = await api.getTask(taskId);
      setTask(nextTask);
      setError(null);
    } catch (loadError) {
      console.error("[TaskDetailPage] Failed to load task:", loadError);
      setError("Unable to load this task.");
      setTask(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [taskId]);

  useEffect(() => {
    load();
  }, [load]);

  const taskStatus = task ? STATUS_CONFIG[task.status] : null;

  async function handleDeleteTask() {
    if (!task) {
      return;
    }
    if (task.status === "running") {
      const message = "Running tasks cannot be deleted.";
      setError(message);
      push("error", message);
      return;
    }
    if (!confirm(`Delete task "${task.title}" and all of its deliverables? This action cannot be undone.`)) {
      return;
    }

    setDeleting(true);
    setError(null);
    try {
      await api.deleteTask(task.id);
      push("success", `Task "${task.title}" deleted.`);
      router.push("/tasks");
    } catch (deleteError) {
      const message = extractApiErrorMessage(deleteError, "Error while deleting the task.");
      setError(message);
      push("error", message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <WorkspacePageShell
      eyebrow={
        taskStatus ? (
          <Badge variant="outline" className={`text-xs ${taskStatus.className}`}>
            <taskStatus.Icon className={`w-3.5 h-3.5${task?.status === "running" ? " animate-spin" : ""}`} />
            {taskStatus.label}
          </Badge>
        ) : undefined
      }
      title={task?.title ?? "Task detail"}
      description={task?.description ?? "Result, deliverables, execution trace, and risks for this task."}
      meta={
        task ? (
          <>
            <span>Updated {formatRelativeTime(task.updated_at)}</span>
            <span>ID {task.id.slice(0, 8)}</span>
          </>
        ) : undefined
      }
      actions={
        <>
          <Link href="/tasks">
            <Button variant="outline" className="rounded-full gap-2">
              <ArrowLeft className="size-4" />
              Back to tasks
            </Button>
          </Link>
          <Link href="/chat">
            <Button variant="outline" className="rounded-full gap-2">
              <MessageSquare className="size-4" />
              Open Alex
            </Button>
          </Link>
          <Button
            variant="destructive"
            className="rounded-full gap-2"
            onClick={handleDeleteTask}
            disabled={!task || task.status === "running" || deleting}
            title={task?.status === "running" ? "Running tasks cannot be deleted." : "Delete task permanently"}
          >
            {deleting ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
            Delete task
          </Button>
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
      ) : task ? (
        <TaskDetailView task={task} onTaskUpdated={setTask} />
      ) : (
        <Card className="border-black/5 bg-white/92 shadow-none">
          <CardContent className="p-8 text-center text-sm text-slate-500">
            This task is no longer available.
          </CardContent>
        </Card>
      )}
    </WorkspacePageShell>
  );
}
