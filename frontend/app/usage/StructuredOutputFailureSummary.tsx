import type { UsageSummary } from "../../lib/api";

import {
  channelBadgeClass,
  formatChannelLabel,
  formatFailureKind,
  recommendNextAction,
  shouldShowFailureMessage,
} from "./usage-utils";

type StructuredFlowStats = NonNullable<UsageSummary["structured_outputs"]>["by_flow"][string];

function failureBadgeClass(errorKind: string): string {
  const base = "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium";
  switch (errorKind) {
    case "validation":
      return `${base} border-amber-200 bg-amber-50 text-amber-800`;
    case "provider":
      return `${base} border-rose-200 bg-rose-50 text-rose-800`;
    case "parse":
    case "repair":
    case "empty_response":
      return `${base} border-orange-200 bg-orange-50 text-orange-800`;
    case "tool_use":
    case "legacy_json":
      return `${base} border-fuchsia-200 bg-fuchsia-50 text-fuchsia-800`;
    default:
      return `${base} border-slate-200 bg-slate-100 text-slate-700`;
  }
}

export function StructuredOutputFailureSummary({
  failure,
  flow,
}: {
  failure: StructuredFlowStats["last_failure"];
  flow: string;
}) {
  if (!failure) {
    return null;
  }

  return (
    <div className="mt-3 rounded-xl border border-rose-100 bg-white/80 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
          Latest failure
        </span>
        <span
          className={failureBadgeClass(failure.error_kind)}
        >
          {formatFailureKind(failure.error_kind)}
        </span>
        {failure.validation_failed ? (
          <span
            className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800"
          >
            Validation failed
          </span>
        ) : null}
        {failure.stop_reason ? (
          <span
            className="inline-flex items-center rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-[11px] font-mono text-slate-700"
          >
            {failure.stop_reason}
          </span>
        ) : null}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
        {failure.channel ? (
          <span className={`inline-flex items-center rounded-full border px-2 py-0.5 font-medium ${channelBadgeClass(failure.channel)}`}>
            {formatChannelLabel(failure.channel)}
          </span>
        ) : null}
        {failure.at ? (
          <span>At {new Date(failure.at).toLocaleString("en-US")}</span>
        ) : null}
      </div>

      {shouldShowFailureMessage(failure) ? (
        <p className="mt-2 text-[11px] text-slate-600">
          {failure.message}
        </p>
      ) : null}

      <p className="mt-2 text-[11px] font-medium text-slate-700">
        Next action: {recommendNextAction(flow, { calls: 0, successes: 0, failures: 1, channels: {}, last_failure: failure, last_request_name: failure.request_name, last_seen_at: failure.at })}
      </p>
    </div>
  );
}
