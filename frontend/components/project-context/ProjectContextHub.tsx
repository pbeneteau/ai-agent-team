"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Clock3,
  Loader2,
  MessageSquare,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  Target,
  UserMinus2,
  UserPlus2,
  Users,
} from "lucide-react";

import { WorkspacePageShell } from "@/components/layout/WorkspacePageShell";
import { useWsEvent } from "@/lib/ws-context";
import {
  api,
  type Document,
  type DocumentPreview,
  type GlobalKnowledgeReadiness,
  type ProjectContextState,
  type Team,
  type TeamChangeRecommendation,
  type TeamRecommendation,
} from "@/lib/api";
import { ProjectDocumentLibrary } from "@/components/project-context/ProjectDocumentLibrary";
import { ProjectContextPanel } from "@/components/team/ProjectContextPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const urgencyMeta: Record<TeamRecommendation["urgency"], { label: string; className: string }> = {
  now: { label: "Now", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  soon: { label: "Soon", className: "bg-amber-50 text-amber-700 border-amber-200" },
  later: { label: "Later", className: "bg-slate-100 text-slate-700 border-slate-200" },
};

const readinessMeta: Record<
  NonNullable<GlobalKnowledgeReadiness["agents"][number]>["readiness_level"],
  { label: string; className: string }
