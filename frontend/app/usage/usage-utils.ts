import type { UsageSummary } from "../../lib/api";
import { formatRelativeTimestamp } from "@/lib/config/formatting";

type StructuredFlowStats = NonNullable<UsageSummary["structured_outputs"]>["by_flow"][string];
type StructuredFailure = NonNullable<StructuredFlowStats["last_failure"]>;

type SignalSeverity = "critical" | "warning" | "healthy";

const FLOW_LABELS: Record<string, string> = {
  plan_generation: "Plan generation",
  task_planning: "Task planning",
  task_execution: "Task execution",
  team_recommendations: "Team recommendations",
  knowledge_readiness: "Knowledge readiness",
  chat_plan_preview: "Alex plan preview",
  chat_plan_confirm: "Alex plan confirm",
  chat_plan_revise: "Alex plan revise",
};

export function formatFlowName(flow: string): string {
  return FLOW_LABELS[flow] ?? flow.replace(/_/g, " ");
}

export function formatFailureKind(errorKind: string): string {
  switch (errorKind) {
    case "provider":
      return "Provider failure";
    case "validation":
      return "Schema mismatch";
    case "parse":
      return "Parse failure";
    case "empty_response":
      return "Empty response";
    case "repair":
      return "Repair fallback failed";
    case "tool_use":
      return "Tool-use mismatch";
    case "legacy_json":
      return "Legacy JSON path";
    case "unknown":
      return "Unknown failure";
    default:
      return errorKind.replace(/_/g, " ");
  }
}

export function formatChannelLabel(channel: string): string {
  switch (channel) {
    case "native_json_schema":
      return "Native schema";
    case "text_json":
      return "Text extraction";
    case "text_json_repair":
      return "JSON repair";
    case "mixed":
      return "Mixed channel";
    case "heuristic_fallback":
      return "Heuristic fallback";
    default:
      return channel.replace(/_/g, " ");
  }
}

export function channelBadgeClass(channel: string): string {
  switch (channel) {
    case "native_json_schema":
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    case "text_json_repair":
      return "border-violet-200 bg-violet-50 text-violet-800";
    case "text_json":
      return "border-slate-200 bg-slate-100 text-slate-700";
    default:
      return "border-slate-200 bg-slate-100 text-slate-700";
  }
}

export function getSignalSeverity(stats: StructuredFlowStats): SignalSeverity {
  if (stats.failures > 0) {
    return stats.failures >= Math.max(2, Math.round(stats.calls * 0.25)) ? "critical" : "warning";
  }
  return "healthy";
}

export function severityLabel(severity: SignalSeverity): string {
  switch (severity) {
    case "critical":
      return "Immediate action";
    case "warning":
      return "Watch closely";
    case "healthy":
      return "Healthy";
    default: {
      const exhaustive: never = severity;
      return exhaustive;
    }
  }
}

export function severityClasses(severity: SignalSeverity): string {
  switch (severity) {
    case "critical":
      return "border-rose-200 bg-rose-50 text-rose-800";
    case "warning":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "healthy":
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    default: {
      const exhaustive: never = severity;
      return exhaustive;
    }
  }
}

export function describeFailureImpact(flow: string, stats: StructuredFlowStats): string {
  if (stats.failures === 0) {
    return `${formatFlowName(flow)} remains stable across the latest observed calls.`;
  }
  const failureKind = stats.last_failure ? formatFailureKind(stats.last_failure.error_kind) : "Failure";
  return `${formatFlowName(flow)} produced ${stats.failures} recent failure(s). Latest signal: ${failureKind}.`;
}

export function recommendNextAction(flow: string, stats: StructuredFlowStats): string {
  const lastFailure = stats.last_failure;
  if (!lastFailure) {
    return "Keep monitoring the flow.";
  }
  switch (lastFailure.error_kind) {
    case "validation":
      return "Check the expected schema, the produced payload, and the validation rules.";
    case "provider":
      return "Inspect the provider, limits, or model-side availability issues.";
    case "parse":
    case "repair":
    case "legacy_json":
      return "Compare the expected raw output with the format actually returned by the model.";
    case "tool_use":
      return "Review the prompt or orchestration that triggers the tool call.";
    case "empty_response":
      return "Check whether the model stops too early or the request lacks context.";
    default:
      return `Inspect ${formatFlowName(flow)} in technical diagnostics.`;
  }
}

export function shouldShowFailureMessage(failure: StructuredFailure | null | undefined): boolean {
  return Boolean(failure?.message && failure.message.trim().length > 0);
}

export { formatRelativeTimestamp };

