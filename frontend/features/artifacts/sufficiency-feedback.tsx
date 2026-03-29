"use client";

/**
 * Inline sufficiency issue display with matched_text highlighting.
 *
 * Ref: TDD-05 Section 8.3, TDD-01 Journey J2 Step 5a
 *
 * Strategy: Each issue targets a specific form field via `issue.field`.
 * This component renders per-field issues next to the relevant input.
 * When `matched_text` is provided, it highlights the matching substring
 * in the form field's value using a mark element.
 */

import { Badge } from "@/components/ui/badge";
import { AlertCircle, AlertTriangle, Info } from "lucide-react";
import type { SufficiencyIssue } from "@/lib/types/api";

const severityConfig = {
  critical: {
    icon: AlertCircle,
    variant: "destructive" as const,
    bgClass: "bg-[var(--color-danger-subtle)]",
    textClass: "text-[var(--color-danger)]",
    borderClass: "border-[var(--color-danger)]",
  },
  warning: {
    icon: AlertTriangle,
    variant: "outline" as const,
    bgClass: "bg-[var(--color-warning-subtle)]",
    textClass: "text-[var(--color-warning)]",
    borderClass: "border-[var(--color-warning)]",
  },
  info: {
    icon: Info,
    variant: "secondary" as const,
    bgClass: "bg-[var(--color-bg-tertiary)]",
    textClass: "text-[var(--color-text-secondary)]",
    borderClass: "border-[var(--color-border-secondary)]",
  },
};

interface FieldIssuesProps {
  issues: SufficiencyIssue[];
  fieldValue?: string;
}

/**
 * Renders issues for a single form field, inline below the input.
 */
export function FieldIssues({ issues, fieldValue }: FieldIssuesProps) {
  if (issues.length === 0) return null;

  return (
    <div className="space-y-1.5 pt-1">
      {issues.map((issue, i) => {
        const config = severityConfig[issue.severity];
        const Icon = config.icon;

        return (
          <div
            key={i}
            className={`flex items-start gap-2 rounded-[var(--radius-sm)] border p-2 ${config.bgClass} ${config.borderClass}`}
          >
            <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${config.textClass}`} />
            <div className="min-w-0 space-y-1">
              <p className={`text-xs font-medium ${config.textClass}`}>{issue.message}</p>
              {issue.matched_text && fieldValue && (
                <HighlightedText text={fieldValue} match={issue.matched_text} severity={issue.severity} />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Highlights matched_text within the field value.
 */
function HighlightedText({
  text,
  match,
  severity,
}: {
  text: string;
  match: string;
  severity: SufficiencyIssue["severity"];
}) {
  const idx = text.toLowerCase().indexOf(match.toLowerCase());
  if (idx === -1) return null;

  const before = text.slice(0, idx);
  const matched = text.slice(idx, idx + match.length);
  const after = text.slice(idx + match.length);

  const highlightClass =
    severity === "critical"
      ? "bg-[var(--color-danger)] text-[var(--color-text-inverse)]"
      : severity === "warning"
        ? "bg-[var(--color-warning)] text-[var(--color-text-inverse)]"
        : "bg-[var(--color-bg-inverse)] text-[var(--color-text-inverse)]";

  return (
    <p className="text-xs text-[var(--color-text-secondary)] break-words">
      {before && <span>...{before.slice(-30)}</span>}
      <mark className={`rounded-sm px-0.5 ${highlightClass}`}>{matched}</mark>
      {after && <span>{after.slice(0, 30)}...</span>}
    </p>
  );
}

/**
 * Summary bar showing overall sufficiency status.
 */
interface SufficiencySummaryProps {
  isEligible: boolean;
  issues: SufficiencyIssue[];
}

export function SufficiencySummary({ isEligible, issues }: SufficiencySummaryProps) {
  const criticalCount = issues.filter((i) => i.severity === "critical").length;
  const warningCount = issues.filter((i) => i.severity === "warning").length;

  if (issues.length === 0 && isEligible) {
    return (
      <div className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-success-subtle)] p-3">
        <div className="h-2 w-2 rounded-full bg-[var(--color-success)]" />
        <p className="text-sm font-medium text-[var(--color-success)]">
          Brief is sufficient. Ready to delegate.
        </p>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)] p-3">
      {criticalCount > 0 && (
        <Badge variant="destructive">{criticalCount} critical</Badge>
      )}
      {warningCount > 0 && (
        <Badge variant="outline" className="bg-[var(--color-warning-subtle)] text-[var(--color-warning)]">
          {warningCount} warning{warningCount !== 1 ? "s" : ""}
        </Badge>
      )}
      <p className="text-xs text-[var(--color-text-secondary)]">
        {criticalCount > 0
          ? "Fix critical issues before delegating."
          : "Warnings are advisory — you can still delegate."}
      </p>
    </div>
  );
}
