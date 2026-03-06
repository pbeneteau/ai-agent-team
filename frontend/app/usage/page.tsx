"use client";

import { useEffect, useState, useCallback } from "react";
import { api, UsageSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { AlertTriangle, Loader2, RefreshCw, Trash2, TrendingUp, Cpu, DollarSign } from "lucide-react";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatCost(usd: number): string {
  if (usd < 0.01) return `$${(usd * 100).toFixed(3)}¢`;
  return `$${usd.toFixed(4)}`;
}

// Minimal bar chart using pure Tailwind
function DailyBarChart({ daily }: { daily: Record<string, { input: number; output: number; cost: number }> }) {
  const entries = Object.entries(daily)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14); // Last 14 days

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-slate-400">
        Aucune donnée historique
      </div>
    );
  }

  const maxCost = Math.max(...entries.map(([, v]) => v.cost), 0.0001);

  return (
    <div className="flex items-end gap-1.5 h-32 pt-2">
      {entries.map(([date, v]) => {
        const heightPct = Math.max((v.cost / maxCost) * 100, 2);
        const tokens = v.input + v.output;
        return (
          <div key={date} className="flex-1 flex flex-col items-center gap-1 group relative">
            <div className="hidden group-hover:block absolute bottom-full mb-1 bg-slate-800 text-white text-[10px] rounded px-2 py-1 whitespace-nowrap z-10">
              {date}<br />
              {formatCost(v.cost)} — {formatTokens(tokens)} tokens
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
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getUsage();
      setUsage(data);
      setError(null);
    } catch {
      setError("Impossible de charger les données d'usage.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleReset() {
    if (!confirm("Réinitialiser tous les compteurs d'usage ? Cette action est irréversible.")) return;
    setResetting(true);
    try {
      await api.resetUsage();
      await load();
    } catch {
      setError("Erreur lors du reset.");
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Usage & Coûts</h1>
          <p className="text-slate-500 mt-1">Suivi des tokens et coûts estimés Anthropic</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} className="gap-2">
            <RefreshCw className="w-3.5 h-3.5" />
            Actualiser
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={resetting}
            className="gap-2 text-red-600 hover:text-red-700"
          >
            {resetting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
            Réinitialiser
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      ) : usage ? (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-3 gap-4">
            <Card>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-indigo-100 rounded-lg">
                    <DollarSign className="w-4 h-4 text-indigo-600" />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">Coût total</p>
                    <p className="text-2xl font-bold text-slate-900">{formatCost(usage.total.cost_usd)}</p>
                    <p className="text-xs text-slate-400">{usage.total.calls} appels API</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-green-100 rounded-lg">
                    <TrendingUp className="w-4 h-4 text-green-600" />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">Aujourd&apos;hui</p>
                    <p className="text-2xl font-bold text-slate-900">{formatCost(usage.today.cost_usd)}</p>
                    <p className="text-xs text-slate-400">
                      {formatTokens(usage.today.input_tokens + usage.today.output_tokens)} tokens
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-violet-100 rounded-lg">
                    <Cpu className="w-4 h-4 text-violet-600" />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">Tokens totaux</p>
                    <p className="text-2xl font-bold text-slate-900">
                      {formatTokens(usage.total.input_tokens + usage.total.output_tokens)}
                    </p>
                    <p className="text-xs text-slate-400">
                      {formatTokens(usage.total.input_tokens)} in · {formatTokens(usage.total.output_tokens)} out
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Breakdown par modèle */}
          <Card>
            <CardHeader className="pb-3">
              <h3 className="font-semibold text-slate-800">Breakdown par modèle</h3>
            </CardHeader>
            <CardContent>
              {Object.keys(usage.by_model).length === 0 ? (
                <p className="text-sm text-slate-400">Aucun appel enregistré.</p>
              ) : (
                <div className="space-y-3">
                  {Object.entries(usage.by_model).map(([model, stats]) => {
                    const totalTokens = stats.input_tokens + stats.output_tokens;
                    const grandTotal = usage.total.input_tokens + usage.total.output_tokens || 1;
                    const pct = Math.round((totalTokens / grandTotal) * 100);
                    const isSonnet = model.includes("sonnet");

                    return (
                      <div key={model} className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className={`w-2 h-2 rounded-full ${isSonnet ? "bg-blue-500" : "bg-purple-500"}`} />
                            <span className="text-sm font-medium text-slate-700">{model}</span>
                          </div>
                          <div className="flex items-center gap-4 text-xs text-slate-500">
                            <span>{formatTokens(stats.input_tokens)} in</span>
                            <span>{formatTokens(stats.output_tokens)} out</span>
                            <span className="font-semibold text-slate-700">{formatCost(stats.cost_usd)}</span>
                          </div>
                        </div>
                        <div className="w-full bg-slate-100 rounded-full h-1.5">
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

          {/* Historique journalier */}
          <Card>
            <CardHeader className="pb-3">
              <h3 className="font-semibold text-slate-800">Historique (14 derniers jours)</h3>
              <p className="text-xs text-slate-500">Survolez les barres pour voir le détail</p>
            </CardHeader>
            <CardContent className="pb-6">
              <DailyBarChart daily={usage.daily ?? {}} />
            </CardContent>
          </Card>

          {/* Note sur les prix */}
          <p className="text-xs text-slate-400 text-center">
            {usage.pricing_note}
          </p>
        </>
      ) : null}
    </div>
  );
}
