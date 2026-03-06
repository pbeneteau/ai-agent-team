"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Task, TaskStatus, TaskPriority } from "@/lib/api";
import { api } from "@/lib/api";
import { CheckCircle, Clock, Loader2, XCircle, RotateCcw, ChevronRight } from "lucide-react";

const STATUS_CONFIG: Record<TaskStatus, { icon: React.ReactNode; className: string; label: string }> = {
  pending: {
    icon: <Clock className="w-3.5 h-3.5" />,
    className: "bg-slate-100 text-slate-600 border-slate-200",
    label: "En attente",
  },
  running: {
    icon: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
    className: "bg-blue-100 text-blue-700 border-blue-200",
    label: "En cours",
  },
  completed: {
    icon: <CheckCircle className="w-3.5 h-3.5" />,
    className: "bg-green-100 text-green-700 border-green-200",
    label: "Terminé",
  },
  failed: {
    icon: <XCircle className="w-3.5 h-3.5" />,
    className: "bg-red-100 text-red-700 border-red-200",
    label: "Échoué",
  },
};

const PRIORITY_CONFIG: Record<TaskPriority, { className: string; label: string }> = {
  low: { className: "bg-gray-100 text-gray-600", label: "Faible" },
  medium: { className: "bg-yellow-100 text-yellow-700", label: "Moyen" },
  high: { className: "bg-red-100 text-red-700", label: "Haute" },
};

function MarkdownText({ text }: { text: string }) {
  // Minimal markdown: bold, code blocks, line breaks
  const lines = text.split("\n");
  return (
    <div className="space-y-1 text-xs leading-relaxed">
      {lines.map((line, i) => {
        if (line.startsWith("# ")) return <h1 key={i} className="font-bold text-sm mt-2">{line.slice(2)}</h1>;
        if (line.startsWith("## ")) return <h2 key={i} className="font-semibold text-sm mt-2">{line.slice(3)}</h2>;
        if (line.startsWith("### ")) return <h3 key={i} className="font-medium mt-1">{line.slice(4)}</h3>;
        if (line.startsWith("- ") || line.startsWith("* ")) return <li key={i} className="ml-4 list-disc">{line.slice(2)}</li>;
        if (line === "") return <div key={i} className="h-1" />;
        return <p key={i}>{line}</p>;
      })}
    </div>
  );
}

export function TaskCard({
  task,
  onRetry,
}: {
  task: Task;
  onRetry?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const status = STATUS_CONFIG[task.status];
  const priority = PRIORITY_CONFIG[task.priority];

  async function handleRetry() {
    if (!confirm(`Relancer la tâche "${task.title}" ?`)) return;
    setRetrying(true);
    try {
      await api.createTask({
        title: task.title,
        description: task.description,
        priority: task.priority,
        assigned_team_id: task.assigned_team_id ?? undefined,
      });
      onRetry?.();
      setOpen(false);
    } catch (e) {
      alert(`Erreur : ${e}`);
    } finally {
      setRetrying(false);
    }
  }

  return (
    <>
      <Card
        className="hover:shadow-md transition-shadow cursor-pointer"
        onClick={() => setOpen(true)}
      >
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <p className="font-semibold text-sm leading-tight">{task.title}</p>
            <div className="flex gap-1.5 flex-shrink-0">
              <Badge variant="outline" className={`text-xs gap-1 ${status.className}`}>
                {status.icon}
                {status.label}
              </Badge>
              <Badge variant="outline" className={`text-xs ${priority.className}`}>
                {priority.label}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0 space-y-2">
          <p className="text-xs text-muted-foreground line-clamp-2">{task.description}</p>

          {task.status === "running" && task.progress_log.length > 0 && (
            <div className="text-xs bg-blue-50 rounded p-2 text-blue-700">
              {task.progress_log[task.progress_log.length - 1].message}
            </div>
          )}

          {task.result && (
            <div className="text-xs bg-green-50 rounded p-2 text-green-800 max-h-24 overflow-y-auto">
              <span className="font-medium">Résultat :</span>{" "}
              {task.result.slice(0, 300)}
              {task.result.length > 300 && (
                <span className="text-green-600 ml-1 inline-flex items-center gap-0.5">
                  … <ChevronRight className="w-3 h-3" /> voir tout
                </span>
              )}
            </div>
          )}

          {task.error && (
            <div className="text-xs bg-red-50 rounded p-2 text-red-700">
              <span className="font-medium">Erreur :</span> {task.error}
            </div>
          )}

          <p className="text-[10px] text-muted-foreground">
            Créé le {new Date(task.created_at).toLocaleString("fr-FR")}
          </p>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 flex-wrap">
              <span>{task.title}</span>
              <Badge variant="outline" className={`text-xs gap-1 ${status.className}`}>
                {status.icon}
                {status.label}
              </Badge>
              <Badge variant="outline" className={`text-xs ${priority.className}`}>
                {priority.label}
              </Badge>
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 text-sm">
            {/* Description */}
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Description</p>
              <p className="text-sm text-muted-foreground">{task.description}</p>
            </div>

            {/* Agents assignés */}
            {task.assigned_agent_ids.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Agents assignés</p>
                <div className="flex flex-wrap gap-1">
                  {task.assigned_agent_ids.map((id) => (
                    <Badge key={id} variant="secondary" className="text-xs font-mono">
                      {id.slice(0, 8)}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Résultat complet */}
            {task.result && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Résultat</p>
                <div className="bg-green-50 rounded-md p-3 border border-green-100">
                  <MarkdownText text={task.result} />
                </div>
              </div>
            )}

            {/* Erreur */}
            {task.error && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Erreur</p>
                <div className="bg-red-50 rounded-md p-3 border border-red-100 text-red-700 text-xs font-mono whitespace-pre-wrap">
                  {task.error}
                </div>
              </div>
            )}

            {/* Progress log */}
            {task.progress_log.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                  Chronologie ({task.progress_log.length} événements)
                </p>
                <div className="space-y-1 max-h-48 overflow-y-auto border rounded-md p-2 bg-slate-50">
                  {task.progress_log.map((entry, i) => (
                    <div key={i} className="flex gap-2 text-xs">
                      <span className="text-muted-foreground shrink-0 tabular-nums">
                        {new Date(entry.timestamp).toLocaleTimeString("fr-FR")}
                      </span>
                      {entry.agent && (
                        <span className="text-blue-600 shrink-0">[{entry.agent}]</span>
                      )}
                      <span>{entry.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Métadonnées */}
            <div className="text-xs text-muted-foreground pt-1 border-t flex gap-4">
              <span>Créé : {new Date(task.created_at).toLocaleString("fr-FR")}</span>
              <span>Mis à jour : {new Date(task.updated_at).toLocaleString("fr-FR")}</span>
            </div>

            {/* Actions */}
            {task.status === "failed" && (
              <div className="flex justify-end pt-1">
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-2"
                  onClick={handleRetry}
                  disabled={retrying}
                >
                  {retrying ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <RotateCcw className="w-3.5 h-3.5" />
                  )}
                  Réessayer
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
