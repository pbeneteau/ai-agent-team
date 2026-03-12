"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronUp, FolderOpen, Loader2, PencilLine, Save, Send, X } from "lucide-react";

import { api, type ProjectBrief, type ProjectContext, type ProjectContextState } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MarkdownContent } from "@/components/ui/markdown-content";
import { Textarea } from "@/components/ui/textarea";

interface ProjectContextPanelProps {
  onSaved?: () => void;
  defaultExpanded?: boolean;
  collapsible?: boolean;
  documentCount?: number;
}

type ProjectContextField = keyof ProjectContext;

const FIELD_LABELS: Record<ProjectContextField, string> = {
  name: "Project name",
  description: "Project summary",
  domain: "Domain",
  short_term_goal: "Current focus",
  tech_stack: "Tech stack",
  target_audience: "Target audience",
  business_model: "Business model",
  notes: "Open questions / risks",
};

function emptyContext(): ProjectContext {
  return {
    name: "",
    description: "",
    domain: "",
    short_term_goal: "",
    tech_stack: "",
    target_audience: "",
    business_model: "",
    notes: "",
  };
}

function toEditableContext(brief?: ProjectBrief | ProjectContext | null): ProjectContext {
  return {
    name: brief?.name ?? "",
    description: brief?.description ?? "",
    domain: brief?.domain ?? "",
    short_term_goal: brief?.short_term_goal ?? "",
    tech_stack: brief?.tech_stack ?? "",
    target_audience: brief?.target_audience ?? "",
    business_model: brief?.business_model ?? "",
    notes: brief?.notes ?? "",
  };
}

function normalizeContext(context: ProjectContext): Record<ProjectContextField, string> {
  return {
    name: (context.name ?? "").trim(),
    description: (context.description ?? "").trim(),
    domain: (context.domain ?? "").trim(),
    short_term_goal: (context.short_term_goal ?? "").trim(),
    tech_stack: (context.tech_stack ?? "").trim(),
    target_audience: (context.target_audience ?? "").trim(),
    business_model: (context.business_model ?? "").trim(),
    notes: (context.notes ?? "").trim(),
  };
}

function diffFields(current: ProjectContext, baseline?: ProjectBrief | ProjectContext | null): ProjectContextField[] {
  const left = normalizeContext(current);
  const right = normalizeContext(toEditableContext(baseline));
  return (Object.keys(FIELD_LABELS) as ProjectContextField[]).filter((field) => left[field] !== right[field]);
}

