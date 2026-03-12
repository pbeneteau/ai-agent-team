"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Folder,
  File,
  ChevronRight,
  RefreshCw,
  HardDrive,
  ArrowLeft,
  BookOpen,
  FolderOpen,
  Upload,
  Link2,
  Search,
  Loader2,
  CheckCircle2,
  GitBranch,
  GitPullRequest,
  Paperclip,
  Pencil,
  Trash2,
  Plus,
  Save,
  X,
  Sparkles,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { MarkdownContent } from "@/components/ui/markdown-content";
import {
  api,
  type AgentGitBinding,
  extractApiErrorMessage,
  type AgentMcpToolBinding,
  type AgentKnowledgeReadiness,
  type GitProviderConnection,
  type KnowledgeRecommendation,
  type KnowledgeRecommendationAction,
  type McpConnection,
} from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface WorkspaceEntry {
  name: string;
  type: "file" | "dir";
  size: number | null;
  modified: string;
  path: string;
}

interface WorkspaceInfo {
  agent_id: string;
  root: string;
  total_size_bytes: number;
  contents: WorkspaceEntry[];
}

interface SkillMeta {
  name: string;
  path: string;
  size_bytes: number;
  modified: string;
  author: string;
}

interface WorkLearningPreview {
  insights: string[];
  cautions: string[];
}

const AUTHOR_COLORS: Record<string, string> = {
  self: "bg-indigo-100 text-indigo-700",
  learning_phase: "bg-violet-100 text-violet-700",
  associate_alex: "bg-amber-100 text-amber-700",
  api: "bg-slate-100 text-slate-600",
};

