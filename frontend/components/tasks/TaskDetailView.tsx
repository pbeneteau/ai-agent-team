"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Download,
  ExternalLink,
  FileText,
  GitBranch,
  Loader2,
  RotateCcw,
  ShieldAlert,
  Workflow,
} from "lucide-react";

import { EmptyState } from "@/components/layout/EmptyState";
import { SectionPanel } from "@/components/layout/SectionPanel";
import { SegmentedTabs } from "@/components/layout/SegmentedTabs";
import { StatBlock } from "@/components/layout/StatBlock";
import { MarkdownContent } from "@/components/ui/markdown-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, type Agent, type Task, type TaskDeliverable } from "@/lib/api";
import {
  EXECUTION_MODE_LABELS,
  NODE_STATUS_CONFIG,
  NODE_TYPE_LABELS,
  PLAN_STATUS_LABELS,
  PRIORITY_CONFIG,
  STATUS_CONFIG,
  formatBytes,
  formatDateTime,
} from "@/components/tasks/task-ui";

type TaskDetailTab = "summary" | "deliverables" | "execution" | "sources";

interface TaskDetailViewProps {
  task: Task;
  onTaskUpdated?: (task: Task) => void;
}

function SourceItem({ source }: { source: string }) {
  const urlMatch = source.match(/https?:\/\/[^\s)]+/);
  const url = urlMatch?.[0];
  return (
    <li className="text-sm flex items-start gap-2">
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 hover:underline flex items-center gap-1 break-all"
        >
          <ExternalLink className="w-3 h-3 shrink-0" />
          {source}
        </a>
      ) : (
        <span className="text-slate-600">{source}</span>
      )}
    </li>
  );
}