function computeCompleteness(context: ProjectContext, documentCount: number): number {
  const normalized = normalizeContext(context);
  let score = 0;
  const weights: Record<ProjectContextField, number> = {
    name: 10,
    description: 26,
    domain: 8,
    short_term_goal: 18,
    tech_stack: 10,
    target_audience: 12,
    business_model: 8,
    notes: 8,
  };

  (Object.keys(weights) as ProjectContextField[]).forEach((field) => {
    if (normalized[field]) {
      score += weights[field];
    }
  });

  if (documentCount > 0) {
    score += 10;
  }

  return Math.min(score, 100);
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "Never";
  }
  try {
    return new Intl.DateTimeFormat("en-US", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function renderStatusLabel(brief?: ProjectBrief | null): string {
  if (!brief) {
    return "No brief";
  }
  return brief.status === "published" ? `Published rev ${brief.revision}` : `Draft rev ${brief.revision}`;
}

function truncateText(value: string, limit: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, limit - 1)).trimEnd()}…`;
}

function PublishedInfoBlock({
  label,
  value,
  markdown = false,
}: {
  label: string;
  value?: string;
  markdown?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const content = value ?? "";
  const normalized = content.replace(/\s+/g, " ").trim();
  const preview = truncateText(content, markdown ? 320 : 220);
  const isLong = normalized.length > (markdown ? 320 : 220);

  if (!normalized) {
    return null;
  }

  return (
    <div className="space-y-2 rounded-2xl border border-black/5 bg-white px-4 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      {markdown && expanded ? (
        <MarkdownContent content={content} className="prose-p:my-0 prose-headings:mt-0 prose-headings:mb-2" />
      ) : (
        <p className="text-sm leading-6 text-slate-700">{expanded ? content : preview}</p>
      )}
      {isLong ? (
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="text-xs font-medium text-primary transition-colors hover:text-primary/80"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      ) : null}
    </div>
  );
}

function ReadOnlyInfoGrid({
  brief,
  emptyLabel,
}: {
  brief?: ProjectBrief | ProjectContext | null;
  emptyLabel: string;
}) {
  const values = toEditableContext(brief);
  const hasValues = Object.values(normalizeContext(values)).some(Boolean);

  if (!hasValues) {
    return (
      <div className="rounded-2xl border border-dashed border-black/8 bg-muted/30 px-4 py-6 text-sm text-muted-foreground">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <PublishedInfoBlock label="Identity" value={[values.name, values.domain].filter(Boolean).join(" · ")} />
      <PublishedInfoBlock label="Current focus" value={values.short_term_goal} />
      <PublishedInfoBlock label="Project summary" value={values.description} markdown />
      <PublishedInfoBlock
        label="Audience & market"
        value={[values.target_audience, values.business_model].filter(Boolean).join(" · ")}
      />
      <PublishedInfoBlock label="Stack & constraints" value={values.tech_stack} />
      <PublishedInfoBlock label="Open questions / risks" value={values.notes} markdown />
    </div>
  );
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <Card className="border-black/5 bg-white/92 shadow-none">
      <CardContent className="space-y-4 p-5">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <p className="text-xs leading-5 text-slate-500">{description}</p>
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

export function ProjectContextPanel({
  onSaved,
  defaultExpanded = false,
  collapsible = true,
  documentCount = 0,
}: ProjectContextPanelProps = {}) {
  const [state, setState] = useState<ProjectContextState | null>(null);
  const [form, setForm] = useState<ProjectContext>(emptyContext());
  const [loading, setLoading] = useState(true);
  const [savingDraft, setSavingDraft] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [flashMessage, setFlashMessage] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [isEditing, setIsEditing] = useState(false);
  const [selectedView, setSelectedView] = useState<"published" | "draft">("published");
  const [showDiff, setShowDiff] = useState(false);

  const loadState = useCallback(async () => {
    setLoading(true);
    try {
      const nextState = await api.getProjectContext();
      const baseline = nextState.draft ?? nextState.active;
      setState(nextState);
      setForm(toEditableContext(baseline));
      setIsEditing(!baseline);
    } catch {
      setState(null);
      setForm(emptyContext());
      setIsEditing(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadState();
  }, [loadState]);

  const published = state?.published ?? null;
  const active = state?.active ?? null;
  const draftBaseline = state?.draft ?? state?.active ?? null;
  const currentDraft = state?.draft ?? state?.active ?? null;

  const completionScore = useMemo(() => computeCompleteness(form, documentCount), [documentCount, form]);
  const changedAgainstPublished = useMemo(() => diffFields(form, published), [form, published]);
  const changedAgainstDraft = useMemo(() => diffFields(form, draftBaseline), [draftBaseline, form]);
  const hasLocalUnsavedChanges = changedAgainstDraft.length > 0;
  const hasContext = Boolean(active?.name || active?.description);
  const publishedHasContent = Boolean(published?.name || published?.description);
  const hasDraftContent = Boolean(currentDraft?.name || currentDraft?.description);
  const publishedChangedLabels = changedAgainstPublished.map((field) => FIELD_LABELS[field]);
  const visibleBrief = selectedView === "published" ? published : currentDraft;

  useEffect(() => {
    if (selectedView === "published" && !publishedHasContent && hasDraftContent) {
      setSelectedView("draft");
    }
    if (selectedView === "draft" && !hasDraftContent && publishedHasContent) {
      setSelectedView("published");
    }
  }, [hasDraftContent, publishedHasContent, selectedView]);

  async function handleSaveDraft(e: React.FormEvent) {
    e.preventDefault();
    setSavingDraft(true);
    try {
      const result = await api.saveProjectContextDraft(form);
      setState(result.state);
      setForm(toEditableContext(result.state.draft ?? result.state.active));
      setFlashMessage(result.message);
      setIsEditing(false);
    } catch (error) {
      alert(`Error: ${error}`);
    } finally {
      setSavingDraft(false);
    }
  }

  async function handlePublish() {
    if (!form.name?.trim() || !form.description?.trim()) {
      return;
    }
    setPublishing(true);
    try {
      const result = await api.publishProjectContext({
        ...form,
        name: form.name ?? "",
        description: form.description ?? "",
      });
      setState(result.state);
      setForm(toEditableContext(result.state.draft ?? result.state.active));
      setFlashMessage(result.message);
      setIsEditing(false);
      onSaved?.();
    } catch (error) {
      alert(`Error: ${error}`);
    } finally {
      setPublishing(false);
    }
  }

  function updateField(field: ProjectContextField, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function handleStartEditing() {
    setFlashMessage(null);
    setForm(toEditableContext(draftBaseline));
    setIsEditing(true);
  }

  function handleCancelEditing() {
    setForm(toEditableContext(draftBaseline));
    setIsEditing(false);
  }

  return (
    <div className="overflow-hidden rounded-3xl border border-black/5 bg-white/94 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.2)]">
      {collapsible ? (
        <button
          className="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-slate-50"
          onClick={() => setExpanded((current) => !current)}
        >
          <FolderOpen className="h-4 w-4 shrink-0 text-indigo-500" />
          <div className="min-w-0 flex-1">
            {loading ? (
              <p className="text-sm text-slate-400">Loading project context…</p>
            ) : hasContext ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-sm font-semibold text-slate-800">{active?.name}</p>
                  <Badge variant="outline" className="border-black/8 bg-white text-[10px] text-slate-600">
                    {renderStatusLabel(active)}
                  </Badge>
                </div>
                <p className="truncate text-xs text-slate-500">
                  {active?.domain ? `${active.domain} - ` : ""}
                  {active?.short_term_goal ? `Current focus: ${active.short_term_goal}` : active?.description}
                </p>
              </>
            ) : (
              <p className="text-sm text-slate-500">No project context yet — click to define one</p>
            )}
          </div>
          {expanded ? (
            <ChevronUp className="h-4 w-4 shrink-0 text-slate-400" />
          ) : (
            <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
          )}
        </button>
      ) : (
        <div className="flex items-start gap-3 border-b border-black/5 px-5 py-4">
          <FolderOpen className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-slate-800">Project reference brief</p>
              <Badge variant="outline" className="border-black/8 bg-white text-[10px] text-slate-600">
                {renderStatusLabel(active)}
              </Badge>
              <Badge variant="secondary" className="bg-primary/8 text-primary">
                {completionScore}/100
              </Badge>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Project source of truth. Alex remains the conversational interface, but does not directly edit this published brief.
            </p>
          </div>
        </div>
      )}

      {expanded ? (
        <div className={collapsible ? "border-t border-black/5 px-5 py-5" : "px-5 py-5"}>
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
            </div>
          ) : (
            <form onSubmit={handleSaveDraft} className="space-y-5">
              {flashMessage ? (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                  {flashMessage}
                </div>
              ) : null}

              <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm leading-6 text-blue-900">
                The published brief is the shared frame used by Alex, planning, learning, and knowledge audits.
                Chat remains useful for exploring, clarifying, and arbitrating, but it does not replace this source of truth.
              </div>

              {!isEditing ? (
                <div className="space-y-4">
                  <div className="flex flex-col gap-3 rounded-2xl border border-black/5 bg-[#fafaf7] px-4 py-4 md:flex-row md:items-center md:justify-between">
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-slate-900">Current brief</p>
                      <p className="text-xs leading-5 text-slate-500">
                        Only one visible version at a time to keep the reading clear.
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {publishedHasContent ? (
                        <button
                          type="button"
                          onClick={() => setSelectedView("published")}
                          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                            selectedView === "published"
                              ? "border-primary bg-primary/8 text-primary"
                              : "border-black/8 bg-white text-slate-600 hover:border-black/12"
                          }`}
                        >
                          Published view
                        </button>
                      ) : null}
                      {hasDraftContent ? (
                        <button
                          type="button"
                          onClick={() => setSelectedView("draft")}
                          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                            selectedView === "draft"
                              ? "border-primary bg-primary/8 text-primary"
                              : "border-black/8 bg-white text-slate-600 hover:border-black/12"
                          }`}
                        >
                          Current draft
                        </button>
                      ) : null}
                      <Button type="button" variant="outline" className="gap-2 rounded-full" onClick={handleStartEditing}>
                        <PencilLine className="h-3.5 w-3.5" />
                        {hasDraftContent ? "Edit" : "Create brief"}
                      </Button>
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">
                        {selectedView === "published" ? "Published view" : "Current draft"}
                      </p>
                      <p className="text-xs leading-5 text-slate-500">
                        {selectedView === "published"
                          ? "This is the version that should serve as the stable reference for the teams."
                          : "This draft prepares the next publication without overloading the main readout."}
                      </p>
                    </div>
                    {visibleBrief ? (
                      <Badge variant="outline" className="border-black/8 bg-white text-slate-600">
                        Rev {visibleBrief.revision}
                        {selectedView === "published" ? ` · ${formatDate(published?.published_at)}` : ""}
                      </Badge>
                    ) : null}
                  </div>

                  <ReadOnlyInfoGrid
                    brief={visibleBrief}
                    emptyLabel={
                      selectedView === "published"
                        ? "No published brief yet. Save a draft, then publish it to rebrief the teams."
                        : "No draft yet. Click “Create brief” to enter editing mode."
                    }
                  />

                  <div className="space-y-3 rounded-2xl border border-black/5 bg-[#fafaf7] px-4 py-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div className="space-y-1">
                        <p className="text-sm font-medium text-slate-900">Draft / published diff</p>
                        <p className="text-xs leading-5 text-slate-500">
                          Changes to publish stay secondary until you explicitly ask for the detail.
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="secondary" className="bg-slate-100 text-slate-700">
                          {publishedChangedLabels.length} field{publishedChangedLabels.length > 1 ? "s" : ""}
                        </Badge>
                        <Button
                          type="button"
                          variant="ghost"
                          className="rounded-full"
                          onClick={() => setShowDiff((current) => !current)}
                        >
                          {showDiff ? "Hide changes" : "View changes"}
                        </Button>
                      </div>
                    </div>

                    {showDiff ? (
                      publishedChangedLabels.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {publishedChangedLabels.map((label) => (
                            <Badge key={label} variant="outline" className="border-amber-200 bg-amber-50 text-amber-800">
                              {label}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <div className="rounded-2xl border border-dashed border-black/8 bg-muted/30 px-4 py-4 text-sm text-muted-foreground">
                          No difference between the current draft and the published brief.
                        </div>
                      )
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="space-y-5">
                  <div className="flex flex-col gap-3 rounded-2xl border border-black/5 bg-[#fafaf7] px-4 py-4 md:flex-row md:items-center md:justify-between">
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-slate-900">Draft editing</p>
                      <p className="text-xs leading-5 text-slate-500">
                        Update the project frame without stacking all reading views together.
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {currentDraft ? (
                        <Badge variant="outline" className="border-black/8 bg-white text-slate-600">
                          Rev {currentDraft.revision}
                        </Badge>
                      ) : null}
                      <Button type="button" variant="ghost" className="gap-2 rounded-full" onClick={handleCancelEditing}>
                        <X className="h-3.5 w-3.5" />
                        Cancel
                      </Button>
                    </div>
                  </div>

                  <SectionCard
                    title="Identity"
                    description="Set the basic frame: project name and primary domain."
                  >
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <label className="text-xs font-medium text-slate-600">Project name *</label>
                        <Input
                          placeholder="My Great Project"
                          value={form.name ?? ""}
                          onChange={(e) => updateField("name", e.target.value)}
                          required
                          className="h-9 text-sm"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-medium text-slate-600">Domain</label>
                        <Input
                          placeholder="SaaS, e-commerce, fintech…"
                          value={form.domain ?? ""}
                          onChange={(e) => updateField("domain", e.target.value)}
                          className="h-9 text-sm"
                        />
                      </div>
                    </div>
                  </SectionCard>

                  <SectionCard
                    title="Project summary"
                    description="Explain the problem, the value proposition, and what the project aims to accomplish."
                  >
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-slate-600">Description *</label>
                      <Textarea
                        placeholder="Describe your project, its core problem, and the main promise."
                        value={form.description ?? ""}
                        onChange={(e) => updateField("description", e.target.value)}
                        required
                        className="min-h-[120px] text-sm"
                      />
                    </div>
                  </SectionCard>

                  <SectionCard
                    title="Current focus"
                    description="Define the short-term goal that should orient every agent's priorities."
                  >
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-slate-600">Short-term goal</label>
                      <Textarea
                        placeholder="What is the main topic the team should focus on right now?"
                        value={form.short_term_goal ?? ""}
                        onChange={(e) => updateField("short_term_goal", e.target.value)}
                        className="min-h-[92px] text-sm"
                      />
                    </div>
                  </SectionCard>

                  <SectionCard
                    title="Audience & market"
                    description="Clarify who the project exists for and how it creates value."
                  >
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <label className="text-xs font-medium text-slate-600">Target audience</label>
                        <Input
                          placeholder="SMBs, startups, developers…"
                          value={form.target_audience ?? ""}
                          onChange={(e) => updateField("target_audience", e.target.value)}
                          className="h-9 text-sm"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-medium text-slate-600">Business model</label>
                        <Input
                          placeholder="Freemium, B2B SaaS, marketplace…"
                          value={form.business_model ?? ""}
                          onChange={(e) => updateField("business_model", e.target.value)}
                          className="h-9 text-sm"
                        />
                      </div>
                    </div>
                  </SectionCard>

                  <SectionCard
                    title="Stack & constraints"
                    description="Capture the stack, major dependencies, and known technical or operational constraints."
                  >
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-slate-600">Tech stack</label>
                      <Textarea
                        placeholder="Next.js, FastAPI, PostgreSQL, infra constraints, external APIs…"
                        value={form.tech_stack ?? ""}
                        onChange={(e) => updateField("tech_stack", e.target.value)}
                        className="min-h-[92px] text-sm"
                      />
                    </div>
                  </SectionCard>

                  <SectionCard
                    title="Open questions / risks"
                    description="List what remains ambiguous, known risks, and angles that still need validation."
                  >
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-slate-600">Notes</label>
                      <Textarea
                        placeholder="Hypotheses, risks, fuzzy areas, decisions to arbitrate…"
                        value={form.notes ?? ""}
                        onChange={(e) => updateField("notes", e.target.value)}
                        className="min-h-[110px] text-sm"
                      />
                    </div>
                  </SectionCard>

                  <div className="flex flex-col gap-3 rounded-2xl border border-black/5 bg-[#fafaf7] px-4 py-4 md:flex-row md:items-center md:justify-between">
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-slate-900">
                        {hasLocalUnsavedChanges
                          ? "Local changes have not been saved yet."
                          : !state?.published
                            ? "No published brief yet."
                            : state?.has_unpublished_changes
                              ? "The draft differs from the published brief."
                              : "The draft is aligned with the latest publication."}
                      </p>
                      <p className="text-xs leading-5 text-slate-500">
                        Saving the draft does not rebrief teams. Publishing launches a global rebrief with tracked revisioning.
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Button type="submit" variant="outline" disabled={savingDraft} className="gap-2 rounded-full">
                        {savingDraft ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                        Save draft
                      </Button>
                      <Button
                        type="button"
                        disabled={publishing || !form.name?.trim() || !form.description?.trim()}
                        className="gap-2 rounded-full"
                        onClick={handlePublish}
                      >
                        {publishing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                        Publish and rebrief teams
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </form>
          )}
        </div>
      ) : null}
    </div>
  );
}
