"use client";

/**
 * Usage & cost tracking page with budget editor.
 * Ref: TDD-05 Section 16.3, TDD-01 J6 Steps 7-8
 */

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { DollarSign, Loader2, Pencil, Check } from "lucide-react";
import { useUsageStats, useUpdateBudget } from "@/lib/hooks/use-settings";
import { cn } from "@/lib/utils";

const periods = ["day", "week", "month"] as const;

export default function UsagePage() {
  const [period, setPeriod] = useState<string>("month");
  const { data, isLoading } = useUsageStats(period);

  const budget = data?.budget;
  const byModel = data?.by_model ?? {};
  const byArtifact = data?.by_artifact ?? [];
  const daily = data?.daily_breakdown ?? [];

  const budgetPct = budget ? budget.usage_pct : 0;
  const budgetColor = budgetPct > 90 ? "bg-[var(--color-danger)]" : budgetPct > 70 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]";

  return (
    <div className="space-y-6">
      {/* Period selector */}
      <div className="flex gap-1">
        {periods.map((p) => (
          <Button key={p} variant={period === p ? "default" : "ghost"} size="sm" onClick={() => setPeriod(p)} className="capitalize">
            {p}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-20 w-full rounded-[var(--radius-lg)]" />
          <div className="grid gap-4 sm:grid-cols-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-[var(--radius-lg)]" />)}</div>
        </div>
      ) : (
        <>
          {/* Budget bar */}
          {budget && (
            <div className="rounded-[var(--radius-lg)] border border-[var(--color-border-primary)] p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-[var(--color-text-primary)]">Monthly Budget</span>
                <BudgetEditor current={budget.monthly_limit_usd} />
              </div>
              <div className="flex items-center justify-between mb-1 text-xs text-[var(--color-text-secondary)]">
                <span>${budget.monthly_spent_usd.toFixed(2)} / ${budget.monthly_limit_usd.toFixed(2)}</span>
                <span className="tabular-nums">{budgetPct}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-bg-tertiary)]">
                <div className={cn("h-full rounded-full transition-all", budgetColor)} style={{ width: `${Math.min(budgetPct, 100)}%` }} />
              </div>
            </div>
          )}

          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-3">
            <Card size="sm">
              <CardHeader><CardTitle className="text-sm text-[var(--color-text-secondary)]">Total Cost</CardTitle></CardHeader>
              <CardContent><p className="text-2xl font-semibold text-[var(--color-text-primary)]">${(data?.total_cost_usd ?? 0).toFixed(2)}</p></CardContent>
            </Card>
            <Card size="sm">
              <CardHeader><CardTitle className="text-sm text-[var(--color-text-secondary)]">Input Tokens</CardTitle></CardHeader>
              <CardContent><p className="text-2xl font-semibold text-[var(--color-text-primary)]">{(data?.total_input_tokens ?? 0).toLocaleString()}</p></CardContent>
            </Card>
            <Card size="sm">
              <CardHeader><CardTitle className="text-sm text-[var(--color-text-secondary)]">Output Tokens</CardTitle></CardHeader>
              <CardContent><p className="text-2xl font-semibold text-[var(--color-text-primary)]">{(data?.total_output_tokens ?? 0).toLocaleString()}</p></CardContent>
            </Card>
          </div>

          {/* Model breakdown */}
          {Object.keys(byModel).length > 0 && (
            <div>
              <h3 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">By Model</h3>
              <div className="divide-y divide-[var(--color-border-primary)] rounded-[var(--radius-lg)] border border-[var(--color-border-primary)]">
                {Object.entries(byModel).map(([model, usage]) => (
                  <div key={model} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-sm font-medium text-[var(--color-text-primary)] capitalize">{model}</span>
                    <div className="text-right">
                      <span className="text-sm font-medium text-[var(--color-text-primary)]">${usage.cost_usd.toFixed(2)}</span>
                      <span className="ml-2 text-xs text-[var(--color-text-tertiary)]">
                        {usage.input_tokens.toLocaleString()} in / {usage.output_tokens.toLocaleString()} out
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Artifact breakdown */}
          {byArtifact.length > 0 && (
            <div>
              <h3 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">By Artifact</h3>
              <div className="divide-y divide-[var(--color-border-primary)] rounded-[var(--radius-lg)] border border-[var(--color-border-primary)] max-h-64 overflow-y-auto">
                {byArtifact.map((a) => (
                  <div key={a.artifact_id} className="flex items-center justify-between px-4 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-[var(--color-text-primary)]">{a.title}</p>
                      <p className="text-xs text-[var(--color-text-tertiary)]">{a.versions} version{a.versions !== 1 ? "s" : ""}</p>
                    </div>
                    <span className="shrink-0 text-sm font-medium tabular-nums text-[var(--color-text-primary)]">${a.cost_usd.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Daily trend (CSS bars) */}
          {daily.length > 0 && (
            <div>
              <h3 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Daily Trend</h3>
              <div className="flex items-end gap-1 h-32">
                {daily.map((d) => {
                  const maxCost = Math.max(...daily.map((x) => x.cost_usd), 0.01);
                  const height = Math.max((d.cost_usd / maxCost) * 100, 2);
                  return (
                    <div key={d.date} className="flex flex-1 flex-col items-center gap-1" title={`${d.date}: $${d.cost_usd.toFixed(2)}`}>
                      <div
                        className="w-full rounded-t-sm bg-[var(--color-accent)] transition-all"
                        style={{ height: `${height}%` }}
                      />
                      <span className="text-[8px] text-[var(--color-text-tertiary)] tabular-nums">
                        {d.date.slice(-2)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Budget editor ────────────────────────────────────────────────────
function BudgetEditor({ current }: { current: number }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(current));
  const updateBudget = useUpdateBudget();

  const handleSave = useCallback(() => {
    const amount = parseFloat(value);
    if (isNaN(amount) || amount <= 0) { toast.error("Invalid amount"); return; }
    updateBudget.mutate(amount, {
      onSuccess: () => { toast.success("Budget updated"); setEditing(false); },
      onError: (e) => toast.error(e.message || "Failed"),
    });
  }, [value, updateBudget]);

  if (!editing) {
    return (
      <Button size="xs" variant="ghost" onClick={() => { setValue(String(current)); setEditing(true); }}>
        <Pencil className="h-3 w-3" /> Edit
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <DollarSign className="h-3 w-3 text-[var(--color-text-tertiary)]" />
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        type="number"
        step="1"
        min="1"
        className="h-6 w-24 text-xs"
        onKeyDown={(e) => e.key === "Enter" && handleSave()}
        autoFocus
      />
      <Button size="icon-xs" onClick={handleSave} disabled={updateBudget.isPending}>
        {updateBudget.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
      </Button>
    </div>
  );
}
