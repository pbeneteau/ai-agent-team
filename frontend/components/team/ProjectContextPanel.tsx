"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Save, FolderOpen, ChevronDown, ChevronUp } from "lucide-react";

interface ProjectContext {
  name?: string;
  description?: string;
  domain?: string;
  tech_stack?: string;
  target_audience?: string;
  business_model?: string;
  notes?: string;
}

export function ProjectContextPanel() {
  const [ctx, setCtx] = useState<ProjectContext>({});
  const [form, setForm] = useState<ProjectContext>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    api.getProjectContext()
      .then((data) => {
        setCtx(data);
        setForm(data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name?.trim() || !form.description?.trim()) return;
    setSaving(true);
    try {
      await api.saveProjectContext({
        name: form.name ?? "",
        description: form.description ?? "",
        domain: form.domain,
        tech_stack: form.tech_stack,
        target_audience: form.target_audience,
        business_model: form.business_model,
        notes: form.notes,
      });
      setCtx(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      alert(`Erreur : ${e}`);
    } finally {
      setSaving(false);
    }
  }

  const hasContext = ctx.name || ctx.description;

  return (
    <div className="border rounded-xl bg-white overflow-hidden">
      {/* Header — clickable summary */}
      <button
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-slate-50 transition-colors text-left"
        onClick={() => setExpanded((e) => !e)}
      >
        <FolderOpen className="w-4 h-4 text-indigo-500 shrink-0" />
        <div className="flex-1 min-w-0">
          {loading ? (
            <p className="text-sm text-slate-400">Chargement du contexte projet…</p>
          ) : hasContext ? (
            <>
              <p className="text-sm font-semibold text-slate-800 truncate">{ctx.name}</p>
              <p className="text-xs text-slate-500 truncate">{ctx.domain ? `${ctx.domain} — ` : ""}{ctx.description}</p>
            </>
          ) : (
            <p className="text-sm text-slate-500">Aucun contexte projet — cliquez pour en définir un</p>
          )}
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-slate-400 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
        )}
      </button>

      {/* Expanded form */}
      {expanded && (
        <div className="border-t px-5 py-4">
          {loading ? (
            <div className="flex justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
            </div>
          ) : (
            <form onSubmit={handleSave} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-600">Nom du projet *</label>
                  <Input
                    placeholder="Mon Super Projet"
                    value={form.name ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    required
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-600">Domaine</label>
                  <Input
                    placeholder="SaaS, e-commerce, fintech…"
                    value={form.domain ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))}
                    className="h-8 text-sm"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-600">Description *</label>
                <Textarea
                  placeholder="Décrivez votre projet en quelques phrases…"
                  value={form.description ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  required
                  className="text-sm min-h-[60px]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-600">Stack technique</label>
                  <Input
                    placeholder="Next.js, FastAPI, PostgreSQL…"
                    value={form.tech_stack ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, tech_stack: e.target.value }))}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-600">Audience cible</label>
                  <Input
                    placeholder="PME, startups, développeurs…"
                    value={form.target_audience ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, target_audience: e.target.value }))}
                    className="h-8 text-sm"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-600">Modèle économique</label>
                  <Input
                    placeholder="Freemium, SaaS B2B, marketplace…"
                    value={form.business_model ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, business_model: e.target.value }))}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-600">Notes</label>
                  <Input
                    placeholder="Contexte additionnel…"
                    value={form.notes ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                    className="h-8 text-sm"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-1">
                <p className="text-xs text-slate-400">
                  Sauvegarder rebriefe automatiquement tous les agents.
                </p>
                <Button type="submit" size="sm" disabled={saving} className="gap-1.5">
                  {saving ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : saved ? (
                    <span className="text-green-600">✓ Sauvegardé</span>
                  ) : (
                    <>
                      <Save className="w-3.5 h-3.5" />
                      Sauvegarder
                    </>
                  )}
                </Button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
