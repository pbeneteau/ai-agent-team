"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ClipboardList,
  Loader2,
  Radar,
  RefreshCw,
  TriangleAlert,
  Users,
  Workflow,
} from "lucide-react";

import { AgentCard } from "@/components/agents/AgentCard";
import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { TaskCard } from "@/components/tasks/TaskCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
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
      <Card className="h-full border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0 transition-transform hover:-translate-y-0.5 hover:border-black/8">
        <CardContent className="flex h-full items-start justify-between gap-4 p-4">
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {label}
            </p>
            <p className="text-2xl font-semibold tracking-tight text-slate-950">{value}</p>
            <p className="text-xs leading-5 text-slate-500">{description}</p>
          </div>
          <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-slate-50 text-slate-700">
            {icon}
          </div>
        </CardContent>
      </Card>
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
        href: "/team-builder",
        cta: "Open Alex team design",
        tone: "indigo",
      });
    }
    if (!projectContextState?.published) {
      items.push({
        title: "Publish the reference brief",
        description: "The published brief should become the source of truth before accelerating tasks and learning.",
        href: "/project-context",
        cta: "Open Brief & Documents",
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
        href: "/project-context",
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
        href: "/usage",
        cta: "Inspect AI Observability",
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
      title="Operations"
      description="See what needs action now, what is blocked, and what decision comes next."
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
            <Card className="border-black/5 bg-white/92 shadow-[0_22px_48px_-34px_rgba(15,23,42,0.2)] ring-0">
              <CardHeader className="border-b border-black/5 pb-4">
                <div className="flex items-center gap-3">
                  <div className="flex size-11 items-center justify-center rounded-2xl bg-amber-50 text-amber-700">
                    <TriangleAlert className="size-5" />
                  </div>
                  <div>
                    <p className="text-base font-semibold text-slate-950">Needs attention now</p>
                    <p className="mt-1 text-sm text-slate-500">
                      The items that change product trajectory or unblock execution.
                    </p>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 pt-5">
                {attentionItems.map((item) => (
                  <Link
                    key={`${item.title}-${item.href}`}
                    href={item.href}
                    className={`block rounded-2xl border px-4 py-4 transition-transform hover:-translate-y-0.5 ${toneClasses(item.tone)}`}
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
              </CardContent>
            </Card>

            <Card className="border-black/5 bg-white/92 shadow-[0_22px_48px_-34px_rgba(15,23,42,0.2)] ring-0">
              <CardHeader className="border-b border-black/5 pb-4">
                <div className="flex items-center gap-3">
                  <div className="flex size-11 items-center justify-center rounded-2xl bg-primary/8 text-primary">
                    <ClipboardList className="size-5" />
                  </div>
                  <div>
                    <p className="text-base font-semibold text-slate-950">Recommended next action</p>
                    <p className="mt-1 text-sm text-slate-500">
                      The best immediate lever based on the state of the brief, tasks, and agents.
                    </p>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 pt-5">
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

                <div className="rounded-2xl border border-black/5 bg-slate-50/70 px-4 py-4">
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
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <StatLinkCard
              href="/team"
              label="Teams"
              value={`${teams.length}`}
              description="Structure active"
              icon={<Users className="size-5 text-indigo-600" />}
            />
            <StatLinkCard
              href="/team"
              label="Ready agents"
              value={`${readyAgents.length}`}
              description="Available to start"
              icon={<Bot className="size-5 text-violet-600" />}
            />
            <StatLinkCard
              href="/team"
              label="Busy agents"
              value={`${busyAgents.length}`}
              description="Already engaged"
              icon={<Workflow className="size-5 text-sky-600" />}
            />
            <StatLinkCard
              href="/tasks"
              label="Running tasks"
              value={`${runningTasks.length}`}
              description="Worth watching"
              icon={<Loader2 className="size-5 text-blue-600" />}
            />
            <StatLinkCard
              href="/tasks"
              label="Needs decision"
              value={`${blockedOrFailedTasks.length}`}
              description="Blocked or failed"
              icon={<TriangleAlert className="size-5 text-rose-600" />}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
              <CardHeader className="border-b border-black/5 pb-3">
                <p className="text-base font-semibold text-slate-950">Blocked or failed tasks</p>
                <p className="text-sm text-slate-500">Tasks waiting for a decision, clarification, or retry.</p>
              </CardHeader>
              <CardContent className="space-y-3 pt-5">
                {blockedOrFailedTasks.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-black/8 bg-slate-50/60 px-4 py-5 text-sm text-slate-500">
                    No critical task needs unblocking right now.
                  </div>
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
              </CardContent>
            </Card>

            <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
              <CardHeader className="border-b border-black/5 pb-3">
                <p className="text-base font-semibold text-slate-950">Agents missing context</p>
                <p className="text-sm text-slate-500">Agents that would immediately become more reliable with more context.</p>
              </CardHeader>
              <CardContent className="space-y-3 pt-5">
                {agentsMissingContext.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-black/8 bg-slate-50/60 px-4 py-5 text-sm text-slate-500">
                    No critical agent context gap detected.
                  </div>
                ) : (
                  agentsMissingContext.slice(0, 3).map((agent) => (
                    <Link
                      key={agent.agent_id}
                      href="/project-context"
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
              </CardContent>
            </Card>

            <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
              <CardHeader className="border-b border-black/5 pb-3">
                <p className="text-base font-semibold text-slate-950">Latest observability signal</p>
                <p className="text-sm text-slate-500">The latest useful signal surfaced by structured outputs and runtime diagnostics.</p>
              </CardHeader>
              <CardContent className="space-y-3 pt-5">
                {latestStructuredSignal ? (
                  <Link
                    href="/usage"
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
                        "No recent failure on this flow. Open AI Observability for technical detail."}
                    </p>
                  </Link>
                ) : (
                  <div className="rounded-2xl border border-dashed border-black/8 bg-slate-50/60 px-4 py-5 text-sm text-slate-500">
                    No structured signal available right now.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <div>
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="font-semibold text-slate-900">Recent executions</h2>
                  <p className="mt-1 text-sm text-slate-500">The latest executed tasks, to keep a quick read on the workflow.</p>
                </div>
                <Link href="/tasks" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
                  View all <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {recentTasks.length === 0 ? (
                <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.12)] ring-0">
                  <CardContent className="p-8 text-center text-slate-500 text-sm">
                    No recent execution. Use Alex to scope the next task.
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-3">
                  {recentTasks.map((task) => (
                    <TaskCard key={task.id} task={task} />
                  ))}
                </div>
              )}
            </div>

            <div>
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="font-semibold text-slate-900">Ready to work</h2>
                  <p className="mt-1 text-sm text-slate-500">Agents immediately available for the next execution.</p>
                </div>
                <Link href="/team" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
                  View all <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {visibleAgents.length === 0 ? (
                <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.12)] ring-0">
                  <CardContent className="space-y-3 p-8 text-center text-sm text-slate-500">
                    <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-600">
                      <BrainCircuit className="size-5" />
                    </div>
                    <p>No agent is immediately available. Check capacity or enrich the context before the next launch.</p>
                    <div className="flex justify-center gap-2">
                      <Link href="/team">
                        <Button variant="outline" className="rounded-full gap-2">
                          <Users className="size-4" />
                          View Teams & Agents
                        </Button>
                      </Link>
                      <Link href="/project-context">
                        <Button variant="outline" className="rounded-full gap-2">
                          <CheckCircle2 className="size-4" />
                          Address the context
                        </Button>
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <div className="grid gap-3 md:grid-cols-2">
                  {visibleAgents.map((agent) => (
                    <AgentCard key={agent.id} agent={agent} onOpen={(selectedAgent) => router.push(`/team/agents/${selectedAgent.id}`)} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </WorkspacePageShell>
  );
}