> = {
  sufficient: { label: "Well briefed", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  partial: { label: "Partial", className: "bg-amber-50 text-amber-700 border-amber-200" },
  insufficient: { label: "Needs context", className: "bg-rose-50 text-rose-700 border-rose-200" },
};

const changeTypeMeta: Record<TeamChangeRecommendation["change_type"], { label: string; icon: ReactNode; className: string }> = {
  add_specialist: {
    label: "Add a specialist",
    icon: <UserPlus2 className="w-3.5 h-3.5" />,
    className: "bg-blue-50 text-blue-700 border-blue-200",
  },
  remove_agent: {
    label: "Remove an agent",
    icon: <UserMinus2 className="w-3.5 h-3.5" />,
    className: "bg-rose-50 text-rose-700 border-rose-200",
  },
  adjust_scope: {
    label: "Adjust scope",
    icon: <SlidersHorizontal className="w-3.5 h-3.5" />,
    className: "bg-slate-100 text-slate-700 border-slate-200",
  },
};

export function ProjectContextHub() {
  const router = useRouter();
  const [activeSection, setActiveSection] = useState<"brief" | "documents" | "readiness" | "organization">("brief");
  const [teams, setTeams] = useState<Team[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [projectContextState, setProjectContextState] = useState<ProjectContextState | null>(null);
  const [newTeamRecommendations, setNewTeamRecommendations] = useState<TeamRecommendation[]>([]);
  const [teamChangeRecommendations, setTeamChangeRecommendations] = useState<TeamChangeRecommendation[]>([]);
  const [recommendationSource, setRecommendationSource] = useState<"llm" | "heuristic_fallback">("llm");
  const [recommendationChannel, setRecommendationChannel] = useState<string | null>(null);
  const [recommendationIssue, setRecommendationIssue] = useState<string | null>(null);
  const [knowledgeReadiness, setKnowledgeReadiness] = useState<GlobalKnowledgeReadiness | null>(null);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [projectContextLoading, setProjectContextLoading] = useState(true);
  const [recommendationsLoading, setRecommendationsLoading] = useState(true);
  const [knowledgeReadinessLoading, setKnowledgeReadinessLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [recommendationLoading, setRecommendationLoading] = useState<string | null>(null);
  const [teamChangeLoading, setTeamChangeLoading] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadDescription, setUploadDescription] = useState("");
  const [briefingDocId, setBriefingDocId] = useState<string | null>(null);
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null);
  const [showFullKnowledge, setShowFullKnowledge] = useState(false);
  const [showAdvancedRecommendations, setShowAdvancedRecommendations] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadTeams = useCallback(async () => {
    try {
      const nextTeams = await api.getTeams();
      setTeams(nextTeams);
    } catch (err) {
      console.error("[ProjectContextHub] Failed to load teams:", err);
      setError("Unable to load teams related to the context.");
    }
  }, []);

  const loadDocuments = useCallback(async () => {
    setLoadingDocuments(true);
    try {
      const nextDocuments = await api.getDocuments();
      setDocuments(nextDocuments);
    } catch (err) {
      console.error("[ProjectContextHub] Failed to load documents:", err);
      setError("Unable to load the document library.");
    } finally {
      setLoadingDocuments(false);
    }
  }, []);

  const loadProjectContext = useCallback(async () => {
    setProjectContextLoading(true);
    try {
      const nextState = await api.getProjectContext();
      setProjectContextState(nextState);
    } catch (err) {
      console.error("[ProjectContextHub] Failed to load project context:", err);
      setProjectContextState(null);
    } finally {
      setProjectContextLoading(false);
    }
  }, []);

  const loadRecommendations = useCallback(async () => {
    setRecommendationsLoading(true);
    try {
      const recs = await api.getTeamRecommendations();
      setNewTeamRecommendations(recs.new_teams);
      setTeamChangeRecommendations(recs.team_changes);
      setRecommendationSource(recs.generation_source);
      setRecommendationChannel(recs.generation_channel ?? null);
      setRecommendationIssue(recs.generation_issue);
    } catch (err) {
      console.error("[ProjectContextHub] Failed to load recommendations:", err);
      setNewTeamRecommendations([]);
      setTeamChangeRecommendations([]);
      setRecommendationSource("llm");
      setRecommendationChannel(null);
      setRecommendationIssue(null);
    } finally {
      setRecommendationsLoading(false);
    }
  }, []);

  const loadKnowledgeReadiness = useCallback(async () => {
    setKnowledgeReadinessLoading(true);
    try {
      const readiness = await api.getKnowledgeReadiness();
      setKnowledgeReadiness(readiness);
    } catch (err) {
      console.error("[ProjectContextHub] Failed to load knowledge readiness:", err);
      setKnowledgeReadiness(null);
    } finally {
      setKnowledgeReadinessLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjectContext();
    loadTeams();
    loadDocuments();
    loadRecommendations();
    loadKnowledgeReadiness();
  }, [loadDocuments, loadKnowledgeReadiness, loadProjectContext, loadRecommendations, loadTeams]);

  useWsEvent((msg) => {
    if (msg.type === "briefing_complete" || msg.type === "research_complete") {
      loadKnowledgeReadiness();
    }
    if (msg.type === "agent_status") {
      loadTeams();
    }
    if (msg.type === "team_created") {
      loadTeams();
      loadRecommendations();
      loadKnowledgeReadiness();
    }
  }, [loadKnowledgeReadiness, loadRecommendations, loadTeams]);

  const refreshAll = useCallback(() => {
    setError(null);
    loadProjectContext();
    loadTeams();
    loadDocuments();
    loadRecommendations();
    loadKnowledgeReadiness();
  }, [loadDocuments, loadKnowledgeReadiness, loadProjectContext, loadRecommendations, loadTeams]);

  async function handleCreateRecommendation(rec: TeamRecommendation) {
    setRecommendationLoading(rec.id);
    setError(null);
    try {
      await api.createCustomTeam({
        name: rec.name,
        description: rec.description,
        domain: rec.domain,
        agents: rec.agents,
      });
      setInfoMessage(`Team "${rec.name}" was created.`);
      refreshAll();
    } catch {
      setError("Error while creating the recommended team.");
    } finally {
      setRecommendationLoading(null);
    }
  }

  async function handleApplyTeamChange(change: TeamChangeRecommendation) {
    setTeamChangeLoading(change.id);
    setError(null);
    try {
      switch (change.change_type) {
        case "add_specialist":
          if (!change.suggested_agent) {
            throw new Error("No suggested specialist.");
          }
          await api.addAgentToTeam(change.team_id, change.suggested_agent);
          break;
        case "remove_agent":
          if (!change.target_agent_id) {
            throw new Error("No target agent.");
          }
          if (!confirm(`Remove ${change.target_agent_name ?? "this agent"} from team ${change.team_name}?`)) {
            return;
          }
          await api.deleteAgent(change.target_agent_id);
          break;
        case "adjust_scope":
          await api.updateTeamScope(change.team_id, {
            description: change.scope_update || change.reason,
            scope_note: change.reason,
          });
          break;
        default: {
          const exhaustive: never = change.change_type;
          throw new Error(`Unhandled change type: ${exhaustive}`);
        }
      }
      setInfoMessage(`The recommended change for "${change.team_name}" was applied.`);
      refreshAll();
    } catch {
      setError("Error while applying the recommendation.");
    } finally {
      setTeamChangeLoading(null);
    }
  }

  async function handleUploadFile(file: File) {
    setIsUploading(true);
    setError(null);
    try {
      await api.uploadDocument(file, uploadDescription.trim() || undefined);
      setUploadDescription("");
      setInfoMessage(`"${file.name}" was added to the document library.`);
      loadDocuments();
    } catch {
      setError("Error while adding the document.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function handleDeleteDocument(document: Document) {
    if (!confirm(`Delete document "${document.filename}"? This action cannot be undone.`)) {
      return;
    }
    setError(null);
    try {
      await api.deleteDocument(document.id);
      setPreview((current) => (current?.id === document.id ? null : current));
      setInfoMessage(`"${document.filename}" was deleted.`);
      loadDocuments();
    } catch {
      setError("Error while deleting the document.");
    }
  }

  async function handlePreviewDocument(document: Document) {
    setPreviewLoadingId(document.id);
    setError(null);
    try {
      const nextPreview = await api.getDocumentPreview(document.id);
      setPreview(nextPreview);
    } catch {
      setError("Unable to display the document preview.");
    } finally {
      setPreviewLoadingId(null);
    }
  }

  async function handleBriefAgents(document: Document) {
    setBriefingDocId(document.id);
    setError(null);
    try {
      await api.briefAgentsWithDocument(document.id);
      setInfoMessage(
        `Broadcast of "${document.filename}" to agents started in the background.`,
      );
      loadKnowledgeReadiness();
    } catch {
      setError("Unable to start broadcasting the document to agents.");
    } finally {
      setBriefingDocId(null);
    }
  }

  const topAgents = showFullKnowledge ? knowledgeReadiness?.agents ?? [] : (knowledgeReadiness?.agents ?? []).slice(0, 3);
  const topSharedGaps = showFullKnowledge
    ? knowledgeReadiness?.shared_gaps ?? []
    : (knowledgeReadiness?.shared_gaps ?? []).slice(0, 3);
  const activeBrief = projectContextState?.active ?? null;
  const readinessSummary = knowledgeReadinessLoading
    ? "Analysis in progress"
    : !knowledgeReadiness
      ? "Unavailable"
      : knowledgeReadiness.insufficient_agents > 0
        ? `${knowledgeReadiness.insufficient_agents} need context`
        : knowledgeReadiness.partial_agents > 0
          ? `${knowledgeReadiness.partial_agents} partial`
          : "Ready";
  const canExpandKnowledge =
    (knowledgeReadiness?.agents.length ?? 0) > 3 || (knowledgeReadiness?.shared_gaps.length ?? 0) > 3;

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.txt,.md,.csv,.json,.yaml,.yml"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            handleUploadFile(file);
          }
        }}
      />

      <WorkspacePageShell
        title="Brief & Documents"
        description="Maintain the shared brief, source documents, and readiness context that Alex and the agents rely on."
        meta={
          <>
            <span>
              {activeBrief?.updated_at
                ? `Brief updated ${formatDate(activeBrief.updated_at)}`
                : "Brief not initialized"}
            </span>
            <span>{documents.length} shared document(s)</span>
          </>
        }
        actions={
          <>
            <Link href="/chat">
              <Button variant="outline" className="gap-2 rounded-full">
                <MessageSquare className="size-4" />
                Open Alex
              </Button>
            </Link>
            <Link href="/team">
              <Button variant="outline" className="gap-2 rounded-full">
                <Users className="size-4" />
                View Teams & Agents
              </Button>
            </Link>
            <Button variant="outline" className="gap-2 rounded-full" onClick={refreshAll}>
              <RefreshCw className="size-4" />
              Refresh
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

        {infoMessage ? (
          <div className="flex items-center justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            <span>{infoMessage}</span>
            <Button variant="ghost" size="sm" className="rounded-full text-emerald-700" onClick={() => setInfoMessage(null)}>
              Close
            </Button>
          </div>
        ) : null}

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <SummaryCard
            label="Brief status"
            value={projectContextLoading ? "Loading…" : activeBrief ? renderBriefStatus(activeBrief.status) : "No brief"}
            description={
              activeBrief
                ? activeBrief.status === "published"
                  ? "Active reference version"
                  : "Active draft, not published yet"
                : "Define a shared frame"
            }
          />
          <SummaryCard
            label="Active revision"
            value={projectContextLoading ? "…" : `${activeBrief?.revision ?? 0}`}
            description={activeBrief?.published_at ? `Published on ${formatDate(activeBrief.published_at)}` : "No final publication yet"}
          />
          <SummaryCard
            label="Documents"
            value={loadingDocuments ? "…" : `${documents.length}`}
            description={documents.length > 0 ? "Sources available for chat and agents" : "No shared source yet"}
          />
          <SummaryCard
            label="Agent readiness"
            value={readinessSummary}
            description={
              knowledgeReadiness
                ? knowledgeReadiness.has_fallback_results
                  ? `${knowledgeReadiness.fallback_agent_count} audit(s) via fallback`
                  : `${knowledgeReadiness.sufficient_agents}/${knowledgeReadiness.total_agents} well briefed`
                : "Knowledge diagnostic"
            }
          />
        </div>

        <div className="flex flex-wrap gap-2 rounded-3xl border border-black/5 bg-white/92 p-3 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.18)]">
          {[
            {
              id: "brief",
              label: "Brief",
              description: "Published frame and current draft",
            },
            {
              id: "documents",
              label: "Documents",
              description: "Shared library and broadcasts",
            },
            {
              id: "readiness",
              label: "Readiness",
              description: "Agent context diagnostic",
            },
            {
              id: "organization",
              label: "Organization",
              description: "Structure recommendations",
            },
          ].map((section) => {
            const isActive = activeSection === section.id;
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => setActiveSection(section.id as typeof activeSection)}
                className={`rounded-2xl border px-4 py-3 text-left transition-colors ${
                  isActive
                    ? "border-primary bg-primary/8 text-primary"
                    : "border-transparent bg-[#fafaf7] text-slate-600 hover:border-black/8 hover:text-slate-900"
                }`}
              >
                <p className="text-sm font-semibold">{section.label}</p>
                <p className="mt-1 text-xs leading-5 text-current/80">{section.description}</p>
              </button>
            );
          })}
        </div>

        {activeSection === "brief" ? (
          <div className="space-y-4">
            <Card className="border-black/5 bg-[#fafaf7] shadow-none">
              <CardContent className="flex flex-col gap-3 p-5 md:flex-row md:items-start md:justify-between">
                <div className="space-y-1.5">
                  <p className="text-sm font-semibold text-slate-900">Reference brief</p>
                  <p className="text-sm leading-6 text-slate-600">
                    This section remains the source of truth for the project. The published brief overrides conversations and serves as the base for Alex, planning, and rebriefing.
                  </p>
                </div>
                {activeBrief ? (
                  <Badge variant="outline" className="self-start">
                    {activeBrief.status === "published" ? `Published rev ${activeBrief.revision}` : `Draft rev ${activeBrief.revision}`}
                  </Badge>
                ) : null}
              </CardContent>
            </Card>

            <ProjectContextPanel
              collapsible={false}
              defaultExpanded
              documentCount={documents.length}
              onSaved={() => {
                loadProjectContext();
                loadRecommendations();
                loadKnowledgeReadiness();
              }}
            />
          </div>
        ) : null}

        {activeSection === "documents" ? (
          <ProjectDocumentLibrary
            documents={documents}
            loading={loadingDocuments}
            isUploading={isUploading}
            uploadDescription={uploadDescription}
            preview={preview}
            previewLoadingId={previewLoadingId}
            briefingDocId={briefingDocId}
            onUploadDescriptionChange={setUploadDescription}
            onUploadClick={() => fileInputRef.current?.click()}
            onPreview={handlePreviewDocument}
            onClosePreview={() => setPreview(null)}
            onBriefAgents={handleBriefAgents}
            onDeleteDocument={handleDeleteDocument}
          />
        ) : null}

        {activeSection === "readiness" ? (
          <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.2)] ring-0">
          <CardHeader className="border-b border-black/5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle className="text-base">Agent context</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  Summary view of agent context level, with detail on demand only.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {canExpandKnowledge ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="rounded-full"
                    onClick={() => setShowFullKnowledge((current) => !current)}
                  >
                    {showFullKnowledge ? "Collapse" : "View full diagnostic"}
                  </Button>
                ) : null}
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2 rounded-full"
                  onClick={loadKnowledgeReadiness}
                  disabled={knowledgeReadinessLoading}
                >
                  {knowledgeReadinessLoading ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="size-3.5" />
                  )}
                  Refresh
                </Button>
              </div>
            </div>
          </CardHeader>

          <CardContent className="space-y-5 pt-4">
            {knowledgeReadinessLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Agent context analysis in progress…
              </div>
            ) : !knowledgeReadiness ? (
              <div className="rounded-2xl border border-dashed border-black/8 bg-muted/30 px-4 py-6 text-sm text-muted-foreground">
                Unable to load the context diagnostic right now.
              </div>
            ) : (
              <>
                {knowledgeReadiness.has_fallback_results ? (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                    Part of the knowledge audits comes from heuristic fallback, not the nominal structured channel.
                  </div>
                ) : null}

                {knowledgeReadiness.generation_channel ? (
                  <div className="flex flex-wrap gap-2">
                    <Badge
                      variant="outline"
                      className={
                        knowledgeReadiness.generation_channel === "native_json_schema"
                          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                          : knowledgeReadiness.generation_channel === "mixed"
                            ? "border-slate-200 bg-slate-100 text-slate-700"
                            : "border-amber-200 bg-amber-50 text-amber-800"
                      }
                    >
                      {knowledgeReadiness.generation_channel === "native_json_schema"
                        ? "Native schema"
                        : knowledgeReadiness.generation_channel === "mixed"
                          ? "Mixed channel"
                          : "Heuristic fallback"}
                    </Badge>
                  </div>
                ) : null}

                <div className="grid gap-3 md:grid-cols-4">
                  <MetricCard label="Tracked agents" value={knowledgeReadiness.total_agents} />
                  <MetricCard label="Needs context" value={knowledgeReadiness.insufficient_agents} tone="rose" />
                  <MetricCard label="Partial" value={knowledgeReadiness.partial_agents} tone="amber" />
                  <MetricCard label="Well briefed" value={knowledgeReadiness.sufficient_agents} tone="emerald" />
                </div>

                <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
                  <div className="space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Agents with the biggest gaps
                    </p>
                    {topAgents.length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-black/8 bg-muted/30 px-4 py-6 text-sm text-muted-foreground">
                        No agent available for diagnostics.
                      </div>
                    ) : (
                      topAgents.map((item) => (
                        <button
                          key={item.agent_id}
                          onClick={() => {
                            const found = teams.flatMap((team) => team.agents).find((agent) => agent.id === item.agent_id);
                            if (found) {
                              router.push(`/team/agents/${found.id}`);
                              return;
                            }
                            router.push(`/team/agents/${item.agent_id}`);
                          }}
                          className="w-full rounded-2xl border border-black/5 bg-white px-4 py-3 text-left transition-colors hover:border-primary/25 hover:bg-primary/5"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-sm font-semibold text-slate-900">{item.agent_name}</p>
                              <p className="mt-1 text-xs text-slate-500">{item.agent_title}</p>
                            </div>
                            <div className="flex flex-wrap items-center justify-end gap-2">
                              <Badge variant="outline" className={readinessMeta[item.readiness_level].className}>
                                {readinessMeta[item.readiness_level].label}
                              </Badge>
                              <Badge variant="outline">{item.readiness_score}/100</Badge>
                            </div>
                          </div>
                          <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-slate-600">{item.summary}</p>
                          {item.missing_knowledge_summary.length > 0 ? (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {item.missing_knowledge_summary.slice(0, 3).map((gap) => (
                                <span
                                  key={`${item.agent_id}-${gap}`}
                                  className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700"
                                >
                                  {gap}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </button>
                      ))
                    )}
                  </div>

                  <div className="space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Shared gaps
                    </p>
                    {topSharedGaps.length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-black/8 bg-muted/30 px-4 py-6 text-sm text-muted-foreground">
                        No notable shared gap right now.
                      </div>
                    ) : (
                      topSharedGaps.map((gap) => (
                        <div key={gap.id} className="rounded-2xl border border-black/5 bg-white px-4 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-900">{gap.title}</p>
                              <p className="mt-1 text-xs text-slate-500">
                                {gap.can_be_found_on_web
                                  ? "Can likely be covered with web research"
                                  : "Probably requires an internal source"}
                              </p>
                            </div>
                            <Badge variant="outline">{gap.agent_count} agent{gap.agent_count > 1 ? "s" : ""}</Badge>
                          </div>
                          <p className="mt-3 line-clamp-2 text-xs text-slate-600">
                            {gap.affected_agent_names.join(", ")}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
        ) : null}

        {activeSection === "organization" ? (
        <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.2)] ring-0">
          <CardHeader className="border-b border-black/5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-violet-500" />
                  <CardTitle className="text-base">Organization optimization</CardTitle>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  Advanced AI recommendations for creating or adjusting teams, intentionally kept behind a secondary view.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="rounded-full"
                onClick={() => setShowAdvancedRecommendations((current) => !current)}
              >
                {showAdvancedRecommendations ? "Collapse" : "View recommendations"}
              </Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-5 pt-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="New teams" value={newTeamRecommendations.length} />
              <MetricCard label="Adjustments" value={teamChangeRecommendations.length} tone="amber" />
              <MetricCard label="Current teams" value={teams.length} />
              <MetricCard
                label="Immediate priority"
                value={newTeamRecommendations.filter((rec) => rec.urgency === "now").length}
                tone="emerald"
              />
            </div>

            {recommendationSource === "heuristic_fallback" ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                Displayed recommendations use heuristic fallback.
                {recommendationIssue ? ` Reason: ${recommendationIssue}` : ""}
              </div>
            ) : null}

            {recommendationChannel ? (
              <div className="flex flex-wrap gap-2">
                <Badge
                  variant="outline"
                  className={
                    recommendationChannel === "native_json_schema"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                      : "border-amber-200 bg-amber-50 text-amber-800"
                  }
                >
                  {recommendationChannel === "native_json_schema" ? "Native schema" : "Heuristic fallback"}
                </Badge>
              </div>
            ) : null}

            {showAdvancedRecommendations ? (
              <>
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-violet-500" />
                    <p className="text-sm font-semibold text-slate-700">Recommended teams for this context</p>
                  </div>
                  {recommendationsLoading ? (
                    <InfoState label="Generating AI recommendations…" />
                  ) : newTeamRecommendations.length === 0 ? (
                    <InfoState label="No additional team is strongly recommended right now." />
                  ) : (
                    <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
                      {newTeamRecommendations.map((rec) => {
                        const isLoading = recommendationLoading === rec.id;
                        const urgency = urgencyMeta[rec.urgency];
                        return (
                          <button
                            key={rec.id}
                            onClick={() => handleCreateRecommendation(rec)}
                            disabled={isLoading}
                            className="flex flex-col items-start gap-3 rounded-2xl border border-black/5 bg-white p-4 text-left transition-all hover:border-primary/25 hover:shadow-sm disabled:opacity-60"
                          >
                            <div className="flex w-full items-start justify-between gap-3">
                              <div className="flex min-w-0 items-start gap-3">
                                <div className="rounded-2xl bg-violet-50 p-2 text-violet-600">
                                  {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Users className="w-4 h-4" />}
                                </div>
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-semibold text-slate-900">{rec.name}</p>
                                  <p className="mt-1 text-xs text-slate-500">{rec.description}</p>
                                </div>
                              </div>
                              <Badge variant="outline" className="shrink-0">
                                {rec.score}/100
                              </Badge>
                            </div>

                            <p className="text-sm leading-relaxed text-slate-600">{rec.reason}</p>

                            <div className="flex flex-wrap gap-2">
                              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${urgency.className}`}>
                                <Clock3 className="mr-1 inline h-3 w-3" />
                                {urgency.label}
                              </span>
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                                <Target className="mr-1 inline h-3 w-3" />
                                {rec.domain}
                              </span>
                              <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-700">
                                {rec.agents.length} agent{rec.agents.length > 1 ? "s" : ""}
                              </span>
                            </div>

                            <div className="w-full rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                              {rec.agents.map((agent) => (
                                <div key={`${rec.id}-${agent.name}-${agent.title}`} className="truncate">
                                  {agent.is_lead ? "Lead" : "Specialist"}: {agent.name} - {agent.title}
                                </div>
                              ))}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-sky-500" />
                    <p className="text-sm font-semibold text-slate-700">Recommended adjustments to existing teams</p>
                  </div>
                  {recommendationsLoading ? (
                    <InfoState label="Analyzing existing teams…" />
                  ) : teamChangeRecommendations.length === 0 ? (
                    <InfoState label="No team change is considered necessary right now." />
                  ) : (
                    <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
                      {teamChangeRecommendations.map((change) => {
                        const urgency = urgencyMeta[change.urgency];
                        const meta = changeTypeMeta[change.change_type];
                        const isApplying = teamChangeLoading === change.id;

                        return (
                          <div key={change.id} className="flex flex-col gap-3 rounded-2xl border border-black/5 bg-white p-4">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="text-sm font-semibold text-slate-900">{change.team_name}</p>
                                <p className="mt-1 text-xs text-slate-500">{change.reason}</p>
                              </div>
                              <Badge variant="outline" className="shrink-0">
                                {change.score}/100
                              </Badge>
                            </div>

                            <div className="flex flex-wrap gap-2">
                              <span
                                className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${meta.className}`}
                              >
                                {meta.icon}
                                {meta.label}
                              </span>
                              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${urgency.className}`}>
                                <Clock3 className="mr-1 inline h-3 w-3" />
                                {urgency.label}
                              </span>
                            </div>

                            {change.suggested_agent ? (
                              <div className="rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                                <p className="font-medium text-slate-700">Recommended profile</p>
                                <p className="mt-1">
                                  {change.suggested_agent.name} - {change.suggested_agent.title}
                                </p>
                                <p className="text-slate-500">
                                  {change.suggested_agent.specialization.replace(/_/g, " ")}
                                </p>
                              </div>
                            ) : null}

                            {change.target_agent_name ? (
                              <div className="rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                                Affected agent: {change.target_agent_name}
                              </div>
                            ) : null}

                            {change.scope_update ? (
                              <div className="rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                                New focus: {change.scope_update}
                              </div>
                            ) : null}

                            <Button
                              size="sm"
                              className="self-start gap-2"
                              disabled={isApplying}
                              onClick={() => handleApplyTeamChange(change)}
                            >
                              {isApplying ? (
                                <>
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  Applying…
                                </>
                              ) : (
                                <>
                                  {change.change_type === "add_specialist" ? (
                                    <UserPlus2 className="h-3.5 w-3.5" />
                                  ) : change.change_type === "remove_agent" ? (
                                    <UserMinus2 className="h-3.5 w-3.5" />
                                  ) : (
                                    <SlidersHorizontal className="h-3.5 w-3.5" />
                                  )}
                                  Apply
                                </>
                              )}
                            </Button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="rounded-2xl border border-dashed border-black/8 bg-muted/30 px-4 py-5 text-sm text-muted-foreground">
                Open this section only if you want to explore staffing or team-adjustment recommendations.
              </div>
            )}
          </CardContent>
        </Card>
        ) : null}
      </WorkspacePageShell>

    </>
  );
}

function renderBriefStatus(status: ProjectContextState["active"] extends infer T ? (T extends { status: infer S } ? S : never) : never) {
  return status === "published" ? "Published" : "Draft";
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

function SummaryCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl border border-black/5 bg-white/92 px-4 py-4 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.2)]">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-lg font-semibold text-slate-900">{value}</p>
      <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: number;
  tone?: "slate" | "rose" | "amber" | "emerald";
}) {
  const toneClassName =
    tone === "rose"
      ? "bg-rose-50"
      : tone === "amber"
        ? "bg-amber-50"
        : tone === "emerald"
          ? "bg-emerald-50"
          : "bg-slate-50";
  const valueClassName =
    tone === "rose"
      ? "text-rose-700"
      : tone === "amber"
        ? "text-amber-700"
        : tone === "emerald"
          ? "text-emerald-700"
          : "text-slate-900";

  return (
    <div className={`rounded-2xl border border-black/5 px-4 py-3 ${toneClassName}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${valueClassName}`}>{value}</p>
    </div>
  );
}

function InfoState({ label }: { label: string }) {
  return (
    <div className="rounded-2xl border border-black/5 bg-white px-4 py-6 text-sm text-muted-foreground">
      {label}
    </div>
  );
}
