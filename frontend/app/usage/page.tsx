"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Cable,
  Cpu,
  DollarSign,
  Loader2,
  RefreshCw,
  ShieldAlert,
  TrendingUp,
  Workflow,
} from "lucide-react";

import { DomainSecondaryNav } from "@/components/layout/DomainSecondaryNav";
import { EmptyState } from "@/components/layout/EmptyState";
import { SectionPanel } from "@/components/layout/SectionPanel";
import { StatBlock } from "@/components/layout/StatBlock";
import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

type ObservabilitySection = "overview" | "reliability" | "costs";
type StructuredFlowStats = NonNullable<UsageSummary["structured_outputs"]>["by_flow"][string];
type StructuredFlowEntry = {
  flow: string;
  stats: StructuredFlowStats;
  severity: "critical" | "warning" | "healthy";
};

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

function formatCost(usd: number): string {
  if (usd < 0.01) return `$${(usd * 100).toFixed(3)}¢`;
  return `$${usd.toFixed(4)}`;
}

function normalizeSection(value: string | null): ObservabilitySection {
  switch (value) {
    case "reliability":
    case "costs":
    case "overview":
      return value;
    default:
      return "overview";
  }
}

function DailyBarChart({ daily }: { daily: Record<string, { input: number; output: number; cost: number }> }) {
  const entries = Object.entries(daily)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14);

  if (entries.length === 0) {
    return <div className="flex h-32 items-center justify-center text-xs text-slate-400">No historical data</div>;
  }

  const maxCost = Math.max(...entries.map(([, item]) => item.cost), 0.0001);

  return (
    <div className="flex h-32 items-end gap-1.5 pt-2">
      {entries.map(([date, item]) => {
        const heightPct = Math.max((item.cost / maxCost) * 100, 2);
        const tokens = item.input + item.output;
        return (
          <div key={date} className="group relative flex flex-1 flex-col items-center gap-1">
            <div className="absolute bottom-full z-10 mb-1 hidden whitespace-nowrap rounded bg-slate-800 px-2 py-1 text-[10px] text-white group-hover:block">
              {date}
              <br />
              {formatCost(item.cost)} - {formatTokens(tokens)} tokens
            </div>
            <div
              className="w-full rounded-t bg-indigo-500 transition-colors group-hover:bg-indigo-400"
              style={{ height: `${heightPct}%` }}
            />
            <span className="origin-left translate-x-1 rotate-45 text-[9px] text-slate-400">
              {date.slice(5)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function UsagePage() {
  return (
    <Suspense fallback={<div className="h-full min-h-0 bg-[var(--ops-canvas)]" />}>
      <UsagePageContent />
    </Suspense>
  );
}

function UsagePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
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

  useEffect(() => {
    if (searchParams.get("section") === "infrastructure") {
      router.replace("/connections");
    }
  }, [router, searchParams]);

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

  const activeSection = normalizeSection(searchParams.get("section"));
  const structuredFlows = useMemo<StructuredFlowEntry[]>(() => {
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
  const healthyFlows = structuredFlows.filter((item) => item.severity === "healthy");
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
  const totalInfrastructureConnections =
    (mcpSummary?.total_connections ?? 0) + (gitProviderSummary?.total_connections ?? 0);
  const healthyInfrastructureConnections =
    (mcpSummary?.healthy_connections ?? 0) + (gitProviderSummary?.healthy_connections ?? 0);
  const degradedInfrastructureConnections =
    (mcpSummary?.degraded_connections ?? 0) +
    (gitProviderSummary?.degraded_connections ?? 0) +
    (mcpSummary?.unavailable_connections ?? 0) +
    (gitProviderSummary?.unavailable_connections ?? 0);
  const totalFailures = structuredFlows.reduce((sum, item) => sum + item.stats.failures, 0);
  const totalCalls = structuredFlows.reduce((sum, item) => sum + item.stats.calls, 0);
  const uniqueChannelCount = new Set(
    structuredFlows.flatMap((item) => Object.keys(item.stats.channels)),
  ).size;

  return (
    <WorkspacePageShell
      title="Observability"
      description="Track system health, reliability, costs, and infrastructure signals coming from real backend and Alex activity."
      meta={
        <>
          <span>Last updated {formatRelativeTimestamp(lastUpdatedAt)}</span>
          {usage?.pricing_note ? <span>{usage.pricing_note}</span> : null}
        </>
      }
      actions={
        <>
          <Button variant="outline" size="sm" onClick={() => load(true)} className="gap-2 rounded-full">
            {refreshing ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
            Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={resetting}
            className="gap-2 rounded-full text-red-600 hover:text-red-700"
          >
            {resetting ? <Loader2 className="size-3.5 animate-spin" /> : <AlertTriangle className="size-3.5" />}
            Reset
          </Button>
        </>
      }
    >
      {error ? (
        <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="size-4 shrink-0" />
          {error}
        </div>
      ) : null}

      <DomainSecondaryNav domain="observability" />

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="size-6 animate-spin text-slate-400" />
        </div>
      ) : usage ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <StatBlock
              label="Signals requiring action"
              value={attentionFlows.length}
              description={attentionFlows.length > 0 ? "Flows to inspect" : "No active alert"}
              tone={attentionFlows.length > 0 ? "warning" : "positive"}
              icon={<ShieldAlert className="size-4" />}
            />
            <StatBlock
              label="Primary signal"
              value={primarySignal ? formatFlowName(primarySignal.flow) : "None"}
              description={primarySignal ? severityLabel(primarySignal.severity) : "No observed flow yet"}
              tone={primarySignal?.severity === "critical" ? "danger" : primarySignal?.severity === "warning" ? "warning" : "default"}
              icon={<Workflow className="size-4" />}
            />
            <StatBlock
              label="Today burn"
              value={formatCost(usage.today.cost_usd)}
              description={`${formatTokens(usage.today.input_tokens + usage.today.output_tokens)} tokens today`}
              tone="accent"
              icon={<TrendingUp className="size-4" />}
            />
            <StatBlock
              label="Infrastructure"
              value={healthyInfrastructureConnections}
              description={`${totalInfrastructureConnections} configured connection(s)`}
              tone={degradedInfrastructureConnections > 0 ? "warning" : "positive"}
              icon={<Cable className="size-4" />}
            />
          </div>

          {activeSection === "overview" ? (
            <ObservabilityOverview
              usage={usage}
              structuredFlows={structuredFlows}
              attentionFlows={attentionFlows}
              primarySignal={primarySignal}
              topModel={topModel}
              totalInfrastructureConnections={totalInfrastructureConnections}
              healthyInfrastructureConnections={healthyInfrastructureConnections}
              degradedInfrastructureConnections={degradedInfrastructureConnections}
            />
          ) : null}

          {activeSection === "reliability" ? (
            <ObservabilityReliability
              structuredFlows={structuredFlows}
              attentionFlows={attentionFlows}
              healthyFlows={healthyFlows}
              totalCalls={totalCalls}
              totalFailures={totalFailures}
              uniqueChannelCount={uniqueChannelCount}
            />
          ) : null}

          {activeSection === "costs" ? (
            <ObservabilityCosts usage={usage} topModel={topModel} />
          ) : null}
        </>
      ) : null}
    </WorkspacePageShell>
  );
}

function ObservabilityOverview({
  usage,
  structuredFlows,
  attentionFlows,
  primarySignal,
  topModel,
  totalInfrastructureConnections,
  healthyInfrastructureConnections,
  degradedInfrastructureConnections,
}: {
  usage: UsageSummary;
  structuredFlows: StructuredFlowEntry[];
  attentionFlows: StructuredFlowEntry[];
  primarySignal: StructuredFlowEntry | null;
  topModel: [string, { input_tokens: number; output_tokens: number; cost_usd: number }] | null;
  totalInfrastructureConnections: number;
  healthyInfrastructureConnections: number;
  degradedInfrastructureConnections: number;
}) {
  return (
    <div className="space-y-5">
      <SectionPanel
        eyebrow="Health"
        title="System health"
        description="Read the current posture first. Deeper diagnostics live in Reliability, Costs, and Infrastructure."
      >
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <div className="space-y-4 rounded-3xl border border-black/5 bg-white/90 p-5">
            {primarySignal ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className={severityClasses(primarySignal.severity)}>
                    {severityLabel(primarySignal.severity)}
                  </Badge>
                  <Badge variant="outline">
                    {formatFlowName(primarySignal.flow)}
                  </Badge>
                  <span className="text-xs text-slate-500">
                    Seen {formatRelativeTimestamp(primarySignal.stats.last_failure?.at ?? primarySignal.stats.last_seen_at)}
                  </span>
                </div>
                <div>
                  <p className="text-lg font-semibold text-slate-900">
                    {primarySignal.severity === "healthy"
                      ? "System health is currently stable."
                      : "Operator attention is required."}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {describeFailureImpact(primarySignal.flow, primarySignal.stats)}
                  </p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Recommended next action</p>
                  <p className="mt-2 text-sm leading-6 text-slate-700">
                    {recommendNextAction(primarySignal.flow, primarySignal.stats)}
                  </p>
                </div>
              </>
            ) : (
              <EmptyState description="No structured flow has been observed yet." />
            )}
          </div>

          <div className="grid gap-3">
            <MiniSignalCard
              label="Reliability posture"
              value={attentionFlows.length > 0 ? `${attentionFlows.length} alert(s)` : "Healthy"}
              description={
                attentionFlows.length > 0
                  ? `${attentionFlows.length} flow(s) need inspection`
                  : `${structuredFlows.length} observed flow(s) currently stable`
              }
            />
            <MiniSignalCard
              label="Cost posture"
              value={formatCost(usage.today.cost_usd)}
              description={
                topModel
                  ? `Dominant model: ${topModel[0]}`
                  : "No dominant model yet"
              }
            />
            <MiniSignalCard
              label="Infrastructure posture"
              value={`${healthyInfrastructureConnections}/${totalInfrastructureConnections}`}
              description={
                degradedInfrastructureConnections > 0
                  ? `${degradedInfrastructureConnections} connection(s) degraded or unavailable`
                  : "No degraded connection reported"
              }
            />
          </div>
        </div>
      </SectionPanel>

      <SectionPanel
        eyebrow="Drilldown"
        title="Next areas to inspect"
        description="Move from high-level health to the dedicated surface that answers the next operator question."
        tone="subtle"
      >
        <div className="grid gap-4 xl:grid-cols-3">
          <OverviewPathCard
            href="/usage?section=reliability"
            title="Reliability"
            description="Inspect failing flows, structured channels, and the latest backend-level diagnostics."
            value={attentionFlows.length > 0 ? `${attentionFlows.length} flow(s)` : "Healthy"}
            icon={<Workflow className="size-4" />}
          />
          <OverviewPathCard
            href="/usage?section=costs"
            title="Costs"
            description="Review burn, model distribution, and the recent spend trend without reliability noise."
            value={formatCost(usage.total.cost_usd)}
            icon={<DollarSign className="size-4" />}
          />
          <OverviewPathCard
            href="/connections"
            title="Infrastructure"
            description="Open the connection inventory, health status, and backend-executed integration setup."
            value={`${totalInfrastructureConnections} connection(s)`}
            icon={<Cable className="size-4" />}
          />
        </div>
      </SectionPanel>
    </div>
  );
}

function ObservabilityReliability({
  structuredFlows,
  attentionFlows,
  healthyFlows,
  totalCalls,
  totalFailures,
  uniqueChannelCount,
}: {
  structuredFlows: StructuredFlowEntry[];
  attentionFlows: StructuredFlowEntry[];
  healthyFlows: StructuredFlowEntry[];
  totalCalls: number;
  totalFailures: number;
  uniqueChannelCount: number;
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatBlock
          label="Attention flows"
          value={attentionFlows.length}
          description="Flows with warnings or failures"
          tone={attentionFlows.length > 0 ? "warning" : "positive"}
          icon={<ShieldAlert className="size-4" />}
        />
        <StatBlock
          label="Observed calls"
          value={totalCalls}
          description="Across structured backend flows"
          icon={<Workflow className="size-4" />}
        />
        <StatBlock
          label="Recorded failures"
          value={totalFailures}
          description="Latest backend reliability footprint"
          tone={totalFailures > 0 ? "danger" : "positive"}
          icon={<AlertTriangle className="size-4" />}
        />
        <StatBlock
          label="Active channels"
          value={uniqueChannelCount}
          description={`${healthyFlows.length} healthy flow(s)`}
          icon={<Cpu className="size-4" />}
        />
      </div>

      <SectionPanel
        eyebrow="Operator"
        title="Signals requiring attention"
        description="Start with the flows that need a decision or closer monitoring before reading raw diagnostics."
      >
        {attentionFlows.length === 0 ? (
          <EmptyState
            title="No active reliability alert."
            description="Observed calls remain healthy across the recent structured flows."
          />
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {attentionFlows.map(({ flow, stats, severity }) => (
              <div key={flow} className={`rounded-3xl border px-5 py-5 ${severityClasses(severity)}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-base font-semibold">{formatFlowName(flow)}</p>
                    <p className="mt-1 text-xs opacity-80">
                      Seen {formatRelativeTimestamp(stats.last_failure?.at ?? stats.last_seen_at)}
                    </p>
                  </div>
                  <Badge variant="outline" className={severityClasses(severity)}>
                    {severityLabel(severity)}
                  </Badge>
                </div>
                <p className="mt-4 text-sm leading-6 opacity-90">
                  {describeFailureImpact(flow, stats)}
                </p>
                <p className="mt-3 text-xs font-medium opacity-90">
                  Next action: {recommendNextAction(flow, stats)}
                </p>
                <a href="#technical-diagnostics" className="mt-4 inline-flex items-center gap-1 text-xs font-semibold">
                  Open diagnostics
                  <ArrowRight className="size-3" />
                </a>
              </div>
            ))}
          </div>
        )}
      </SectionPanel>

      <SectionPanel
        eyebrow="Technical"
        title="Structured diagnostics"
        description="Detailed channel usage, failure kinds, and latest backend signal per flow."
        contentClassName="space-y-4"
      >
        <div id="technical-diagnostics" />
        {structuredFlows.length === 0 ? (
          <EmptyState description="No structured flow has been observed yet." />
        ) : (
          structuredFlows.map(({ flow, stats, severity }) => (
            <div key={flow} className="rounded-3xl border border-slate-200 bg-slate-50/70 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-slate-900">{formatFlowName(flow)}</p>
                    <Badge variant="outline" className={severityClasses(severity)}>
                      {severityLabel(severity)}
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

              <div className="mt-4 flex flex-wrap gap-2">
                {Object.entries(stats.channels).length > 0 ? (
                  Object.entries(stats.channels).map(([channel, count]) => (
                    <Badge key={`${flow}-${channel}`} variant="outline" className={channelBadgeClass(channel)}>
                      {formatChannelLabel(channel)} · {count}
                    </Badge>
                  ))
                ) : (
                  <Badge variant="outline">No channel telemetry</Badge>
                )}
              </div>

              {Object.keys(stats.failures_by_kind ?? {}).length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-2">
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
          ))
        )}
      </SectionPanel>
    </div>
  );
}

function ObservabilityCosts({
  usage,
  topModel,
}: {
  usage: UsageSummary;
  topModel: [string, { input_tokens: number; output_tokens: number; cost_usd: number }] | null;
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatBlock
          label="Today burn"
          value={formatCost(usage.today.cost_usd)}
          description={`${formatTokens(usage.today.input_tokens + usage.today.output_tokens)} tokens today`}
          tone="accent"
          icon={<TrendingUp className="size-4" />}
        />
        <StatBlock
          label="Total spend"
          value={formatCost(usage.total.cost_usd)}
          description={`${usage.total.calls} API call(s) tracked`}
          icon={<DollarSign className="size-4" />}
        />
        <StatBlock
          label="Dominant model"
          value={topModel ? topModel[0] : "None"}
          description={topModel ? formatCost(topModel[1].cost_usd) : "No model usage yet"}
          icon={<Cpu className="size-4" />}
        />
        <StatBlock
          label="Tracked days"
          value={Object.keys(usage.daily).length}
          description="Historical usage buckets"
          icon={<Workflow className="size-4" />}
        />
      </div>

      <SectionPanel
        eyebrow="Cost posture"
        title="Spend summary"
        description="Daily burn, total exposure, and pricing guidance without reliability noise."
        tone="subtle"
      >
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="rounded-3xl border border-black/5 bg-white/90 p-5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Today</p>
            <p className="mt-3 text-3xl font-semibold text-slate-900">{formatCost(usage.today.cost_usd)}</p>
            <p className="mt-2 text-sm text-slate-600">
              {formatTokens(usage.today.input_tokens + usage.today.output_tokens)} tokens consumed today.
            </p>
          </div>
          <div className="rounded-3xl border border-black/5 bg-white/90 p-5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Pricing note</p>
            <p className="mt-3 text-sm leading-6 text-slate-700">
              {usage.pricing_note || "No backend pricing note available."}
            </p>
          </div>
        </div>
      </SectionPanel>

      <SectionPanel
        eyebrow="Breakdown"
        title="Spend by model"
        description="Model distribution, token split, and relative share of the total spend."
      >
        {Object.keys(usage.by_model).length === 0 ? (
          <EmptyState description="No call recorded yet." />
        ) : (
          <div className="space-y-4">
            {Object.entries(usage.by_model).map(([model, stats]) => {
              const totalTokens = stats.input_tokens + stats.output_tokens;
              const grandTotal = usage.total.input_tokens + usage.total.output_tokens || 1;
              const pct = Math.round((totalTokens / grandTotal) * 100);
              const isSonnet = model.includes("sonnet");

              return (
                <div key={model} className="space-y-2">
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
      </SectionPanel>

      <SectionPanel
        eyebrow="History"
        title="Usage history"
        description="Recent burn trend for the last 14 tracked days."
      >
        <DailyBarChart daily={usage.daily} />
      </SectionPanel>
    </div>
  );
}

function OverviewPathCard({
  href,
  title,
  description,
  value,
  icon,
}: {
  href: string;
  title: string;
  description: string;
  value: string;
  icon: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="block rounded-3xl border border-black/5 bg-white/90 px-5 py-5 transition-colors hover:border-primary/20 hover:bg-primary/5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          <p className="text-base font-semibold text-slate-900">{title}</p>
          <p className="text-sm leading-6 text-slate-600">{description}</p>
          <p className="text-sm font-medium text-slate-800">{value}</p>
        </div>
        <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
          {icon}
        </div>
      </div>
      <div className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-indigo-600">
        Open
        <ArrowRight className="size-3" />
      </div>
    </Link>
  );
}

function MiniSignalCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <div className="rounded-3xl border border-black/5 bg-white/90 px-4 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-2 text-lg font-semibold text-slate-900">{value}</p>
      <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
    </div>
  );
}