function formatSize(bytes: number | null): string {
  if (bytes === null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function stripSkillHeader(content: string): string {
  // Remove the HTML comment metadata block at the top (<!-- skill: ... -->)
  return content.replace(/^<!--[\s\S]*?-->\s*/m, "").trimStart();
}

function isMarkdownPath(path: string | null): boolean {
  if (!path) return false;
  return [".md", ".markdown", ".mdx"].some((suffix) => path.toLowerCase().endsWith(suffix));
}

function extractWorkLearningPreview(content: string): WorkLearningPreview {
  const insights: string[] = [];
  const cautions: string[] = [];
  let section: "insights" | "cautions" | null = null;

  for (const rawLine of stripSkillHeader(content).split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;

    const lower = line.toLowerCase();
    if (lower.startsWith("## ")) {
      if (lower.includes("verified reusable insights")) {
        section = "insights";
      } else if (lower.includes("reusable cautions")) {
        section = "cautions";
      } else {
        section = null;
      }
      continue;
    }

    if (!line.startsWith("- ") && !line.startsWith("* ")) continue;
    const item = line.slice(2).trim();
    if (!item || item.toLowerCase().startsWith("no durable insights") || item.toLowerCase().startsWith("no reusable cautions")) {
      continue;
    }

    if (section === "insights" && insights.length < 3) {
      insights.push(item);
    } else if (section === "cautions" && cautions.length < 2) {
      cautions.push(item);
    }
  }

  return { insights, cautions };
}

function getSkillDisplayName(skillName: string): string {
  if (skillName === "work_learnings") return "Learnings";
  if (skillName === "core_skills") return "Core skills";
  if (skillName === "project_context") return "Project context";
  return skillName;
}

function getAuthorMeta(author: string): { label: string; className: string } {
  if (author === "associate_alex") {
    return { label: "Alex", className: "bg-amber-100 text-amber-700" };
  }
  if (author.startsWith("learn_from_work:")) {
    return { label: "Continuous learning", className: "bg-emerald-100 text-emerald-700" };
  }
  if (author.startsWith("knowledge:")) {
    return { label: "Knowledge", className: "bg-blue-100 text-blue-700" };
  }
  if (author.startsWith("doc_rebriefing:")) {
    return { label: "Shared doc", className: "bg-cyan-100 text-cyan-700" };
  }
  return {
    label: author,
    className: AUTHOR_COLORS[author] ?? AUTHOR_COLORS.api,
  };
}

function getReadinessMeta(level: AgentKnowledgeReadiness["readiness_level"]): { label: string; className: string } {
  switch (level) {
    case "sufficient":
      return { label: "Well briefed", className: "bg-emerald-50 text-emerald-700 border-emerald-200" };
    case "partial":
      return { label: "Partial", className: "bg-amber-50 text-amber-700 border-amber-200" };
    case "insufficient":
      return { label: "Needs context", className: "bg-rose-50 text-rose-700 border-rose-200" };
    default: {
      const _exhaustive: never = level;
      return _exhaustive;
    }
  }
}

function getRecommendationPriorityMeta(
  priority: KnowledgeRecommendation["priority"],
): { label: string; className: string } {
  switch (priority) {
    case "high":
      return { label: "High priority", className: "bg-rose-50 text-rose-700 border-rose-200" };
    case "medium":
      return { label: "Medium priority", className: "bg-amber-50 text-amber-700 border-amber-200" };
    case "low":
      return { label: "Low priority", className: "bg-slate-100 text-slate-700 border-slate-200" };
    default: {
      const _exhaustive: never = priority;
      return _exhaustive;
    }
  }
}

function getRecommendationStatusMeta(
  status: KnowledgeRecommendation["status"],
): { label: string; className: string } {
  switch (status) {
    case "suggested":
      return { label: "Suggested", className: "bg-blue-50 text-blue-700 border-blue-200" };
    case "applied":
      return { label: "Applied", className: "bg-emerald-50 text-emerald-700 border-emerald-200" };
    case "dismissed":
      return { label: "Dismissed", className: "bg-slate-100 text-slate-600 border-slate-200" };
    case "stale":
      return { label: "Stale", className: "bg-slate-100 text-slate-500 border-slate-200" };
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

function getRecommendationActionLabel(action: KnowledgeRecommendationAction): string {
  switch (action) {
    case "provide_document":
      return "Add a document";
    case "add_url":
      return "Add a URL";
    case "launch_research":
      return "Launch research";
    case "no_action_needed":
      return "No action needed";
    default: {
      const _exhaustive: never = action;
      return _exhaustive;
    }
  }
}

interface Props {
  agentId: string;
  agentName: string;
  onKnowledgeChanged?: () => void;
}

export function WorkspacePanel({ agentId, agentName, onKnowledgeChanged }: Props) {
  const [info, setInfo] = useState<WorkspaceInfo | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "knowledge" | "files" | "settings">("overview");
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [viewingSkill, setViewingSkill] = useState<{ name: string; content: string } | null>(null);
  const [editingSkill, setEditingSkill] = useState<{ name: string; content: string } | null>(null);
  const [skillSaving, setSkillSaving] = useState(false);
  const [newSkillMode, setNewSkillMode] = useState(false);
  const [newSkillName, setNewSkillName] = useState("");
  const [newSkillContent, setNewSkillContent] = useState("");
  const [currentPath, setCurrentPath] = useState(".");
  const [entries, setEntries] = useState<WorkspaceEntry[]>([]);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [, setLoading] = useState(true);
  const [history, setHistory] = useState<string[]>([]);

  // Knowledge tab state
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [mcpConnectionsEnabled, setMcpConnectionsEnabled] = useState(false);
  const [gitProviderConnectionsEnabled, setGitProviderConnectionsEnabled] = useState(false);
  const [knowledgeReadiness, setKnowledgeReadiness] = useState<AgentKnowledgeReadiness | null>(null);
  const [loadingKnowledgeReadiness, setLoadingKnowledgeReadiness] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [researchTopic, setResearchTopic] = useState("");
  const [knowledgeLoading, setKnowledgeLoading] = useState<"file" | "url" | "research" | null>(null);
  const [knowledgeSuccess, setKnowledgeSuccess] = useState<string | null>(null);
  const [knowledgeRecommendationLoading, setKnowledgeRecommendationLoading] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const urlInputRef = useRef<HTMLInputElement>(null);
  const [workLearningsContent, setWorkLearningsContent] = useState<string | null>(null);
  const [loadingWorkLearnings, setLoadingWorkLearnings] = useState(false);
  const [mcpConnections, setMcpConnections] = useState<McpConnection[]>([]);
  const [mcpBindings, setMcpBindings] = useState<AgentMcpToolBinding[]>([]);
  const [loadingMcpBindings, setLoadingMcpBindings] = useState(false);
  const [savingMcpBindings, setSavingMcpBindings] = useState(false);
  const [gitProviderConnections, setGitProviderConnections] = useState<GitProviderConnection[]>([]);
  const [gitBindings, setGitBindings] = useState<AgentGitBinding[]>([]);
  const [loadingGitBindings, setLoadingGitBindings] = useState(false);
  const [savingGitBindings, setSavingGitBindings] = useState(false);

  const loadInfo = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/agents/${agentId}/workspace`);
      if (res.ok) setInfo(await res.json());
    } catch (err) {
      console.error("[WorkspacePanel] Failed to load workspace info:", err);
    }
  }, [agentId]);

  const loadSkills = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/agents/${agentId}/skills`);
      if (res.ok) {
        const data = await res.json();
        setSkills(data.skills || []);
      }
    } catch (err) {
      console.error("[WorkspacePanel] Failed to load skills:", err);
    }
  }, [agentId]);

  const loadKnowledgeReadiness = useCallback(async () => {
    setLoadingKnowledgeReadiness(true);
    try {
      const data = await api.getAgentKnowledgeRecommendations(agentId);
      setKnowledgeReadiness(data);
    } catch (err) {
      console.error("[WorkspacePanel] Failed to load knowledge readiness:", err);
      setKnowledgeReadiness(null);
    } finally {
      setLoadingKnowledgeReadiness(false);
    }
  }, [agentId]);

  const loadMcpBindings = useCallback(async () => {
    setLoadingMcpBindings(true);
    try {
      const [connections, bindings] = await Promise.all([
        api.getMcpConnections(),
        api.getAgentMcpTools(agentId),
      ]);
      setMcpConnections(connections);
      setMcpBindings(bindings);
    } catch (err) {
      console.error("[WorkspacePanel] Failed to load MCP bindings:", err);
      setMcpConnections([]);
      setMcpBindings([]);
    } finally {
      setLoadingMcpBindings(false);
    }
  }, [agentId]);

  const loadGitBindings = useCallback(async () => {
    setLoadingGitBindings(true);
    try {
      const [connections, bindings] = await Promise.all([
        api.getGitProviderConnections(),
        api.getAgentGitBindings(agentId),
      ]);
      setGitProviderConnections(connections);
      setGitBindings(bindings);
    } catch (err) {
      console.error("[WorkspacePanel] Failed to load git bindings:", err);
      setGitProviderConnections([]);
      setGitBindings([]);
    } finally {
      setLoadingGitBindings(false);
    }
  }, [agentId]);

  const loadSkillContent = useCallback(async (skillName: string) => {
    try {
      const res = await fetch(`${API_BASE}/agents/${agentId}/skills/${skillName}`);
      if (res.ok) {
        const data = await res.json();
        setViewingSkill({ name: skillName, content: data.content });
      }
    } catch (err) {
      console.error("[WorkspacePanel] Failed to load skill content:", err);
    }
  }, [agentId]);

  const browsePath = useCallback(async (path: string) => {
    setLoading(true);
    setFileContent(null);
    setViewingFile(null);
    try {
      const res = await fetch(
        `${API_BASE}/agents/${agentId}/workspace/browse?path=${encodeURIComponent(path)}`
      );
      if (res.ok) {
        const data = await res.json();
        setEntries(data.entries);
        setCurrentPath(path);
      }
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  const readFile = useCallback(async (path: string) => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/agents/${agentId}/workspace/read?path=${encodeURIComponent(path)}`
      );
      if (res.ok) {
        const data = await res.json();
        setFileContent(data.content);
        setViewingFile(path);
      }
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    loadInfo();
    loadSkills();
    loadKnowledgeReadiness();
    loadMcpBindings();
    loadGitBindings();
    browsePath(".");
    api.getCapabilities()
      .then((c) => {
        setWebSearchEnabled(c.web_search);
        setMcpConnectionsEnabled(c.mcp_connections);
        setGitProviderConnectionsEnabled(c.git_provider_connections);
      })
      .catch(() => {});
  }, [agentId, loadInfo, loadSkills, loadKnowledgeReadiness, loadMcpBindings, loadGitBindings, browsePath]);

  useEffect(() => {
    const hasWorkLearnings = skills.some((skill) => skill.name === "work_learnings");
    if (!hasWorkLearnings) {
      setWorkLearningsContent(null);
      setLoadingWorkLearnings(false);
      return;
    }

    let active = true;
    setLoadingWorkLearnings(true);
    fetch(`${API_BASE}/agents/${agentId}/skills/work_learnings`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (active) {
          setWorkLearningsContent(data?.content ?? null);
        }
      })
      .catch((err) => {
        console.error("[WorkspacePanel] Failed to load work learnings:", err);
        if (active) {
          setWorkLearningsContent(null);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingWorkLearnings(false);
        }
      });

    return () => {
      active = false;
    };
  }, [agentId, skills]);

  const notifyKnowledgeChanged = useCallback(() => {
    onKnowledgeChanged?.();
  }, [onKnowledgeChanged]);

  const handleToggleMcpTool = useCallback(
    async (connectionId: string, toolName: string, enabled: boolean) => {
      setSavingMcpBindings(true);
      try {
        const currentBindings = mcpBindings.map((binding) => ({
          connection_id: binding.connection_id,
          tool_name: binding.tool_name,
          enabled: binding.enabled,
          alias: binding.alias,
          approval_mode: binding.approval_mode,
        }));
        const nextBindings = enabled
          ? [
              ...currentBindings,
              {
                connection_id: connectionId,
                tool_name: toolName,
                enabled: true,
                alias: null,
                approval_mode: "auto" as const,
              },
            ]
          : currentBindings.filter(
              (binding) =>
                !(binding.connection_id === connectionId && binding.tool_name === toolName),
            );
        const deduped = nextBindings.filter((binding, index, bindings) => {
          return (
            bindings.findIndex(
              (candidate) =>
                candidate.connection_id === binding.connection_id &&
                candidate.tool_name === binding.tool_name,
            ) === index
          );
        });
        const updated = await api.updateAgentMcpTools(agentId, deduped);
        setMcpBindings(updated);
      } catch (err) {
        alert(extractApiErrorMessage(err, "Unable to update MCP tools for this agent."));
      } finally {
        setSavingMcpBindings(false);
      }
    },
    [agentId, mcpBindings],
  );

  const handleToggleGitRepo = useCallback(
    async (connectionId: string, repoFullName: string, enabled: boolean) => {
      setSavingGitBindings(true);
      try {
        const currentBindings = gitBindings.map((binding) => ({
          connection_id: binding.connection_id,
          repo_full_name: binding.repo_full_name,
          enabled: binding.enabled,
          can_push: binding.can_push,
          can_open_pr: binding.can_open_pr,
          branch_prefix: binding.branch_prefix,
        }));
        const nextBindings = enabled
          ? [
              ...currentBindings,
              {
                connection_id: connectionId,
                repo_full_name: repoFullName,
                enabled: true,
                can_push: false,
                can_open_pr: false,
                branch_prefix: agentName.toLowerCase().replace(/\s+/g, "-"),
              },
            ]
          : currentBindings.filter(
              (binding) =>
                !(binding.connection_id === connectionId && binding.repo_full_name === repoFullName),
            );
        const deduped = nextBindings.filter((binding, index, bindings) => {
          return (
            bindings.findIndex(
              (candidate) =>
                candidate.connection_id === binding.connection_id &&
                candidate.repo_full_name === binding.repo_full_name,
            ) === index
          );
        });
        const updated = await api.updateAgentGitBindings(agentId, deduped);
        setGitBindings(updated);
      } catch (err) {
        alert(extractApiErrorMessage(err, "Unable to update git repository bindings for this agent."));
      } finally {
        setSavingGitBindings(false);
      }
    },
    [agentId, agentName, gitBindings],
  );

  const handleGitBindingPermissionChange = useCallback(
    async (
      connectionId: string,
      repoFullName: string,
      field: "can_push" | "can_open_pr" | "branch_prefix",
      value: boolean | string,
    ) => {
      setSavingGitBindings(true);
      try {
        const nextBindings = gitBindings.map((binding) => {
          if (binding.connection_id !== connectionId || binding.repo_full_name !== repoFullName) {
            return {
              connection_id: binding.connection_id,
              repo_full_name: binding.repo_full_name,
              enabled: binding.enabled,
              can_push: binding.can_push,
              can_open_pr: binding.can_open_pr,
              branch_prefix: binding.branch_prefix,
            };
          }
          return {
            connection_id: binding.connection_id,
            repo_full_name: binding.repo_full_name,
            enabled: binding.enabled,
            can_push: field === "can_push" ? Boolean(value) : binding.can_push,
            can_open_pr: field === "can_open_pr" ? Boolean(value) : binding.can_open_pr,
            branch_prefix: field === "branch_prefix" ? String(value) : binding.branch_prefix,
          };
        });
        const updated = await api.updateAgentGitBindings(agentId, nextBindings);
        setGitBindings(updated);
      } catch (err) {
        alert(extractApiErrorMessage(err, "Unable to update git repository permissions."));
      } finally {
        setSavingGitBindings(false);
      }
    },
    [agentId, gitBindings],
  );

  const handleRecommendationAction = useCallback(async (recommendation: KnowledgeRecommendation) => {
    switch (recommendation.action_type) {
      case "provide_document":
        setKnowledgeSuccess(`Recommended document: ${recommendation.recommended_source}`);
        fileInputRef.current?.click();
        return;
      case "add_url":
        setKnowledgeSuccess(`Suggested source: ${recommendation.recommended_source}`);
        setTimeout(() => urlInputRef.current?.focus(), 0);
        return;
      case "launch_research":
        setKnowledgeRecommendationLoading(recommendation.id);
        setKnowledgeSuccess(null);
        try {
          const readiness = await api.applyAgentKnowledgeRecommendation(agentId, recommendation.id);
          setKnowledgeReadiness(readiness);
          setKnowledgeSuccess(`Research launched for ${agentName}. The recommendation was marked as applied.`);
          notifyKnowledgeChanged();
        } catch (e) {
          setKnowledgeSuccess(`Error: ${e}`);
        } finally {
          setKnowledgeRecommendationLoading(null);
        }
        return;
      case "no_action_needed":
        return;
      default: {
        const _exhaustive: never = recommendation.action_type;
        return _exhaustive;
      }
    }
  }, [agentId, agentName, notifyKnowledgeChanged]);

  const handleDismissRecommendation = useCallback(async (recommendationId: string) => {
    setKnowledgeRecommendationLoading(recommendationId);
    setKnowledgeSuccess(null);
    try {
      const readiness = await api.dismissAgentKnowledgeRecommendation(agentId, recommendationId);
      setKnowledgeReadiness(readiness);
      notifyKnowledgeChanged();
    } catch (e) {
      setKnowledgeSuccess(`Error: ${e}`);
    } finally {
      setKnowledgeRecommendationLoading(null);
    }
  }, [agentId, notifyKnowledgeChanged]);

  const handleFileUpload = useCallback(async (file: File) => {
    setKnowledgeLoading("file");
    setKnowledgeSuccess(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.addAgentKnowledge(agentId, fd);
      setKnowledgeSuccess(`"${file.name}" shared with ${agentName}. The project context is being updated.`);
      setTimeout(() => {
        loadSkills();
        loadKnowledgeReadiness();
        notifyKnowledgeChanged();
        setKnowledgeSuccess(null);
      }, 6000);
    } catch (e) {
      setKnowledgeSuccess(`Error: ${e}`);
    } finally {
      setKnowledgeLoading(null);
    }
  }, [agentId, agentName, loadKnowledgeReadiness, loadSkills, notifyKnowledgeChanged]);

  const handleUrlSubmit = useCallback(async () => {
    if (!urlInput.trim()) return;
    setKnowledgeLoading("url");
    setKnowledgeSuccess(null);
    try {
      const fd = new FormData();
      fd.append("url", urlInput.trim());
      await api.addAgentKnowledge(agentId, fd);
      setKnowledgeSuccess(`URL shared with ${agentName}. The project context is being updated.`);
      setUrlInput("");
      setTimeout(() => {
        loadSkills();
        loadKnowledgeReadiness();
        notifyKnowledgeChanged();
        setKnowledgeSuccess(null);
      }, 6000);
    } catch (e) {
      setKnowledgeSuccess(`Error: ${e}`);
    } finally {
      setKnowledgeLoading(null);
    }
  }, [agentId, agentName, loadKnowledgeReadiness, loadSkills, notifyKnowledgeChanged, urlInput]);

  const handleResearch = useCallback(async () => {
    if (!researchTopic.trim()) return;
    setKnowledgeLoading("research");
    setKnowledgeSuccess(null);
    try {
      await api.launchAgentResearch(agentId, researchTopic.trim());
      setKnowledgeSuccess(`Research launched for "${researchTopic}". ${agentName} is searching the web now (30–90 sec).`);
      setResearchTopic("");
      setTimeout(() => {
        loadSkills();
        loadKnowledgeReadiness();
        notifyKnowledgeChanged();
        setKnowledgeSuccess(null);
      }, 90000);
    } catch (e) {
      setKnowledgeSuccess(`Error: ${e}`);
    } finally {
      setKnowledgeLoading(null);
    }
  }, [agentId, agentName, loadKnowledgeReadiness, loadSkills, notifyKnowledgeChanged, researchTopic]);

  function navigateTo(entry: WorkspaceEntry) {
    if (entry.type === "dir") {
      setHistory((h) => [...h, currentPath]);
      browsePath(entry.path);
    } else {
      readFile(entry.path);
    }
  }

  function goBack() {
    if (viewingSkill) {
      setViewingSkill(null);
      return;
    }
    if (viewingFile) {
      setFileContent(null);
      setViewingFile(null);
      return;
    }
    const prev = history[history.length - 1] ?? ".";
    setHistory((h) => h.slice(0, -1));
    browsePath(prev);
  }

  const pathParts = currentPath === "." ? [] : currentPath.split("/").filter(Boolean);

  const workLearningsSkill = skills.find((skill) => skill.name === "work_learnings") ?? null;
  const otherSkills = skills.filter((skill) => skill.name !== "work_learnings");
  const workLearningPreview = workLearningsContent ? extractWorkLearningPreview(workLearningsContent) : null;

  return (
    <div className="h-full min-h-0 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-slate-50">
        <div className="flex items-center gap-2">
          <HardDrive className="w-4 h-4 text-slate-500" />
          <span className="text-sm font-medium text-slate-700">
            Workspace — {agentName}
          </span>
          {info && (
            <span className="text-xs text-slate-400">
              ({formatSize(info.total_size_bytes)})
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => { loadInfo(); loadSkills(); browsePath(currentPath); }}>
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b shrink-0">
        {(["overview", "knowledge", "files", "settings"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => { setActiveTab(tab); setViewingSkill(null); setViewingFile(null); setFileContent(null); }}
            className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {tab === "overview" && <><Sparkles className="w-3.5 h-3.5" /> Overview</>}
            {tab === "knowledge" && <><Upload className="w-3.5 h-3.5" /> Knowledge</>}
            {tab === "files" && <><FolderOpen className="w-3.5 h-3.5" /> Files</>}
            {tab === "settings" && <><BookOpen className="w-3.5 h-3.5" /> Skills & config</>}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <div className="flex-1 overflow-y-auto min-h-0 p-4 space-y-5">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Workspace</p>
              <p className="mt-2 text-sm text-slate-700">
                {info ? `${entries.filter((entry) => entry.type === "file").length} visible files` : "Reading workspace…"}
              </p>
              {info ? (
                <p className="mt-1 text-xs text-slate-500">
                  Total size {formatSize(info.total_size_bytes)}.
                </p>
              ) : null}
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Knowledge readiness</p>
              {loadingKnowledgeReadiness ? (
                <div className="mt-2 flex items-center gap-2 text-sm text-slate-500">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Analysis in progress…
                </div>
              ) : knowledgeReadiness ? (
                <>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className={getReadinessMeta(knowledgeReadiness.readiness_level).className}>
                      {getReadinessMeta(knowledgeReadiness.readiness_level).label}
                    </Badge>
                    <Badge variant="outline">Score {knowledgeReadiness.readiness_score}/100</Badge>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">{knowledgeReadiness.summary}</p>
                </>
              ) : (
                <p className="mt-2 text-sm text-slate-500">Diagnostic unavailable right now.</p>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-sm font-semibold text-slate-900">Useful next actions</p>
            <p className="mt-1 text-sm text-slate-500">
              Enrich the context, browse workspace deliverables, or adjust the agent&apos;s skills.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="outline" size="sm" className="rounded-full" onClick={() => setActiveTab("knowledge")}>
                Enrich knowledge
              </Button>
              <Button variant="outline" size="sm" className="rounded-full" onClick={() => setActiveTab("files")}>
                Browse files
              </Button>
              <Button variant="outline" size="sm" className="rounded-full" onClick={() => setActiveTab("settings")}>
                Manage skills
              </Button>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Recent learnings</p>
              {loadingWorkLearnings ? (
                <div className="mt-3 flex items-center gap-2 text-sm text-slate-500">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Loading learnings…
                </div>
              ) : workLearningPreview && (workLearningPreview.insights.length > 0 || workLearningPreview.cautions.length > 0) ? (
                <div className="mt-3 space-y-4">
                  {workLearningPreview.insights.length > 0 ? (
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                        Reusable
                      </p>
                      <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
                        {workLearningPreview.insights.map((item) => (
                          <li key={item}>- {item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {workLearningPreview.cautions.length > 0 ? (
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">
                        Watch out
                      </p>
                      <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
                        {workLearningPreview.cautions.map((item) => (
                          <li key={item}>- {item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="mt-3 text-sm leading-6 text-slate-500">
                  No durable learning has been extracted from this workspace yet.
                </p>
              )}
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Quick configuration</p>
              <div className="mt-3 space-y-3 text-sm text-slate-600">
                <div className="rounded-xl bg-slate-50 px-3 py-3">
                  <p className="font-medium text-slate-900">Documented skills</p>
                  <p className="mt-1 text-xs text-slate-500">{skills.length} skill file(s) in the workspace.</p>
                </div>
                <div className="rounded-xl bg-slate-50 px-3 py-3">
                  <p className="font-medium text-slate-900">Current path</p>
                  <p className="mt-1 text-xs text-slate-500 break-all">{currentPath}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Settings tab */}
      {activeTab === "settings" && (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between border-b bg-slate-50/70 px-4 py-3">
            <div>
              <p className="text-sm font-medium text-slate-800">Skills & configuration</p>
              <p className="mt-1 text-xs text-slate-500">
                Advanced area for editing skills and managing this agent.
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="text-slate-400 hover:text-red-600"
              title="Delete this agent"
              onClick={async () => {
                if (!confirm(`Delete agent ${agentName}? This action cannot be undone.`)) return;
                try {
                  await api.deleteAgent(agentId);
                  window.location.reload();
                } catch (e) {
                  alert(`Error: ${e}`);
                }
              }}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </div>
          {!viewingSkill && !editingSkill && !newSkillMode && (
            <div className="border-b bg-white px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-slate-800">Git repositories</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Bind authorized GitHub or GitLab repositories to this agent for dev workflows.
                  </p>
                </div>
                {savingGitBindings ? <Loader2 className="h-4 w-4 animate-spin text-slate-400" /> : null}
              </div>
              {!gitProviderConnectionsEnabled ? (
                <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs text-slate-500">
                  Git provider connections are not available.
                </div>
              ) : loadingGitBindings ? (
                <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Loading git provider connections…
                </div>
              ) : gitProviderConnections.length === 0 ? (
                <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs text-slate-500">
                  No GitHub or GitLab connection has been configured yet.
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  {gitProviderConnections.map((connection) => (
                    <div key={connection.id} className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">{connection.name}</p>
                          <p className="mt-1 text-[11px] text-slate-500">
                            {connection.provider} · {connection.base_url}
                          </p>
                        </div>
                        <Badge
                          variant="outline"
                          className={
                            connection.status === "healthy"
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                              : connection.status === "degraded"
                                ? "border-amber-200 bg-amber-50 text-amber-700"
                                : connection.status === "unavailable"
                                  ? "border-rose-200 bg-rose-50 text-rose-700"
                                  : "border-slate-200 bg-slate-100 text-slate-600"
                          }
                        >
                          {connection.status}
                        </Badge>
                      </div>
                      {connection.discovered_repos.length === 0 ? (
                        <p className="mt-3 text-[11px] text-slate-500">
                          No repository indexed yet for this connection.
                        </p>
                      ) : (
                        <div className="mt-3 space-y-2">
                          {connection.discovered_repos.map((repo) => {
                            const activeBinding = gitBindings.find(
                              (binding) =>
                                binding.connection_id === connection.id &&
                                binding.repo_full_name === repo.full_name &&
                                binding.enabled,
                            );
                            return (
                              <div
                                key={`${connection.id}-${repo.full_name}`}
                                className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700"
                              >
                                <label className="flex items-start gap-2">
                                  <input
                                    type="checkbox"
                                    checked={Boolean(activeBinding)}
                                    disabled={savingGitBindings || connection.status === "unavailable"}
                                    onChange={(e) => handleToggleGitRepo(connection.id, repo.full_name, e.target.checked)}
                                  />
                                  <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="font-medium text-slate-900">{repo.full_name}</span>
                                      <Badge variant="outline" className="border-slate-200 bg-slate-100 text-slate-600">
                                        {repo.default_branch}
                                      </Badge>
                                    </div>
                                    <a
                                      href={repo.web_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="mt-1 inline-flex items-center gap-1 text-[11px] text-indigo-600 hover:text-indigo-700"
                                    >
                                      <GitBranch className="h-3 w-3" />
                                      {repo.web_url}
                                    </a>
                                  </div>
                                </label>
                                {activeBinding ? (
                                  <div className="mt-3 grid gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 md:grid-cols-[1fr_auto_auto]">
                                    <label className="space-y-1">
                                      <span className="text-[11px] font-medium text-slate-600">Branch prefix</span>
                                      <Input
                                        value={activeBinding.branch_prefix}
                                        disabled={savingGitBindings}
                                        onChange={(e) =>
                                          handleGitBindingPermissionChange(
                                            connection.id,
                                            repo.full_name,
                                            "branch_prefix",
                                            e.target.value,
                                          )
                                        }
                                        className="h-8 text-xs"
                                      />
                                    </label>
                                    <label className="flex items-center gap-2 text-[11px] text-slate-700">
                                      <input
                                        type="checkbox"
                                        checked={activeBinding.can_push}
                                        disabled={savingGitBindings}
                                        onChange={(e) =>
                                          handleGitBindingPermissionChange(
                                            connection.id,
                                            repo.full_name,
                                            "can_push",
                                            e.target.checked,
                                          )
                                        }
                                      />
                                      Push
                                    </label>
                                    <label className="flex items-center gap-2 text-[11px] text-slate-700">
                                      <input
                                        type="checkbox"
                                        checked={activeBinding.can_open_pr}
                                        disabled={savingGitBindings}
                                        onChange={(e) =>
                                          handleGitBindingPermissionChange(
                                            connection.id,
                                            repo.full_name,
                                            "can_open_pr",
                                            e.target.checked,
                                          )
                                        }
                                      />
                                      <GitPullRequest className="h-3 w-3" />
                                      PR / MR
                                    </label>
                                  </div>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {!viewingSkill && !editingSkill && !newSkillMode && (
            <div className="border-b bg-white px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-slate-800">MCP tools</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Assign read-only MCP tools from the global connections catalog to this agent.
                  </p>
                </div>
                {savingMcpBindings ? <Loader2 className="h-4 w-4 animate-spin text-slate-400" /> : null}
              </div>
              {!mcpConnectionsEnabled ? (
                <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs text-slate-500">
                  MCP connections are not available.
                </div>
              ) : loadingMcpBindings ? (
                <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Loading MCP connections…
                </div>
              ) : mcpConnections.length === 0 ? (
                <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs text-slate-500">
                  No MCP connection has been configured yet.
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  {mcpConnections.map((connection) => {
                    const readOnlyTools = connection.discovered_tools.filter((tool) => tool.read_only);
                    return (
                      <div key={connection.id} className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-900">{connection.name}</p>
                            <p className="mt-1 text-[11px] text-slate-500">{connection.endpoint_url}</p>
                          </div>
                          <Badge
                            variant="outline"
                            className={
                              connection.status === "healthy"
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                : connection.status === "degraded"
                                  ? "border-amber-200 bg-amber-50 text-amber-700"
                                  : connection.status === "unavailable"
                                    ? "border-rose-200 bg-rose-50 text-rose-700"
                                    : "border-slate-200 bg-slate-100 text-slate-600"
                            }
                          >
                            {connection.status}
                          </Badge>
                        </div>
                        {readOnlyTools.length === 0 ? (
                          <p className="mt-3 text-[11px] text-slate-500">
                            No read-only tool discovered yet for this connection.
                          </p>
                        ) : (
                          <div className="mt-3 space-y-2">
                            {readOnlyTools.map((tool) => {
                              const isChecked = mcpBindings.some(
                                (binding) =>
                                  binding.connection_id === connection.id &&
                                  binding.tool_name === tool.name &&
                                  binding.enabled,
                              );
                              return (
                                <label
                                  key={`${connection.id}-${tool.name}`}
                                  className="flex items-start gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700"
                                >
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    disabled={savingMcpBindings || connection.status === "unavailable"}
                                    onChange={(e) => handleToggleMcpTool(connection.id, tool.name, e.target.checked)}
                                  />
                                  <div className="min-w-0">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="font-medium text-slate-900">{tool.name}</span>
                                      <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
                                        read-only
                                      </Badge>
                                    </div>
                                    <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                                      {tool.description || "No description provided by the MCP server."}
                                    </p>
                                  </div>
                                </label>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          {/* Viewing a skill — read or edit mode */}
          {viewingSkill && !editingSkill ? (
            <div className="flex flex-col min-h-0 flex-1">
              <div className="flex items-center gap-1 px-4 py-2 border-b shrink-0">
                <Button variant="ghost" size="icon-sm" onClick={() => setViewingSkill(null)}>
                  <ArrowLeft className="w-3.5 h-3.5" />
                </Button>
                <span className="text-xs font-medium text-slate-700 flex-1 px-1">{viewingSkill.name}.md</span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setEditingSkill({ ...viewingSkill })}
                  className="text-slate-400 hover:text-primary"
                  title="Edit"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={async () => {
                    if (!confirm(`Delete skill "${viewingSkill.name}"?`)) return;
                    await api.deleteAgentSkill(agentId, viewingSkill.name);
                    setViewingSkill(null);
                    loadSkills();
                  }}
                  className="text-slate-400 hover:text-destructive"
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
              <div className="flex-1 overflow-y-auto min-h-0 p-4">
                <MarkdownContent
                  content={stripSkillHeader(viewingSkill.content)}
                  className="prose-sm prose-p:text-xs prose-li:text-xs prose-table:text-xs prose-h1:text-base prose-h2:text-sm prose-h3:text-xs prose-code:text-[11px] prose-pre:text-[11px]"
                />
              </div>
            </div>
          ) : editingSkill ? (
            <div className="flex flex-col min-h-0 flex-1 p-4 gap-3 overflow-y-auto">
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="icon-sm" onClick={() => setEditingSkill(null)}>
                  <X className="w-3.5 h-3.5" />
                </Button>
                <span className="text-xs font-medium text-slate-700 flex-1 px-1">Edit: {editingSkill.name}</span>
                <Button
                  size="sm"
                  disabled={skillSaving}
                  onClick={async () => {
                    setSkillSaving(true);
                    try {
                      await api.updateAgentSkill(agentId, editingSkill.name, editingSkill.content);
                      setViewingSkill({ name: editingSkill.name, content: editingSkill.content });
                      setEditingSkill(null);
                      loadSkills();
                    } finally {
                      setSkillSaving(false);
                    }
                  }}
                  className="gap-1.5 h-7 text-xs"
                >
                  {skillSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                  Save
                </Button>
              </div>
              <Textarea
                className="font-mono text-xs leading-relaxed resize-none min-h-[400px]"
                value={editingSkill.content}
                onChange={(e) => setEditingSkill({ ...editingSkill, content: e.target.value })}
              />
            </div>
          ) : newSkillMode ? (
            <div className="flex flex-col min-h-0 flex-1 p-4 gap-3 overflow-y-auto">
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="icon-sm" onClick={() => { setNewSkillMode(false); setNewSkillName(""); setNewSkillContent(""); }}>
                  <X className="w-3.5 h-3.5" />
                </Button>
                <Input
                  type="text"
                  placeholder="Skill name (no spaces)"
                  value={newSkillName}
                  onChange={(e) => setNewSkillName(e.target.value.replace(/\s+/g, "_"))}
                  className="flex-1 h-7 text-xs"
                />
                <Button
                  size="sm"
                  disabled={!newSkillName.trim() || skillSaving}
                  onClick={async () => {
                    setSkillSaving(true);
                    try {
                      await api.updateAgentSkill(agentId, newSkillName.trim(), newSkillContent);
                      setNewSkillMode(false);
                      setNewSkillName("");
                      setNewSkillContent("");
                      loadSkills();
                    } finally {
                      setSkillSaving(false);
                    }
                  }}
                  className="gap-1.5 h-7 text-xs"
                >
                  {skillSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                  Create
                </Button>
              </div>
              <Textarea
                className="font-mono text-xs leading-relaxed resize-none min-h-[400px]"
                placeholder="Skill content in Markdown…"
                value={newSkillContent}
                onChange={(e) => setNewSkillContent(e.target.value)}
              />
            </div>
          ) : skills.length === 0 ? (
            <div className="text-center py-10 px-4">
              <BookOpen className="w-8 h-8 text-slate-200 mx-auto mb-2" />
              <p className="text-xs text-slate-400">
                No documented skill yet. The agent will write its skills after the learning phase.
              </p>
              <Button size="sm" variant="outline" className="mt-3 gap-1.5 text-xs" onClick={() => setNewSkillMode(true)}>
                <Plus className="w-3 h-3" /> New skill
              </Button>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto min-h-0 p-2 space-y-1">
              <div className="flex justify-end px-2 py-1">
                <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={() => setNewSkillMode(true)}>
                  <Plus className="w-3 h-3" /> New skill
                </Button>
              </div>
              {workLearningsSkill && (
                <button
                  onClick={() => loadSkillContent(workLearningsSkill.name)}
                  className="mx-2 mb-3 w-[calc(100%-1rem)] rounded-xl border border-emerald-200 bg-emerald-50/70 p-3 text-left transition-colors hover:bg-emerald-50"
                >
                  <div className="flex items-start gap-3">
                    <div className="rounded-lg bg-emerald-100 p-2 text-emerald-700">
                      <Sparkles className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-emerald-950">What {agentName} learned</p>
                          <p className="mt-0.5 text-xs text-emerald-800">
                            Reusable memory extracted from real work.
                          </p>
                        </div>
                        <Badge variant="outline" className="border-emerald-200 bg-white text-[10px] text-emerald-700">
                          {formatSize(workLearningsSkill.size_bytes)}
                        </Badge>
                      </div>

                      {loadingWorkLearnings ? (
                        <div className="mt-3 flex items-center gap-2 text-xs text-emerald-800">
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          Loading learnings…
                        </div>
                      ) : workLearningPreview && (workLearningPreview.insights.length > 0 || workLearningPreview.cautions.length > 0) ? (
                        <div className="mt-3 space-y-3">
                          {workLearningPreview.insights.length > 0 && (
                            <div>
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                                Useful insights
                              </p>
                              <ul className="mt-1 space-y-1 text-xs leading-relaxed text-emerald-950">
                                {workLearningPreview.insights.map((item) => (
                                  <li key={item} className="line-clamp-2">- {item}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {workLearningPreview.cautions.length > 0 && (
                            <div>
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">
                                Watchouts
                              </p>
                              <ul className="mt-1 space-y-1 text-xs leading-relaxed text-amber-900">
                                {workLearningPreview.cautions.map((item) => (
                                  <li key={item} className="line-clamp-2">- {item}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ) : (
                        <p className="mt-3 text-xs text-emerald-800">
                          The memory exists, but no durable learning has been extracted yet.
                        </p>
                      )}
                    </div>
                  </div>
                </button>
              )}
              {(workLearningsSkill ? otherSkills : skills).map((skill) => {
                const authorMeta = getAuthorMeta(skill.author);
                return (
                <div
                  key={skill.name}
                  className="flex items-start gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 border border-transparent hover:border-slate-200 transition-all group"
                >
                  <button
                    className="flex items-start gap-3 flex-1 min-w-0 text-left"
                    onClick={() => loadSkillContent(skill.name)}
                  >
                    <BookOpen className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-700 truncate">{getSkillDisplayName(skill.name)}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge
                          variant="outline"
                          className={`text-[10px] px-1.5 py-0 ${authorMeta.className}`}
                        >
                          {authorMeta.label}
                        </Badge>
                        <span className="text-[10px] text-slate-400">
                          {formatSize(skill.size_bytes)} · {new Date(skill.modified).toLocaleDateString("en-US")}
                        </span>
                      </div>
                    </div>
                  </button>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={async () => {
                        const res = await fetch(`${API_BASE}/agents/${agentId}/skills/${skill.name}`);
                        if (res.ok) {
                          const data = await res.json();
                          setEditingSkill({ name: skill.name, content: data.content });
                        }
                      }}
                      className="text-slate-400 hover:text-primary"
                      title="Edit"
                    >
                      <Pencil className="w-3 h-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={async () => {
                        if (!confirm(`Delete skill "${skill.name}"?`)) return;
                        await api.deleteAgentSkill(agentId, skill.name);
                        loadSkills();
                      }}
                      className="text-slate-400 hover:text-destructive"
                      title="Delete"
                    >
                      <Trash2 className="w-3 h-3" />
                    </Button>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 flex-shrink-0 mt-1 group-hover:text-slate-500 transition-colors" />
                </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Knowledge tab */}
      {activeTab === "knowledge" && (
        <div
          className={`flex-1 overflow-y-auto min-h-0 p-4 space-y-5 ${isDragging ? "bg-indigo-50 ring-2 ring-inset ring-indigo-400" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const file = e.dataTransfer.files[0];
            if (file) handleFileUpload(file);
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md,.csv,.json,.yaml,.yml"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); e.target.value = ""; }}
          />

          {/* Success / status banner */}
          {knowledgeSuccess && (
            <div className="flex items-start gap-2 rounded-lg bg-green-50 border border-green-200 px-3 py-2.5 text-xs text-green-800">
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5 text-green-600" />
              <span>{knowledgeSuccess}</span>
            </div>
          )}

          {/* Knowledge readiness */}
          <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                  Knowledge readiness
                </p>
                <p className="mt-1 text-sm text-slate-700">
                  Checks whether {agentName} has enough specific information to perform the mission well.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 text-xs"
                onClick={loadKnowledgeReadiness}
                disabled={loadingKnowledgeReadiness}
              >
                {loadingKnowledgeReadiness ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                Analyze
              </Button>
            </div>

            {loadingKnowledgeReadiness ? (
              <div className="flex items-center gap-2 rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />
                Knowledge needs analysis in progress…
              </div>
            ) : knowledgeReadiness ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className={getReadinessMeta(knowledgeReadiness.readiness_level).className}>
                    {getReadinessMeta(knowledgeReadiness.readiness_level).label}
                  </Badge>
                  <Badge variant="outline">
                    Score {knowledgeReadiness.readiness_score}/100
                  </Badge>
                  {knowledgeReadiness.generation_channel === "native_json_schema" ? (
                    <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-800">
                      Native schema
                    </Badge>
                  ) : null}
                  {knowledgeReadiness.generation_source === "heuristic_fallback" ? (
                    <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-800">
                      Heuristic fallback
                    </Badge>
                  ) : null}
                  <span className="text-[11px] text-slate-400">
                    Updated {new Date(knowledgeReadiness.updated_at).toLocaleString("en-US")}
                  </span>
                </div>

                {knowledgeReadiness.generation_source === "heuristic_fallback" ? (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-900">
                    This diagnostic was produced via heuristic fallback.
                    {knowledgeReadiness.generation_issue ? ` Reason: ${knowledgeReadiness.generation_issue}` : ""}
                  </div>
                ) : null}

                <p className="text-sm leading-relaxed text-slate-700">
                  {knowledgeReadiness.summary}
                </p>

                {knowledgeReadiness.missing_knowledge_summary.length > 0 && (
                  <div className="rounded-lg bg-white px-3 py-3 text-xs text-slate-600">
                    <p className="font-semibold uppercase tracking-wide text-slate-500">
                      Main missing context
                    </p>
                    <ul className="mt-2 space-y-1.5">
                      {knowledgeReadiness.missing_knowledge_summary.map((item) => (
                        <li key={item}>- {item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {knowledgeReadiness.recommendations.length === 0 ? (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-xs text-emerald-800">
                    No critical gap detected right now.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {knowledgeReadiness.recommendations.map((recommendation) => {
                      const priorityMeta = getRecommendationPriorityMeta(recommendation.priority);
                      const statusMeta = getRecommendationStatusMeta(recommendation.status);
                      const isBusy = knowledgeRecommendationLoading === recommendation.id;
                      const canAct = recommendation.status !== "dismissed" && recommendation.action_type !== "no_action_needed";
                      return (
                        <div
                          key={recommendation.id}
                          className={`rounded-xl border bg-white p-3 ${recommendation.status === "dismissed" ? "opacity-65" : ""}`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-sm font-semibold text-slate-900">{recommendation.title}</p>
                              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                                {recommendation.summary}
                              </p>
                            </div>
                            <div className="flex flex-wrap justify-end gap-2">
                              <Badge variant="outline" className={priorityMeta.className}>
                                {priorityMeta.label}
                              </Badge>
                              <Badge variant="outline" className={statusMeta.className}>
                                {statusMeta.label}
                              </Badge>
                            </div>
                          </div>

                          <p className="mt-3 text-xs leading-relaxed text-slate-700">
                            {recommendation.reason}
                          </p>

                          <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                            <p className="font-medium text-slate-700">Recommended source</p>
                            <p className="mt-1">{recommendation.recommended_source}</p>
                            {recommendation.suggested_topic && (
                              <p className="mt-1 text-slate-500">
                                Suggested topic: {recommendation.suggested_topic}
                              </p>
                            )}
                          </div>

                          {recommendation.evidence.length > 0 && (
                            <div className="mt-3 space-y-2">
                              {recommendation.evidence.map((evidence) => (
                                <div
                                  key={`${recommendation.id}-${evidence.source_label}-${evidence.excerpt}`}
                                  className="rounded-lg border border-slate-200 px-3 py-2 text-[11px] text-slate-600"
                                >
                                  <p className="font-medium text-slate-700">
                                    {evidence.source_label} · {evidence.source_type}
                                  </p>
                                  <p className="mt-1 leading-relaxed">{evidence.excerpt}</p>
                                </div>
                              ))}
                            </div>
                          )}

                          <div className="mt-3 flex flex-wrap gap-2">
                            {canAct && (
                              <Button
                                size="sm"
                                className="h-7 gap-1.5 text-xs"
                                disabled={isBusy}
                                onClick={() => handleRecommendationAction(recommendation)}
                              >
                                {isBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                                {getRecommendationActionLabel(recommendation.action_type)}
                              </Button>
                            )}
                            {recommendation.status === "suggested" && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 text-xs text-slate-500"
                                disabled={isBusy}
                                onClick={() => handleDismissRecommendation(recommendation.id)}
                              >
                                Dismiss
                              </Button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            ) : (
              <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-500">
                Analysis is not available for this agent yet.
              </div>
            )}
          </div>

          {/* Document upload */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Document</p>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={knowledgeLoading === "file"}
              className="w-full flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 px-4 py-5 text-center hover:border-indigo-300 hover:bg-indigo-50/40 transition-all disabled:opacity-50"
            >
              {knowledgeLoading === "file" ? (
                <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
              ) : (
                <Paperclip className="w-6 h-6 text-slate-300" />
              )}
              <span className="text-xs text-slate-500">
                {knowledgeLoading === "file" ? "Sharing…" : "Drag a PDF, DOCX, TXT… or click"}
              </span>
            </button>
          </div>

          {/* URL input */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">URL / Page web</p>
            <div className="flex gap-2">
              <div className="flex-1 flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
                <Link2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <input
                  ref={urlInputRef}
                  type="url"
                  placeholder="https://…"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleUrlSubmit()}
                  className="flex-1 text-sm outline-none bg-transparent placeholder:text-slate-400"
                />
              </div>
              <Button
                size="sm"
                disabled={!urlInput.trim() || knowledgeLoading === "url"}
                onClick={handleUrlSubmit}
                className="shrink-0"
              >
                {knowledgeLoading === "url" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Add"}
              </Button>
            </div>
            <p className="text-[10px] text-slate-400">The page content will be extracted and added to {agentName}&apos;s project context.</p>
          </div>

          {/* Web research */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Autonomous web research</p>
              {!webSearchEnabled && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
                  `SERPER_API_KEY` required
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <div className="flex-1 flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
                <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <input
                  type="text"
                  placeholder="Topic to research…"
                  value={researchTopic}
                  disabled={!webSearchEnabled}
                  onChange={(e) => setResearchTopic(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleResearch()}
                  className="flex-1 text-sm outline-none bg-transparent placeholder:text-slate-400 disabled:opacity-50 disabled:cursor-not-allowed"
                />
              </div>
              <Button
                size="sm"
                disabled={!webSearchEnabled || !researchTopic.trim() || knowledgeLoading === "research"}
                onClick={handleResearch}
                className="shrink-0"
              >
                {knowledgeLoading === "research" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Launch"}
              </Button>
            </div>
            <p className="text-[10px] text-slate-400">
              {webSearchEnabled
                ? `${agentName} will run 3–5 Google searches, summarize the findings, and save them in its skills.`
                : "Add SERPER_API_KEY=xxx to backend/.env to enable Google research (free on serper.dev)."}
            </p>
          </div>
        </div>
      )}

      {/* Files tab */}
      {activeTab === "files" && (
        <>
          {/* Breadcrumb */}
          <div className="flex items-center gap-1 px-4 py-2 border-b text-xs text-slate-500 bg-white">
            {(history.length > 0 || viewingFile) && (
              <button onClick={goBack} className="mr-1 hover:text-slate-700">
                <ArrowLeft className="w-3.5 h-3.5" />
              </button>
            )}
            <span
              className="hover:text-slate-700 cursor-pointer"
              onClick={() => { setHistory([]); browsePath("."); }}
            >
              root
            </span>
            {pathParts.map((part, i) => (
              <span key={i} className="flex items-center gap-1">
                <ChevronRight className="w-3 h-3" />
                <span className="hover:text-slate-700 cursor-pointer">{part}</span>
              </span>
            ))}
            {viewingFile && (
              <span className="flex items-center gap-1">
                <ChevronRight className="w-3 h-3" />
                <span className="text-indigo-600">{viewingFile.split("/").pop()}</span>
              </span>
            )}
          </div>

          <ScrollArea className="flex-1">
            {viewingFile && fileContent !== null ? (
              isMarkdownPath(viewingFile) ? (
                <div className="p-4">
                  <MarkdownContent content={fileContent} className="prose-sm" />
                </div>
              ) : (
                <pre className="p-4 text-xs font-mono text-slate-700 whitespace-pre-wrap leading-relaxed">
                  {fileContent}
                </pre>
              )
            ) : (
              <div className="p-2">
                {entries.length === 0 ? (
                  <p className="text-xs text-slate-400 text-center py-8">Empty directory</p>
                ) : (
                  entries.map((entry) => (
                    <button
                      key={entry.path}
                      onClick={() => navigateTo(entry)}
                      className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-slate-100 text-left group"
                    >
                      {entry.type === "dir" ? (
                        <Folder className="w-4 h-4 text-amber-500 flex-shrink-0" />
                      ) : (
                        <File className="w-4 h-4 text-slate-400 flex-shrink-0" />
                      )}
                      <span className="flex-1 text-sm text-slate-700 truncate">{entry.name}</span>
                      {entry.size !== null && (
                        <span className="text-xs text-slate-400 flex-shrink-0">
                          {formatSize(entry.size)}
                        </span>
                      )}
                      <span className="text-[10px] text-slate-300 flex-shrink-0 hidden group-hover:block">
                        {new Date(entry.modified).toLocaleDateString("en-US")}
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </ScrollArea>
        </>
      )}
    </div>
  );
}
