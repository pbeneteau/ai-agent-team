"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Cpu,
  DollarSign,
  GitBranch,
  GitPullRequest,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Trash2,
  TrendingUp,
  Workflow,
} from "lucide-react";

import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { api, type UsageSummary } from "@/lib/api";
import { StructuredOutputFailureSummary } from "./StructuredOutputFailureSummary";
import {
  channelBadgeClass,
  describeFailureImpact,
  formatChannelLabel,
  formatFailureKind,
  formatFlowName,
  formatRelativeTimestamp,
  getSignalSeverity,
  recommendNextAction,
  severityClasses,
  severityLabel,
} from "./usage-utils";

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

function formatCost(usd: number): string {
  if (usd < 0.01) return `$${(usd * 100).toFixed(3)}¢`;
  return `$${usd.toFixed(4)}`;
}

function DailyBarChart({ daily }: { daily: Record<string, { input: number; output: number; cost: number }> }) {
  const entries = Object.entries(daily)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14);

  if (entries.length === 0) {
    return <div className="flex items-center justify-center h-32 text-xs text-slate-400">No historical data</div>;
  }

  const maxCost = Math.max(...entries.map(([, item]) => item.cost), 0.0001);

  return (
    <div className="flex items-end gap-1.5 h-32 pt-2">
      {entries.map(([date, item]) => {
        const heightPct = Math.max((item.cost / maxCost) * 100, 2);
        const tokens = item.input + item.output;
        return (
          <div key={date} className="flex-1 flex flex-col items-center gap-1 group relative">
            <div className="hidden group-hover:block absolute bottom-full mb-1 bg-slate-800 text-white text-[10px] rounded px-2 py-1 whitespace-nowrap z-10">
              {date}
              <br />
              {formatCost(item.cost)} — {formatTokens(tokens)} tokens
            </div>
            <div
              className="w-full rounded-t bg-indigo-500 group-hover:bg-indigo-400 transition-colors"
              style={{ height: `${heightPct}%` }}
            />
            <span className="text-[9px] text-slate-400 rotate-45 origin-left translate-x-1">
              {date.slice(5)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function UsagePage() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const data = await api.getUsage();
      setUsage(data);
      setLastUpdatedAt(new Date().toISOString());
      setError(null);
    } catch {
      setError("Unable to load usage data.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleReset() {
    if (!confirm("Reset all usage counters? This action cannot be undone.")) {
      return;
    }
    setResetting(true);
    try {
      await api.resetUsage();
      await load();
    } catch {
      setError("Error while resetting usage.");
    } finally {
      setResetting(false);
    }
  }

  const structuredFlows = useMemo(() => {
    return Object.entries(usage?.structured_outputs?.by_flow ?? {})
      .map(([flow, stats]) => ({
        flow,
        stats,
        severity: getSignalSeverity(stats),
      }))
      .sort((left, right) => {
        const leftWeight = left.severity === "critical" ? 2 : left.severity === "warning" ? 1 : 0;
        const rightWeight = right.severity === "critical" ? 2 : right.severity === "warning" ? 1 : 0;
        const leftSeen = new Date(left.stats.last_failure?.at ?? left.stats.last_seen_at ?? 0).getTime();
        const rightSeen = new Date(right.stats.last_failure?.at ?? right.stats.last_seen_at ?? 0).getTime();
        return rightWeight - leftWeight || right.stats.failures - left.stats.failures || rightSeen - leftSeen;
      });
  }, [usage]);

  const attentionFlows = structuredFlows.filter((item) => item.severity !== "healthy");
  const primarySignal = attentionFlows[0] ?? structuredFlows[0] ?? null;
  const topModel = useMemo(() => {
    const models = Object.entries(usage?.by_model ?? {});
    if (models.length === 0) {
      return null;
    }
    return models.sort((left, right) => right[1].cost_usd - left[1].cost_usd)[0];
  }, [usage]);
  const mcpSummary = usage?.mcp ?? null;
  const gitProviderSummary = usage?.git_providers ?? null;

  return (
    <WorkspacePageShell
      title="AI Observability"
      description="Monitor costs, structured flows, and reliability signals from real backend and Alex activity."
      meta={
        <>
          <span>Last updated {formatRelativeTimestamp(lastUpdatedAt)}</span>
          {usage?.pricing_note ? <span>{usage.pricing_note}</span> : null}
        </>
      }
      actions={
        <>
          <Button variant="outline" size="sm" onClick={() => load(true)} className="gap-2 rounded-full">
            {refreshing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={resetting}
            className="gap-2 rounded-full text-red-600 hover:text-red-700"
          >
            {resetting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
            Reset
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

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      ) : usage ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <OperatorStatCard
              label="Signals requiring action"
              value={`${attentionFlows.length}`}
              description={attentionFlows.length > 0 ? "Structured flows to inspect" : "No active alerts"}
              icon={<ShieldAlert className="w-4 h-4 text-rose-600" />}
            />
            <OperatorStatCard
              label="Most impacted flow"
              value={primarySignal ? formatFlowName(primarySignal.flow) : "None"}
              description={primarySignal ? severityLabel(primarySignal.severity) : "No observed flow yet"}
              icon={<Workflow className="w-4 h-4 text-amber-600" />}
            />
            <OperatorStatCard
              label="Today burn"
              value={formatCost(usage.today.cost_usd)}
              description={`${formatTokens(usage.today.input_tokens + usage.today.output_tokens)} tokens today`}
              icon={<TrendingUp className="w-4 h-4 text-green-600" />}
            />
            <OperatorStatCard
              label="Structured coverage"
              value={`${structuredFlows.length}`}
              description={topModel ? `Dominant model: ${topModel[0]}` : "No observed model"}
              icon={<Cpu className="w-4 h-4 text-violet-600" />}
            />
          </div>

          {mcpSummary ? (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
              <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
                <CardHeader className="border-b border-black/5 pb-3">
                  <h3 className="font-semibold text-slate-800">MCP health</h3>
                  <p className="text-xs text-slate-500">
                    Health and recent usage for user-managed MCP connections exposed to agents.
                  </p>
                </CardHeader>
                <CardContent className="space-y-3 pt-5">
                  {mcpSummary.connections.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm text-slate-500">
                      No MCP connection configured yet.
                    </div>
                  ) : (
                    mcpSummary.connections.map((connection) => (
                      <div key={connection.id} className="rounded-2xl border border-slate-200 px-4 py-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-900">{connection.name}</p>
                            <p className="mt-1 text-xs text-slate-500">{connection.endpoint_url}</p>
                          </div>
                          <Badge
                            variant="outline"
                            className={
                              connection.status === "healthy"
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                : connection.status === "degraded"
                                  ? "border-amber-200 bg-amber-50 text-amber-700"
                                  : connection.status === "unavailable"
                                    ? "border-rose-200 bg-rose-50 text-rose-700"
                                    : "border-slate-200 bg-slate-100 text-slate-600"
                            }
                          >
                            {connection.status}
                          </Badge>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                          <span>{connection.discovered_tools.length} tool(s)</span>
                          <span>{connection.total_calls} call(s)</span>
                          <span>{connection.total_failures} failure(s)</span>
                          <span>Last test {formatRelativeTimestamp(connection.last_tested_at)}</span>
                        </div>
                        {connection.last_error ? (
                          <p className="mt-3 text-xs leading-5 text-rose-700">{connection.last_error}</p>
                        ) : null}
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
                <CardHeader className="border-b border-black/5 pb-3">
                  <h3 className="font-semibold text-slate-800">MCP summary</h3>
                  <p className="text-xs text-slate-500">Snapshot of backend MCP reliability.</p>
                </CardHeader>
                <CardContent className="grid gap-4 pt-5 sm:grid-cols-2">
                  <OperatorStatCard
                    label="Connections"
                    value={String(mcpSummary.total_connections)}
                    description={`${mcpSummary.healthy_connections} healthy, ${mcpSummary.degraded_connections} degraded`}
                    icon={<Workflow className="w-4 h-4 text-indigo-600" />}
                  />
                  <OperatorStatCard
                    label="Calls"
                    value={String(mcpSummary.total_calls)}
                    description={`${mcpSummary.total_failures} recorded failures`}
                    icon={<DollarSign className="w-4 h-4 text-slate-600" />}
                  />
                </CardContent>
              </Card>
            </div>
          ) : null}

          {gitProviderSummary ? (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
              <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
                <CardHeader className="border-b border-black/5 pb-3">
                  <h3 className="font-semibold text-slate-800">Git provider health</h3>
                  <p className="text-xs text-slate-500">
                    Native GitHub and GitLab connections used by dev agents for repository workflows.
                  </p>
                </CardHeader>
                <CardContent className="space-y-3 pt-5">
                  {gitProviderSummary.connections.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm text-slate-500">
                      No git provider connection configured yet.
                    </div>
                  ) : (
                    gitProviderSummary.connections.map((connection) => (
                      <div key={connection.id} className="rounded-2xl border border-slate-200 px-4 py-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-900">{connection.name}</p>
                            <p className="mt-1 text-xs text-slate-500">
                              {connection.provider} · {connection.base_url}
                            </p>
                          </div>
                          <Badge
                            variant="outline"
                            className={
                              connection.status === "healthy"
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                : connection.status === "degraded"
                                  ? "border-amber-200 bg-amber-50 text-amber-700"
                                  : connection.status === "unavailable"
                                    ? "border-rose-200 bg-rose-50 text-rose-700"
                                    : "border-slate-200 bg-slate-100 text-slate-600"
                            }
                          >
                            {connection.status}
                          </Badge>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                          <span>{connection.discovered_repos.length} repo(s)</span>
                          <span>{connection.total_repo_actions} action(s)</span>
                          <span>{connection.push_actions} push(es)</span>
                          <span>{connection.pull_request_actions} PR/MR</span>
                          <span>Last test {formatRelativeTimestamp(connection.last_tested_at)}</span>
                        </div>
                        {connection.last_error ? (
                          <p className="mt-3 text-xs leading-5 text-rose-700">{connection.last_error}</p>
                        ) : null}
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
                <CardHeader className="border-b border-black/5 pb-3">
                  <h3 className="font-semibold text-slate-800">Git workflow summary</h3>
                  <p className="text-xs text-slate-500">Remote repository actions executed by agents.</p>
                </CardHeader>
                <CardContent className="grid gap-4 pt-5 sm:grid-cols-2">
                  <OperatorStatCard
                    label="Providers"
                    value={String(gitProviderSummary.total_connections)}
                    description={`${gitProviderSummary.healthy_connections} healthy, ${gitProviderSummary.degraded_connections} degraded`}
                    icon={<GitBranch className="w-4 h-4 text-indigo-600" />}
                  />
                  <OperatorStatCard
                    label="Remote actions"
                    value={String(gitProviderSummary.total_repo_actions)}
                    description={`${gitProviderSummary.push_actions} push(es), ${gitProviderSummary.pull_request_actions} PR/MR`}
                    icon={<GitPullRequest className="w-4 h-4 text-emerald-600" />}
                  />
                </CardContent>
              </Card>
            </div>
          ) : null}

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
            <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
              <CardHeader className="border-b border-black/5 pb-3">
                <h3 className="font-semibold text-slate-800">Operator attention</h3>
                <p className="text-xs text-slate-500">
                  Signals that require action or monitoring before digging into raw diagnostics.
                </p>
              </CardHeader>
              <CardContent className="space-y-4 pt-5">
                {attentionFlows.length === 0 ? (
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-5 text-sm text-emerald-900">
                    No critical structured flow. Observed calls remain healthy over the recent period.
                  </div>
                ) : (
                  attentionFlows.slice(0, 4).map(({ flow, stats, severity }) => (
                    <div key={flow} className={`rounded-2xl border px-4 py-4 ${severityClasses(severity)}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold">{formatFlowName(flow)}</p>
                          <p className="mt-1 text-xs opacity-80">
                            Vu {formatRelativeTimestamp(stats.last_failure?.at ?? stats.last_seen_at)}
                          </p>
                        </div>
                        <Badge variant="outline" className={severityClasses(severity)}>
                          {severityLabel(severity)}
                        </Badge>
                      </div>
                      <p className="mt-3 text-sm leading-6 opacity-90">
                        {describeFailureImpact(flow, stats)}
                      </p>
                      <p className="mt-3 text-xs font-medium opacity-90">
                        Next action: {recommendNextAction(flow, stats)}
                      </p>
                      <a href="#technical-diagnostics" className="mt-4 inline-flex items-center gap-1 text-xs font-semibold">
                        Open diagnostics
                        <ArrowRight className="w-3 h-3" />
                      </a>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
              <CardHeader className="border-b border-black/5 pb-3">
                <h3 className="font-semibold text-slate-800">Spend & coverage</h3>
                <p className="text-xs text-slate-500">
                  Quick readout of cost, volume, and model coverage.
                </p>
              </CardHeader>
              <CardContent className="space-y-4 pt-5">
                <div className="rounded-2xl border border-black/5 bg-slate-50/70 p-4">
                  <div className="flex items-start gap-3">
                    <div className="rounded-lg bg-indigo-100 p-2">
                      <DollarSign className="w-4 h-4 text-indigo-600" />
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Total cost</p>
                      <p className="text-2xl font-bold text-slate-900">{formatCost(usage.total.cost_usd)}</p>
                      <p className="text-xs text-slate-400">{usage.total.calls} API calls</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-2xl border border-black/5 bg-slate-50/70 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Dominant model</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{topModel ? topModel[0] : "None"}</p>
                  {topModel ? (
                    <p className="mt-1 text-xs text-slate-500">
                      {formatCost(topModel[1].cost_usd)} pour {formatTokens(topModel[1].input_tokens + topModel[1].output_tokens)} tokens
                    </p>
                  ) : null}
                </div>

                <div className="rounded-2xl border border-black/5 bg-slate-50/70 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Structured flows</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge variant="outline">{structuredFlows.length} flow(s)</Badge>
                    <Badge variant="outline">{attentionFlows.length} with alerts</Badge>
                    <Badge variant="outline">{structuredFlows.filter((item) => item.severity === "healthy").length} healthy</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
            <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
              <CardHeader className="border-b border-black/5 pb-3">
                <h3 className="font-semibold text-slate-800">Breakdown by model</h3>
              </CardHeader>
              <CardContent className="pt-5">
                {Object.keys(usage.by_model).length === 0 ? (
                  <p className="text-sm text-slate-400">No call recorded.</p>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(usage.by_model).map(([model, stats]) => {
                      const totalTokens = stats.input_tokens + stats.output_tokens;
                      const grandTotal = usage.total.input_tokens + usage.total.output_tokens || 1;
                      const pct = Math.round((totalTokens / grandTotal) * 100);
                      const isSonnet = model.includes("sonnet");

                      return (
                        <div key={model} className="space-y-1.5">
                          <div className="flex items-center justify-between gap-4">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className={`h-2 w-2 rounded-full ${isSonnet ? "bg-blue-500" : "bg-purple-500"}`} />
                              <span className="truncate text-sm font-medium text-slate-700">{model}</span>
                            </div>
                            <div className="flex items-center gap-4 text-xs text-slate-500">
                              <span>{formatTokens(stats.input_tokens)} in</span>
                              <span>{formatTokens(stats.output_tokens)} out</span>
                              <span className="font-semibold text-slate-700">{formatCost(stats.cost_usd)}</span>
                            </div>
                          </div>
                          <div className="h-1.5 w-full rounded-full bg-slate-100">
                            <div
                              className={`h-1.5 rounded-full ${isSonnet ? "bg-blue-400" : "bg-purple-400"}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
              <CardHeader className="border-b border-black/5 pb-3">
                <h3 className="font-semibold text-slate-800">History (last 14 days)</h3>
                <p className="text-xs text-slate-500">Hover over the bars to view details</p>
              </CardHeader>
              <CardContent className="pt-5">
                <DailyBarChart daily={usage.daily} />
              </CardContent>
            </Card>
          </div>

          <Card id="technical-diagnostics" className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
            <CardHeader className="border-b border-black/5 pb-3">
              <h3 className="font-semibold text-slate-800">Technical diagnostics</h3>
              <p className="text-xs text-slate-500">
                Actual channel used per backend flow, failure volume, and latest observed signal.
              </p>
            </CardHeader>
            <CardContent className="pt-5">
              {Object.keys(usage.structured_outputs?.by_flow ?? {}).length === 0 ? (
                <p className="text-sm text-slate-400">No structured flow observed yet.</p>
              ) : (
                <div className="space-y-4">
                  {Object.entries(usage.structured_outputs?.by_flow ?? {}).map(([flow, stats]) => (
                    <div key={flow} className="rounded-2xl border border-slate-100 bg-slate-50/70 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold capitalize text-slate-900">{formatFlowName(flow)}</p>
                            <Badge variant="outline" className={severityClasses(getSignalSeverity(stats))}>
                              {severityLabel(getSignalSeverity(stats))}
                            </Badge>
                          </div>
                          <p className="mt-1 text-xs text-slate-500">
                            {stats.calls} call{stats.calls > 1 ? "s" : ""} · {stats.successes} success{stats.successes > 1 ? "es" : ""} · {stats.failures} failure{stats.failures > 1 ? "s" : ""}
                          </p>
                        </div>
                        {stats.last_seen_at ? (
                          <span className="text-[11px] text-slate-400">
                            Seen {new Date(stats.last_seen_at).toLocaleString("en-US")}
                          </span>
                        ) : null}
                      </div>

                      <div className="mt-3 flex flex-wrap gap-2">
                        {Object.entries(stats.channels).map(([channel, count]) => (
                          <Badge key={`${flow}-${channel}`} variant="outline" className={channelBadgeClass(channel)}>
                            {formatChannelLabel(channel)} · {count}
                          </Badge>
                        ))}
                      </div>

                      {Object.keys(stats.failures_by_kind ?? {}).length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {Object.entries(stats.failures_by_kind ?? {}).map(([kind, count]) => (
                            <Badge
                              key={`${flow}-failure-${kind}`}
                              variant="outline"
                              className="border-rose-200 bg-rose-50 text-rose-800"
                            >
                              {formatFailureKind(kind)} · {count}
                            </Badge>
                          ))}
                        </div>
                      ) : null}

                      {stats.last_request_name ? (
                        <p className="mt-3 text-[11px] text-slate-500">
                          Latest request: <span className="font-mono text-slate-700">{stats.last_request_name}</span>
                        </p>
                      ) : null}

                      <StructuredOutputFailureSummary flow={flow} failure={stats.last_failure} />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </WorkspacePageShell>
  );
}

function OperatorStatCard({
  label,
  value,
  description,
  icon,
}: {
  label: string;
  value: string;
  description: string;
  icon: ReactNode;
}) {
  return (
    <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.16)] ring-0">
      <CardContent className="pt-5 pb-4">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-slate-100 p-2">{icon}</div>
          <div>
            <p className="mb-0.5 text-xs text-slate-500">{label}</p>
            <p className="text-2xl font-bold text-slate-900">{value}</p>
            <p className="text-xs text-slate-400">{description}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
