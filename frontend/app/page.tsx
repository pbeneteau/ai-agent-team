"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Loader2,
  Radar,
  RefreshCw,
  TriangleAlert,
  Users,
  Workflow,
} from "lucide-react";

import { buildAlexWorkspaceHref } from "@/components/chat/chat-shell";
import { AgentCard } from "@/components/agents/AgentCard";
import { EmptyState } from "@/components/layout/EmptyState";
import { SectionPanel } from "@/components/layout/SectionPanel";
import { StatBlock } from "@/components/layout/StatBlock";
import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { TaskCard } from "@/components/tasks/TaskCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatRelativeTimestamp } from "@/lib/config/formatting";
import {
  DASHBOARD_RECENT_TASKS_LIMIT,
  DASHBOARD_VISIBLE_AGENTS_LIMIT,
} from "@/lib/config/ui-limits";
import {
  api,
  type Agent,
  type GlobalKnowledgeReadiness,
  type ProjectContextState,
  type Task,
  type Team,
  type UsageSummary,
} from "@/lib/api";
import { useWsEvent } from "@/lib/ws-context";

type AttentionTone = "slate" | "amber" | "rose" | "emerald" | "indigo";

interface AttentionItem {
  title: string;
  description: string;
  href: string;
  cta: string;
  tone: AttentionTone;
}

function humanizeFlowName(flow: string): string {
  return flow.replace(/[:_]/g, " ");
}

function toneClasses(tone: AttentionTone): string {
  switch (tone) {
    case "amber":
      return "border-amber-200 bg-amber-50 text-amber-900";
    case "rose":
      return "border-rose-200 bg-rose-50 text-rose-900";
    case "emerald":
      return "border-emerald-200 bg-emerald-50 text-emerald-900";
    case "indigo":
      return "border-indigo-200 bg-indigo-50 text-indigo-900";
    default:
      return "border-slate-200 bg-slate-50 text-slate-900";
  }
}

function StatLinkCard({
  href,
  label,
  value,
  description,
  icon,
}: {
  href: string;
  label: string;
  value: string;
  description: string;
  icon: React.ReactNode;
}) {
  return (
    <Link href={href}>
      <StatBlock
        label={label}
        value={value}
        description={description}
        icon={icon}
        className="h-full transition-transform hover:-translate-y-0.5 hover:border-[var(--ops-border-strong)]"
      />
    </Link>
  );
}

