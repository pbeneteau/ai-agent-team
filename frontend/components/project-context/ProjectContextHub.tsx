"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  MessageSquare,
  RefreshCw,
  Users,
} from "lucide-react";

import { ContextReadinessPanel } from "@/components/project-context/ContextReadinessPanel";
import { ContextRecommendationsPanel } from "@/components/project-context/ContextRecommendationsPanel";
import { DomainSecondaryNav } from "@/components/layout/DomainSecondaryNav";
import { SectionPanel } from "@/components/layout/SectionPanel";
import { StatBlock } from "@/components/layout/StatBlock";
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

export function ProjectContextHub() {
  const router = useRouter();
  const searchParams = useSearchParams();
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
        `Agent context refresh for "${document.filename}" started in the background.`,
      );
      loadKnowledgeReadiness();
    } catch {
      setError("Unable to start updating agent context from this document.");
    } finally {
      setBriefingDocId(null);
    }
  }

  const topAgents = showFullKnowledge ? knowledgeReadiness?.agents ?? [] : (knowledgeReadiness?.agents ?? []).slice(0, 3);
  const topSharedGaps = showFullKnowledge
    ? knowledgeReadiness?.shared_gaps ?? []
    : (knowledgeReadiness?.shared_gaps ?? []).slice(0, 3);
  const activeBrief = projectContextState?.active ?? null;
  const activeSection = (() => {
    const section = searchParams.get("section");
    switch (section) {
      case "documents":
      case "readiness":
      case "recommendations":
      case "brief":
        return section;
      default:
        return "brief";
    }
  })();
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
  const openAgentFromReadiness = useCallback(
    (agentId: string) => {
      const found = teams.flatMap((team) => team.agents).find((agent) => agent.id === agentId);
      router.push(`/team/agents/${found?.id ?? agentId}`);
    },
    [router, teams],
  );

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
        title="Context"
        description="Manage the brief, documents, readiness, and recommendations that define the product’s shared source of truth."
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
            <Link href="/team?section=teams">
              <Button variant="outline" className="gap-2 rounded-full">
                <Users className="size-4" />
                Open Organization
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
          <StatBlock
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
          <StatBlock
            label="Active revision"
            value={projectContextLoading ? "…" : `${activeBrief?.revision ?? 0}`}
            description={activeBrief?.published_at ? `Published on ${formatDate(activeBrief.published_at)}` : "No final publication yet"}
          />
          <StatBlock
            label="Documents"
            value={loadingDocuments ? "…" : `${documents.length}`}
            description={documents.length > 0 ? "Sources available for chat and agents" : "No shared source yet"}
          />
          <StatBlock
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

        <DomainSecondaryNav domain="context" />

        {activeSection === "brief" ? (
          <div className="space-y-4">
            <SectionPanel
              eyebrow="Canonical"
              title="Reference brief"
              description="This is the authoritative project frame. The published brief anchors Alex, planning, and rebriefing."
              tone="subtle"
              actions={
                activeBrief ? (
                  <Badge variant="outline" className="self-start">
                    {activeBrief.status === "published" ? `Published rev ${activeBrief.revision}` : `Draft rev ${activeBrief.revision}`}
                  </Badge>
                ) : null
              }
            >
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
            </SectionPanel>
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
          <ContextReadinessPanel
            knowledgeReadiness={knowledgeReadiness}
            knowledgeReadinessLoading={knowledgeReadinessLoading}
            canExpandKnowledge={canExpandKnowledge}
            showFullKnowledge={showFullKnowledge}
            topAgents={topAgents}
            topSharedGaps={topSharedGaps}
            onToggleExpanded={() => setShowFullKnowledge((current) => !current)}
            onRefresh={loadKnowledgeReadiness}
            onOpenAgent={openAgentFromReadiness}
          />
        ) : null}

        {activeSection === "recommendations" ? (
          <ContextRecommendationsPanel
            teams={teams}
            newTeamRecommendations={newTeamRecommendations}
            teamChangeRecommendations={teamChangeRecommendations}
            recommendationsLoading={recommendationsLoading}
            recommendationSource={recommendationSource}
            recommendationChannel={recommendationChannel}
            recommendationIssue={recommendationIssue}
            showAdvancedRecommendations={showAdvancedRecommendations}
            recommendationLoading={recommendationLoading}
            teamChangeLoading={teamChangeLoading}
            onToggleExpanded={() => setShowAdvancedRecommendations((current) => !current)}
            onCreateRecommendation={handleCreateRecommendation}
            onApplyTeamChange={handleApplyTeamChange}
          />
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