export function TaskDetailView({ task, onTaskUpdated }: TaskDetailViewProps) {
  const [activeTab, setActiveTab] = useState<TaskDetailTab>("summary");
  const [taskDetail, setTaskDetail] = useState(task);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [deliverables, setDeliverables] = useState<TaskDeliverable[]>(task.deliverables ?? []);
  const [loadingDeliverables, setLoadingDeliverables] = useState(false);
  const [selectedDeliverablePath, setSelectedDeliverablePath] = useState<string | null>(null);
  const [selectedDeliverableContent, setSelectedDeliverableContent] = useState("");
  const [loadingDeliverableContent, setLoadingDeliverableContent] = useState(false);

  useEffect(() => {
    setTaskDetail(task);
    setDeliverables(task.deliverables ?? []);
  }, [task]);

  const refreshTask = useCallback(async () => {
    setLoadingDetail(true);
    try {
      const freshTask = await api.getTask(task.id);
      setTaskDetail(freshTask);
      onTaskUpdated?.(freshTask);
    } finally {
      setLoadingDetail(false);
    }
  }, [onTaskUpdated, task.id]);

  useEffect(() => {
    refreshTask().catch((error) => {
      console.error("[TaskDetailView] Failed to refresh task:", error);
    });
  }, [refreshTask]);

  useEffect(() => {
    let active = true;
    api.getAgents()
      .then((items) => {
        if (active) {
          setAgents(items);
        }
      })
      .catch((error) => {
        console.error("[TaskDetailView] Failed to load agents:", error);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setLoadingDeliverables(true);
    api.getTaskDeliverables(task.id)
      .then((items) => {
        if (active) {
          setDeliverables(items);
        }
      })
      .catch((error) => {
        console.error("[TaskDetailView] Failed to load deliverables:", error);
      })
      .finally(() => {
        if (active) {
          setLoadingDeliverables(false);
        }
      });
    return () => {
      active = false;
    };
  }, [task.id]);

  const currentTask = taskDetail;
  const status = STATUS_CONFIG[currentTask.status];
  const priority = PRIORITY_CONFIG[currentTask.priority];
  const observabilityHref = "/usage?section=reliability";
  const planNodes = currentTask.execution_plan.nodes;
  const availableDeliverables = deliverables.length > 0 ? deliverables : currentTask.deliverables;
  const planNodeById = useMemo(
    () => Object.fromEntries(planNodes.map((node) => [node.id, node])),
    [planNodes],
  );
  const completedNodes = planNodes.filter((node) => node.status === "completed").length;
  const hasWarnings = currentTask.warnings.length > 0 || currentTask.assumptions.length > 0;
  const reviewItems = currentTask.warnings.length + currentTask.assumptions.length;
  const latestProgressEntry =
    currentTask.progress_log.length > 0 ? currentTask.progress_log[currentTask.progress_log.length - 1] : null;
  const agentNameById = useMemo(
    () => Object.fromEntries(agents.map((agent) => [agent.id, agent.name])),
    [agents],
  );
  const busyAgentIds = useMemo(
    () =>
      Array.from(
        new Set(
          planNodes
            .filter((node) => node.status === "running" && node.assigned_agent_id)
            .map((node) => node.assigned_agent_id as string),
        ),
      ),
    [planNodes],
  );
  const assignedOnlyAgentIds = useMemo(
    () => currentTask.assigned_agent_ids.filter((id) => !busyAgentIds.includes(id)),
    [busyAgentIds, currentTask.assigned_agent_ids],
  );

  useEffect(() => {
    if (availableDeliverables.length === 0) {
      setSelectedDeliverablePath(null);
      setSelectedDeliverableContent("");
      return;
    }

    const preferred =
      availableDeliverables.find((item) => item.path === "system/final-deliverable.md")?.path ??
      availableDeliverables[0].path;

    if (!selectedDeliverablePath || !availableDeliverables.some((item) => item.path === selectedDeliverablePath)) {
      setSelectedDeliverablePath(preferred);
    }
  }, [availableDeliverables, selectedDeliverablePath]);

  useEffect(() => {
    if (!selectedDeliverablePath) {
      return;
    }
    let active = true;
    setLoadingDeliverableContent(true);
    api.readTaskDeliverable(task.id, selectedDeliverablePath)
      .then((payload) => {
        if (active) {
          setSelectedDeliverableContent(payload.content);
        }
      })
      .catch((error) => {
        console.error("[TaskDetailView] Failed to read deliverable:", error);
        if (active) {
          setSelectedDeliverableContent("Unable to load this deliverable.");
        }
      })
      .finally(() => {
        if (active) {
          setLoadingDeliverableContent(false);
        }
      });
    return () => {
      active = false;
    };
  }, [selectedDeliverablePath, task.id]);

  function getAgentLabel(agentId: string) {
    return (
      planNodes.find((node) => node.assigned_agent_id === agentId)?.assigned_agent_name ??
      currentTask.progress_log.find((entry) => entry.agent_id === agentId)?.agent_name ??
      agentNameById[agentId] ??
      agentId.slice(0, 8)
    );
  }

  async function handleRetry() {
    if (!confirm(`Retry task "${currentTask.title}"?`)) return;
    setRetrying(true);
    try {
      const createdTask = await api.createTask({
        title: currentTask.title,
        description: currentTask.description,
        priority: currentTask.priority,
        assigned_team_id: currentTask.assigned_team_id ?? undefined,
        assigned_agent_id: currentTask.assigned_agent_id ?? undefined,
        execution_mode: currentTask.execution_mode,
        context_document_ids: currentTask.context_document_ids,
      });
      await api.executeTask(createdTask.id);
      if (typeof window !== "undefined") {
        window.location.assign(`/tasks/${createdTask.id}`);
      }
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatBlock
          label="Status"
          value={status.label}
          description={priority.label}
          tone={currentTask.status === "failed" ? "danger" : currentTask.status === "running" ? "accent" : "default"}
          icon={<status.Icon className={`size-4${currentTask.status === "running" ? " animate-spin" : ""}`} />}
        />
        <StatBlock
          label="Progress"
          value={`${completedNodes}/${planNodes.length || 0}`}
          description={`Completed node${planNodes.length === 1 ? "" : "s"}`}
        />
        <StatBlock
          label="Deliverables"
          value={availableDeliverables.length}
          description={availableDeliverables.length > 0 ? "Files available" : "No file yet"}
          tone={availableDeliverables.length > 0 ? "positive" : "default"}
        />
        <StatBlock
          label="Review"
          value={reviewItems}
          description={currentTask.execution_eligibility !== "eligible" ? "Blocking clarification" : "Warnings and assumptions"}
          tone={currentTask.execution_eligibility !== "eligible" ? "warning" : reviewItems > 0 ? "warning" : "default"}
        />
      </div>

      <SectionPanel
        eyebrow="Operator readout"
        title="Summary first read"
        description="Read this block before drilling into the full execution trace."
        tone="muted"
        actions={
          <>
            <Badge variant="outline">{EXECUTION_MODE_LABELS[currentTask.execution_mode]}</Badge>
            <Badge variant="outline">{PLAN_STATUS_LABELS[currentTask.execution_plan.status]}</Badge>
          </>
        }
      >
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
          <div className="space-y-4">
            {currentTask.execution_eligibility !== "eligible" ? (
              <div className="ops-signal-warning rounded-[16px] border px-4 py-4 text-sm">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <div>
                    <p className="font-semibold">Execution not ready</p>
                    <ul className="mt-2 space-y-1.5">
                      {currentTask.execution_blockers.map((blocker) => (
                        <li key={blocker}>- {blocker}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ) : null}

            {currentTask.status === "failed" && currentTask.error ? (
              <div className="ops-signal-danger rounded-[16px] border px-4 py-4 text-sm">
                <p className="text-xs font-semibold uppercase tracking-[0.14em]">Failure</p>
                <FailureMetaChips errorType={currentTask.error_type} failureStage={currentTask.failure_stage} />
                <div className="mt-3 whitespace-pre-wrap rounded-[14px] border border-[var(--ops-signal-danger-border)] bg-white/75 p-4 font-mono text-xs text-[var(--ops-signal-danger-ink)]">
                  {currentTask.error}
                </div>
                <FailureTraceback traceback={currentTask.error_traceback} />
                <div className="mt-4">
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
                    Retry execution
                  </Button>
                </div>
              </div>
            ) : currentTask.status === "running" && latestProgressEntry ? (
              <div className="ops-signal-info rounded-[16px] border px-4 py-4 text-sm">
                <p className="text-xs font-semibold uppercase tracking-[0.14em]">Live signal</p>
                {(latestProgressEntry.agent_name ?? latestProgressEntry.agent) ? (
                  <p className="mt-2 text-xs font-medium">
                    {latestProgressEntry.agent_name ?? latestProgressEntry.agent}
                  </p>
                ) : null}
                <p className="mt-1 leading-6">{latestProgressEntry.message}</p>
              </div>
            ) : currentTask.result ? (
              <div className="rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] p-5">
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ops-signal-positive-ink)]">Final result</p>
                <MarkdownContent content={currentTask.result} className="prose-sm" />
              </div>
            ) : (
              <EmptyState description="No consolidated operator summary is available yet." />
            )}
          </div>

          <div className="space-y-4">
            <div className="rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Task facts</p>
              <div className="mt-4 grid gap-4">
                <SummaryRow label="Created" value={formatDateTime(currentTask.created_at)} />
                <SummaryRow label="Updated" value={formatDateTime(currentTask.updated_at)} />
                <SummaryRow label="Mode" value={EXECUTION_MODE_LABELS[currentTask.execution_mode]} />
                <SummaryRow label="Brief revision" value={currentTask.brief_revision ? `Rev ${currentTask.brief_revision}` : "None"} />
                <SummaryRow label="Assigned agents" value={`${currentTask.assigned_agent_ids.length}`} />
                <SummaryRow label="Sources" value={`${currentTask.sources.length}`} />
              </div>
            </div>

            {currentTask.assigned_agent_ids.length > 0 ? (
              <div className="rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Assigned agents</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {busyAgentIds.map((id) => (
                    <Badge
                      key={`busy-${id}`}
                      variant="info"
                      className="px-3 py-1 text-xs"
                    >
                      {getAgentLabel(id)} · Busy
                    </Badge>
                  ))}
                  {assignedOnlyAgentIds.map((id) => (
                    <Badge
                      key={`assigned-${id}`}
                      variant="secondary"
                      className="px-3 py-1 text-xs"
                    >
                      {getAgentLabel(id)} · Assigned
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            <Link href={observabilityHref}>
              <Button variant="outline" className="w-full gap-2">
                <Workflow className="size-4" />
                Open Reliability
              </Button>
            </Link>
          </div>
        </div>
      </SectionPanel>

      {loadingDetail ? (
        <div className="ops-signal-info flex items-center gap-2 rounded-[16px] border px-4 py-3 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading the latest task detail…
        </div>
      ) : null}

      <SegmentedTabs
        items={[
          { id: "summary", label: "Readout" },
          { id: "deliverables", label: "Deliverables" },
          { id: "execution", label: "Execution trace" },
          { id: "sources", label: "Sources & risks" },
        ]}
        value={activeTab}
        onValueChange={setActiveTab}
      />

      {activeTab === "summary" ? (
        <div className="space-y-5">
          <SectionPanel
            eyebrow="Task brief"
            title="Execution scope"
            description="Canonical task description and planning context captured for this execution."
            tone="subtle"
          >
            <div className="space-y-4">
              <p className="text-sm leading-6 text-slate-700">{currentTask.description}</p>
              {currentTask.execution_plan.planning_notes ? (
                <div className="rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] px-4 py-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Planning notes</p>
                  <p className="mt-2 text-sm leading-6 text-slate-700">{currentTask.execution_plan.planning_notes}</p>
                </div>
              ) : null}
            </div>
          </SectionPanel>

          <SectionPanel
            eyebrow="Signals"
            title="Operator notes"
            description="Warnings, assumptions, and review signals that should stay visible before sign-off."
            tone="subtle"
          >
            {hasWarnings ? (
              <div className="grid gap-4 xl:grid-cols-2">
                {currentTask.warnings.length > 0 ? (
                  <div className="ops-signal-warning rounded-[16px] border px-4 py-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-800">Unverified</p>
                    <ul className="mt-3 space-y-1.5 list-disc pl-4 text-sm text-amber-900">
                      {currentTask.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {currentTask.assumptions.length > 0 ? (
                  <div className="ops-signal-warning rounded-[16px] border px-4 py-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-800">Assumptions / TBD</p>
                    <ul className="mt-3 space-y-1.5 list-disc pl-4 text-sm text-amber-900">
                      {currentTask.assumptions.map((assumption) => (
                        <li key={assumption}>{assumption}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyState description="No warning or assumption requires operator review right now." />
            )}
          </SectionPanel>
        </div>
      ) : null}

      {activeTab === "deliverables" ? (
        <SectionPanel
          eyebrow="Artifacts"
          title="Deliverables"
          description="Browse the files generated for this task."
          actions={
            currentTask.deliverables_dir ? (
              <span className="rounded-full bg-[var(--ops-surface-muted)] px-3 py-1 text-[11px] font-medium text-slate-600">
                {currentTask.deliverables_dir}
              </span>
            ) : null
          }
        >
          {loadingDeliverables ? (
            <div className="flex items-center gap-2 rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-muted)] px-4 py-3 text-sm text-slate-600">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading deliverables…
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
              <div className="rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-muted)] p-3">
                <div className="space-y-2">
                  {availableDeliverables.length === 0 ? (
                    <EmptyState description="No deliverables generated yet." className="px-4 py-6" />
                  ) : (
                    availableDeliverables.map((deliverable) => {
                      const isActive = deliverable.path === selectedDeliverablePath;
                      return (
                        <div
                          key={deliverable.path}
                          className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                            isActive
                              ? "border-slate-900 bg-white shadow-sm"
                              : "border-transparent bg-transparent hover:border-slate-200 hover:bg-white/80"
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <div className="rounded-xl bg-slate-100 p-2 text-slate-600">
                              <FileText className="h-4 w-4" />
                            </div>
                            <button
                              type="button"
                              onClick={() => setSelectedDeliverablePath(deliverable.path)}
                              className="min-w-0 flex-1 text-left"
                            >
                              <p className="truncate text-sm font-medium text-slate-900">{deliverable.name}</p>
                              <p className="mt-1 truncate text-xs text-slate-500">{deliverable.path}</p>
                              <p className="mt-2 text-[11px] text-slate-400">
                                {formatBytes(deliverable.size_bytes)} · {formatDateTime(deliverable.modified_at)}
                              </p>
                            </button>
                            <a
                              href={api.getTaskDeliverableDownloadUrl(task.id, deliverable.path)}
                              download={deliverable.name}
                              className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                              title="Download"
                            >
                              <Download className="h-4 w-4" />
                            </a>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              <div className="rounded-2xl border bg-slate-50/70 p-4">
                {selectedDeliverablePath ? (
                  <>
                    <div className="mb-4 flex items-center justify-between gap-3 flex-wrap">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">
                          {availableDeliverables.find((item) => item.path === selectedDeliverablePath)?.name ?? selectedDeliverablePath}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">{selectedDeliverablePath}</p>
                      </div>
                      <a
                        href={api.getTaskDeliverableDownloadUrl(task.id, selectedDeliverablePath)}
                        download={availableDeliverables.find((item) => item.path === selectedDeliverablePath)?.name}
                        className="inline-flex items-center gap-2 rounded-xl border bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                      >
                        <Download className="h-4 w-4" />
                        Download
                      </a>
                    </div>
                    <div className="rounded-2xl border bg-white p-5">
                      {loadingDeliverableContent ? (
                        <div className="flex items-center gap-2 text-sm text-slate-500">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Loading content…
                        </div>
                      ) : (
                        <MarkdownContent content={selectedDeliverableContent} className="prose-sm" />
                      )}
                    </div>
                  </>
                ) : (
                  <EmptyState description="No deliverable available." className="flex min-h-40 items-center justify-center" />
                )}
              </div>
            </div>
          )}
        </SectionPanel>
      ) : null}

      {activeTab === "execution" ? (
        <div className="space-y-5">
          <SectionPanel
            eyebrow="Plan"
            title="Execution plan"
            description="Structured nodes, dependencies, and per-node output for this execution."
          >
            {planNodes.length === 0 ? (
              <Card className="border-black/5 bg-white/92 shadow-none">
                <CardContent className="p-5 text-sm text-slate-500">
                  No structured execution node is available for this task.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-4">
                {planNodes.map((node, index) => {
                  const nodeStatus = NODE_STATUS_CONFIG[node.status];
                  const dependencyLabels = node.depends_on.map(
                    (dependencyId) => planNodeById[dependencyId]?.title ?? dependencyId.slice(0, 8),
                  );

                  return (
                    <article
                      key={node.id}
                      className="rounded-3xl border border-slate-200 bg-white p-5 shadow-none"
                    >
                      <div className="flex items-start justify-between gap-4 flex-wrap">
                        <div className="space-y-2">
                          <div className="flex items-center gap-3 flex-wrap">
                            <span className="inline-flex h-8 min-w-8 items-center justify-center rounded-full bg-slate-900 px-2 text-xs font-semibold text-white">
                              {index + 1}
                            </span>
                            <h3 className="text-base font-semibold text-slate-950">{node.title}</h3>
                          </div>
                          <p className="text-sm text-slate-500">
                            {node.assigned_agent_name ?? node.assigned_agent_id ?? "Unknown agent"}
                          </p>
                        </div>

                        <div className="flex gap-2 flex-wrap">
                          <Badge className={`text-xs ${nodeStatus.className}`}>
                            {nodeStatus.label}
                          </Badge>
                          <Badge variant="outline" className="text-xs text-slate-600">
                            {NODE_TYPE_LABELS[node.node_type]}
                          </Badge>
                        </div>
                      </div>

                      <p className="mt-4 text-sm leading-6 text-slate-700">{node.description}</p>

                      {dependencyLabels.length > 0 ? (
                        <div className="mt-4 flex items-center gap-2 flex-wrap text-xs text-slate-600">
                          <GitBranch className="h-3.5 w-3.5" />
                          <span className="font-medium">Depends on</span>
                          {dependencyLabels.map((label) => (
                            <Badge
                              key={`${node.id}-${label}`}
                              variant="secondary"
                              className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-700"
                            >
                              {label}
                            </Badge>
                          ))}
                        </div>
                      ) : null}

                      {node.result ? (
                        <div className="mt-5 rounded-2xl border bg-slate-50 p-4">
                          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                            Node result
                          </p>
                          <MarkdownContent content={node.result} className="prose-sm" />
                        </div>
                      ) : null}

                      {node.error ? (
                        <div className="mt-4 rounded-2xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-red-700">
                            Node error
                          </p>
                          <FailureMetaChips
                            errorType={node.error_type}
                            failureStage={node.failure_stage}
                          />
                          <div className="mt-3 rounded-2xl border border-red-100 bg-white/70 p-4 font-mono text-xs whitespace-pre-wrap text-red-700">
                            {node.error}
                          </div>
                          <FailureTraceback traceback={node.error_traceback} />
                        </div>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            )}
          </SectionPanel>

          <SectionPanel
            eyebrow="Progress"
            title="Timeline"
            description="Chronological execution log with the latest agent messages and structured flow markers."
            tone="subtle"
          >
            {currentTask.progress_log.length === 0 ? (
              <Card className="border-black/5 bg-white/92 shadow-none">
                <CardContent className="p-5 text-sm text-slate-500">
                  No progress event recorded.
                </CardContent>
              </Card>
            ) : (
              <div className="rounded-3xl border bg-slate-50 p-5">
                <div className="space-y-4">
                  {currentTask.progress_log.map((entry, index) => (
                    <div key={`${entry.timestamp}-${index}`} className="flex gap-4">
                      <div className="pt-0.5 text-xs tabular-nums text-slate-400">
                        {new Date(entry.timestamp).toLocaleTimeString("en-US")}
                      </div>
                      <div className="min-w-0 flex-1 border-l border-slate-200 pl-4">
                        {(entry.agent_name ?? entry.agent) ? (
                          <p className="text-xs font-medium text-blue-700">
                            {entry.agent_name ?? entry.agent}
                          </p>
                        ) : null}
                        {(entry.structured_flow || entry.structured_channel) ? (
                          <div className="mt-1 flex flex-wrap gap-2">
                            {entry.structured_flow ? (
                              <Badge variant="outline" className="text-[10px]">
                                Flow: {entry.structured_flow}
                              </Badge>
                            ) : null}
                            {entry.structured_channel ? (
                              <Badge variant="outline" className="text-[10px]">
                                Channel: {entry.structured_channel}
                              </Badge>
                            ) : null}
                          </div>
                        ) : null}
                        <p className="mt-1 text-sm leading-6 text-slate-700">{entry.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </SectionPanel>
        </div>
      ) : null}

      {activeTab === "sources" ? (
        <div className="space-y-5">
          <SectionPanel
            eyebrow="Evidence"
            title="Sources and review points"
            description="Cited references, uncertainty markers, and other review signals extracted from the execution."
          >
            <div className="space-y-5">
              {currentTask.sources.length > 0 ? (
                <section className="rounded-3xl border border-blue-100 bg-blue-50/70 p-5 shadow-none">
                  <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-blue-700">
                    <ExternalLink className="h-3.5 w-3.5" />
                    Cited sources
                  </p>
                  <ul className="mt-4 space-y-2">
                    {currentTask.sources.map((source) => (
                      <SourceItem key={source} source={source} />
                    ))}
                  </ul>
                </section>
              ) : null}

              {hasWarnings ? (
                <section className="rounded-3xl border border-amber-100 bg-amber-50/80 p-5 shadow-none">
                  <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-amber-700">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    Review points
                  </p>
                  {currentTask.warnings.length > 0 ? (
                    <div className="mt-4">
                      <p className="text-xs font-semibold text-amber-900">Unverified</p>
                      <ul className="mt-2 space-y-1.5 list-disc pl-4 text-sm text-amber-800">
                        {currentTask.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {currentTask.assumptions.length > 0 ? (
                    <div className="mt-4">
                      <p className="text-xs font-semibold text-amber-900">Assumptions / TBD</p>
                      <ul className="mt-2 space-y-1.5 list-disc pl-4 text-sm text-amber-800">
                        {currentTask.assumptions.map((assumption) => (
                          <li key={assumption}>{assumption}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </section>
              ) : null}

              {!currentTask.sources.length && !hasWarnings ? (
                <Card className="border-black/5 bg-white/92 shadow-none">
                  <CardContent className="p-5 text-sm text-slate-500">
                    No risk or structured source has been extracted for this task.
                  </CardContent>
                </Card>
              ) : null}
            </div>
          </SectionPanel>

          {currentTask.error ? (
            <section className="rounded-3xl border border-red-100 bg-red-50/80 p-5 shadow-none">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-red-700">
                Error
              </p>
              <FailureMetaChips
                errorType={currentTask.error_type}
                failureStage={currentTask.failure_stage}
              />
              <div className="mt-3 rounded-2xl border border-red-100 bg-white/70 p-4 font-mono text-xs whitespace-pre-wrap text-red-700">
                {currentTask.error}
              </div>
              <FailureTraceback traceback={currentTask.error_traceback} />
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="text-sm font-medium text-slate-900">{value}</p>
    </div>
  );
}

function FailureMetaChips({
  errorType,
  failureStage,
}: {
  errorType: string | null | undefined;
  failureStage: string | null | undefined;
}) {
  if (!errorType && !failureStage) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {errorType ? (
        <Badge variant="outline" className="rounded-full border-red-200 bg-white text-[11px] text-red-700">
          Type: {errorType}
        </Badge>
      ) : null}
      {failureStage ? (
        <Badge variant="outline" className="rounded-full border-red-200 bg-white text-[11px] text-red-700">
          Stage: {failureStage}
        </Badge>
      ) : null}
    </div>
  );
}

function FailureTraceback({ traceback }: { traceback: string | null | undefined }) {
  if (!traceback) {
    return null;
  }

  return (
    <details className="mt-4 rounded-2xl border border-red-100 bg-white/70 p-4">
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.14em] text-red-700">
        Traceback
      </summary>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-red-700">
        {traceback}
      </pre>
    </details>
  );
}