function LoadingSurface({ className = "h-36" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-3xl border border-black/5 bg-white/90 ${className}`}>
      <div className="space-y-3 p-5">
        <div className="h-3 w-28 rounded-full bg-slate-200" />
        <div className="h-8 w-3/4 rounded-full bg-slate-200" />
        <div className="h-3 w-full rounded-full bg-slate-200" />
        <div className="h-3 w-4/5 rounded-full bg-slate-200" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [teams, setTeams] = useState<Team[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [knowledgeReadiness, setKnowledgeReadiness] = useState<GlobalKnowledgeReadiness | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [projectContextState, setProjectContextState] = useState<ProjectContextState | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const [nextTeams, nextTasks, nextAgents, nextReadiness, nextUsage, nextProjectContext] =
        await Promise.all([
          api.getTeams(),
          api.getTasks(),
          api.getAgents(),
          api.getKnowledgeReadiness().catch(() => null),
          api.getUsage().catch(() => null),
          api.getProjectContext().catch(() => null),
        ]);
      setTeams(nextTeams);
      setTasks(
        nextTasks.slice().sort(
          (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
        ),
      );
      setAgents(nextAgents);
      setKnowledgeReadiness(nextReadiness);
      setUsage(nextUsage);
      setProjectContextState(nextProjectContext);
      setLastUpdatedAt(new Date().toISOString());
      setError(null);
    } catch (err) {
      console.error("[Dashboard] Failed to load data:", err);
      setError("Unable to load the operations center. Check that the backend is running.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useWsEvent(
    (msg) => {
      if (
        msg.type === "agent_status" ||
        msg.type === "task_update" ||
        msg.type === "task_created" ||
        msg.type === "task_deleted" ||
        msg.type === "team_created" ||
        msg.type === "briefing_complete" ||
        msg.type === "research_complete"
      ) {
        load(true);
      }
    },
    [load],
  );

  const readyAgents = agents.filter(
    (agent) => agent.role !== "associate" && agent.status === "ready" && agent.occupancy_status === "idle",
  );
  const busyAgents = agents.filter((agent) => agent.role !== "associate" && agent.occupancy_status === "busy");
  const runningTasks = tasks.filter((task) => task.status === "running");
  const blockedOrFailedTasks = tasks.filter(
    (task) => task.status === "failed" || task.execution_eligibility !== "eligible",
  );
  const recentTasks = tasks.slice(0, DASHBOARD_RECENT_TASKS_LIMIT);
  const visibleAgents = readyAgents.slice(0, DASHBOARD_VISIBLE_AGENTS_LIMIT);
  const agentsMissingContext = (knowledgeReadiness?.agents ?? []).filter(
    (agent) => agent.readiness_level !== "sufficient",
  );
  const latestStructuredSignal = useMemo(() => {
    const entries = Object.entries(usage?.structured_outputs?.by_flow ?? {});
    if (entries.length === 0) {
      return null;
    }
    return entries
      .map(([flow, stats]) => ({
        flow,
        stats,
        timestamp: new Date(stats.last_failure?.at ?? stats.last_seen_at ?? 0).getTime(),
      }))
      .sort((left, right) => {
        const leftHasFailures = left.stats.failures > 0 ? 1 : 0;
        const rightHasFailures = right.stats.failures > 0 ? 1 : 0;
        return rightHasFailures - leftHasFailures || right.timestamp - left.timestamp;
      })[0];
  }, [usage]);

  const attentionItems = useMemo<AttentionItem[]>(() => {
    const items: AttentionItem[] = [];
    if (teams.length === 0) {
      items.push({
        title: "Compose the first team",
        description: "No operational agent exists yet. Start by scoping the structure with Alex.",
        href: buildAlexWorkspaceHref({ mode: "design-team" }),
        cta: "Open Design Team",
        tone: "indigo",
      });
    }
    if (!projectContextState?.published) {
      items.push({
        title: "Publish the reference brief",
        description: "The published brief should become the source of truth before accelerating tasks and learning.",
        href: "/project-context?section=brief",
        cta: "Open Context",
        tone: "amber",
      });
    }
    if (blockedOrFailedTasks.length > 0) {
      const task = blockedOrFailedTasks[0];
      items.push({
        title: blockedOrFailedTasks.length > 1 ? `${blockedOrFailedTasks.length} tasks to unblock` : task.title,
        description:
          task.execution_blockers[0] ??
          (task.status === "failed"
            ? "An execution failed and needs a decision or retry."
            : "A task is waiting for clarification before execution."),
        href: "/tasks",
        cta: "View tasks",
        tone: "rose",
      });
    }
    if (agentsMissingContext.length > 0) {
      const agent = agentsMissingContext[0];
      items.push({
        title:
          agentsMissingContext.length > 1
            ? `${agentsMissingContext.length} agents need context`
            : `${agent.agent_name} lacks context`,
        description: agent.summary,
        href: "/project-context?section=readiness",
        cta: "Address the context",
        tone: "amber",
      });
    }
    if (latestStructuredSignal && latestStructuredSignal.stats.failures > 0) {
      items.push({
        title: `Observability signal on ${humanizeFlowName(latestStructuredSignal.flow)}`,
        description:
          latestStructuredSignal.stats.last_failure?.message ??
          `${latestStructuredSignal.stats.failures} structured failure(s) observed on this flow.`,
        href: "/usage?section=reliability",
        cta: "Open Reliability",
        tone: "slate",
      });
    }
    if (items.length === 0) {
      items.push({
        title: "Prepare the next task",
        description: runningTasks.length > 0
          ? "The current execution is healthy. Use the time to scope what comes next with Alex."
          : "The system is ready. This is a good time to scope the next execution.",
        href: "/chat",
        cta: "Open Alex",
        tone: "emerald",
      });
    }
    return items;
  }, [agentsMissingContext, blockedOrFailedTasks, latestStructuredSignal, projectContextState?.published, runningTasks.length, teams.length]);

  const recommendedAction = attentionItems[0];

  return (
    <WorkspacePageShell
      archetype="command-center"
      headerMode="compact"
      title="Command Center"
      description="Run the product from one clear operational view."
      meta={
        <>
          <span>Last updated {formatRelativeTimestamp(lastUpdatedAt)}</span>
          <span>Real-time refresh via websocket</span>
        </>
      }
      actions={
        <Button variant="outline" className="gap-2 rounded-full" onClick={() => load(true)}>
          {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Refresh
        </Button>
      }
    >
      {error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      ) : null}

      {loading ? (
        <>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)]">
            <LoadingSurface className="h-[260px]" />
            <LoadingSurface className="h-[260px]" />
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, index) => (
              <LoadingSurface key={index} className="h-32" />
            ))}
          </div>
          <div className="grid gap-4 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <LoadingSurface key={index} className="h-[250px]" />
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)]">
            <SectionPanel
              eyebrow="Priority queue"
              title="Needs attention now"
              description="The items that change trajectory or unblock execution."
            >
              <div className="space-y-3">
                {attentionItems.map((item) => (
                  <Link
                    key={`${item.title}-${item.href}`}
                    href={item.href}
                    className={`block rounded-[22px] border px-4 py-4 transition-transform hover:-translate-y-0.5 ${toneClasses(item.tone)}`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-2">
                        <p className="text-sm font-semibold">{item.title}</p>
                        <p className="text-sm leading-6 opacity-90">{item.description}</p>
                      </div>
                      <ArrowRight className="mt-0.5 size-4 shrink-0 opacity-70" />
                    </div>
                    <p className="mt-3 text-xs font-medium opacity-80">{item.cta}</p>
                  </Link>
                ))}
              </div>
            </SectionPanel>

            <SectionPanel
              eyebrow="Operator move"
              title="Recommended next action"
              description="The best immediate lever based on the current system state."
            >
              <div className="space-y-4">
                <div className={`rounded-3xl border px-5 py-5 ${toneClasses(recommendedAction.tone)}`}>
                  <p className="text-sm font-semibold">{recommendedAction.title}</p>
                  <p className="mt-3 text-sm leading-6 opacity-90">{recommendedAction.description}</p>
                  <div className="mt-5 flex flex-wrap gap-2">
                    <Link href={recommendedAction.href}>
                      <Button className="rounded-full gap-2">
                        {recommendedAction.cta}
                        <ArrowRight className="size-4" />
                      </Button>
                    </Link>
                    <Link href="/chat">
                      <Button variant="outline" className="rounded-full gap-2">
                        <Bot className="size-4" />
                        Open Alex
                      </Button>
                    </Link>
                  </div>
                </div>

                <div className="rounded-[22px] border border-[var(--ops-border)] bg-[color:rgba(255,255,251,0.68)] px-4 py-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                    What the system says
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge variant="outline">
                      {teams.length} team{teams.length > 1 ? "s" : ""}
                    </Badge>
                    <Badge variant="outline">
                      {runningTasks.length} running task{runningTasks.length > 1 ? "s" : ""}
                    </Badge>
                    <Badge variant="outline">
                      {readyAgents.length} agent{readyAgents.length > 1 ? "s" : ""} available
                    </Badge>
                    <Badge variant="outline">
                      {agentsMissingContext.length} agent{agentsMissingContext.length > 1 ? "s" : ""} needing context
                    </Badge>
                  </div>
                </div>
              </div>
            </SectionPanel>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <StatLinkCard
              href="/team?section=teams"
              label="Teams"
              value={`${teams.length}`}
              description="Structure active"
              icon={<Users className="size-5 text-indigo-600" />}
            />
            <StatLinkCard
              href="/team?section=agents"
              label="Ready agents"
              value={`${readyAgents.length}`}
              description="Available to start"
              icon={<Bot className="size-5 text-violet-600" />}
            />
            <StatLinkCard
              href="/team?section=agents"
              label="Busy agents"
              value={`${busyAgents.length}`}
              description="Already engaged"
              icon={<Workflow className="size-5 text-sky-600" />}
            />
            <StatLinkCard
              href="/tasks?view=running"
              label="Running tasks"
              value={`${runningTasks.length}`}
              description="Worth watching"
              icon={<Loader2 className="size-5 text-blue-600" />}
            />
            <StatLinkCard
              href="/tasks?view=blocked"
              label="Needs decision"
              value={`${blockedOrFailedTasks.length}`}
              description="Blocked or failed"
              icon={<TriangleAlert className="size-5 text-rose-600" />}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <SectionPanel
              title="Blocked or failed tasks"
              description="Tasks waiting for a decision, clarification, or retry."
              tone="subtle"
            >
              <div className="space-y-3">
                {blockedOrFailedTasks.length === 0 ? (
                  <EmptyState description="No critical task needs unblocking right now." />
                ) : (
                  blockedOrFailedTasks.slice(0, 3).map((task) => (
                    <Link
                      key={task.id}
                      href={`/tasks/${task.id}`}
                      className="block rounded-2xl border border-black/5 bg-slate-50/80 px-4 py-4 transition-colors hover:border-primary/20 hover:bg-primary/5"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-1">
                          <p className="text-sm font-semibold text-slate-900">{task.title}</p>
                          <p className="text-xs text-slate-500">
                            {task.status === "failed" ? "Failed" : "Clarification required"}
                          </p>
                        </div>
                        <ArrowRight className="size-4 shrink-0 text-slate-400" />
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-600">
                        {task.execution_blockers[0] ?? task.error ?? "Open the detail view to resume execution."}
                      </p>
                    </Link>
                  ))
                )}
              </div>
            </SectionPanel>

            <SectionPanel
              title="Agents missing context"
              description="Agents that would immediately become more reliable with more context."
              tone="subtle"
            >
              <div className="space-y-3">
                {agentsMissingContext.length === 0 ? (
                  <EmptyState description="No critical agent context gap detected." />
                ) : (
                  agentsMissingContext.slice(0, 3).map((agent) => (
                    <Link
                      key={agent.agent_id}
                      href="/project-context?section=readiness"
                      className="block rounded-2xl border border-black/5 bg-slate-50/80 px-4 py-4 transition-colors hover:border-primary/20 hover:bg-primary/5"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-1">
                          <p className="text-sm font-semibold text-slate-900">{agent.agent_name}</p>
                          <p className="text-xs text-slate-500">{agent.agent_title}</p>
                        </div>
                        <Badge
                          variant="outline"
                          className={
                            agent.readiness_level === "insufficient"
                              ? "border-rose-200 bg-rose-50 text-rose-800"
                              : "border-amber-200 bg-amber-50 text-amber-800"
                          }
                        >
                          {agent.readiness_score}/100
                        </Badge>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-600">{agent.summary}</p>
                    </Link>
                  ))
                )}
              </div>
            </SectionPanel>

            <SectionPanel
              title="Latest observability signal"
              description="The latest useful signal surfaced by structured outputs and runtime diagnostics."
              tone="subtle"
            >
              <div className="space-y-3">
                {latestStructuredSignal ? (
                  <Link
                    href="/usage?section=reliability"
                    className="block rounded-2xl border border-black/5 bg-slate-50/80 px-4 py-4 transition-colors hover:border-primary/20 hover:bg-primary/5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <p className="text-sm font-semibold text-slate-900">
                          {humanizeFlowName(latestStructuredSignal.flow)}
                        </p>
                        <p className="text-xs text-slate-500">
                          Vu {formatRelativeTimestamp(latestStructuredSignal.stats.last_failure?.at ?? latestStructuredSignal.stats.last_seen_at)}
                        </p>
                      </div>
                      <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                        <Radar className="size-4" />
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Badge variant="outline">
                        {latestStructuredSignal.stats.calls} call{latestStructuredSignal.stats.calls > 1 ? "s" : ""}
                      </Badge>
                      <Badge variant="outline">
                        {latestStructuredSignal.stats.failures} failure{latestStructuredSignal.stats.failures > 1 ? "s" : ""}
                      </Badge>
                      <Badge variant="outline">
                        {Object.keys(latestStructuredSignal.stats.channels).length} channel{Object.keys(latestStructuredSignal.stats.channels).length > 1 ? "s" : ""}
                      </Badge>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-600">
                      {latestStructuredSignal.stats.last_failure?.message ??
                        "No recent failure on this flow. Open Reliability for technical detail."}
                    </p>
                  </Link>
                ) : (
                  <EmptyState description="No structured signal available right now." />
                )}
              </div>
            </SectionPanel>
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <div>
              <SectionPanel
                title="Recent executions"
                description="The latest executed tasks, to keep a quick read on the workflow."
                actions={
                  <Link href="/tasks?view=all" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
                    View all <ArrowRight className="w-3 h-3" />
                  </Link>
                }
              >
                {recentTasks.length === 0 ? (
                  <EmptyState description="No recent execution. Use Alex to scope the next task." />
                ) : (
                  <div className="space-y-3">
                    {recentTasks.map((task) => (
                      <TaskCard key={task.id} task={task} />
                    ))}
                  </div>
                )}
              </SectionPanel>
            </div>

            <div>
              <SectionPanel
                title="Ready to work"
                description="Agents immediately available for the next execution."
                actions={
                  <Link href="/team?section=agents" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
                    View all <ArrowRight className="w-3 h-3" />
                  </Link>
                }
              >
                {visibleAgents.length === 0 ? (
                  <EmptyState
                    title="No agent is immediately available."
                    description="Check capacity or enrich the context before the next launch."
                    action={
                      <div className="flex flex-wrap gap-2">
                        <Link href="/team?section=teams">
                          <Button variant="outline" className="rounded-full gap-2">
                            <Users className="size-4" />
                            Open Organization
                          </Button>
                        </Link>
                        <Link href="/project-context?section=readiness">
                          <Button variant="outline" className="rounded-full gap-2">
                            <CheckCircle2 className="size-4" />
                            Address the context
                          </Button>
                        </Link>
                      </div>
                    }
                  />
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {visibleAgents.map((agent) => (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        onOpen={(selectedAgent) => router.push(`/team/agents/${selectedAgent.id}`)}
                      />
                    ))}
                  </div>
                )}
              </SectionPanel>
            </div>
          </div>
        </>
      )}
    </WorkspacePageShell>
  );
}
