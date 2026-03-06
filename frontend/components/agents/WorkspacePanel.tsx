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
  Paperclip,
  Pencil,
  Trash2,
  Plus,
  Save,
  X,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

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

function formatSize(bytes: number | null): string {
  if (bytes === null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

interface Props {
  agentId: string;
  agentName: string;
}

export function WorkspacePanel({ agentId, agentName }: Props) {
  const [info, setInfo] = useState<WorkspaceInfo | null>(null);
  const [activeTab, setActiveTab] = useState<"skills" | "knowledge" | "files">("skills");
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
  const [urlInput, setUrlInput] = useState("");
  const [researchTopic, setResearchTopic] = useState("");
  const [knowledgeLoading, setKnowledgeLoading] = useState<"file" | "url" | "research" | null>(null);
  const [knowledgeSuccess, setKnowledgeSuccess] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    browsePath(".");
    api.getCapabilities().then((c) => setWebSearchEnabled(c.web_search)).catch(() => {});
  }, [agentId, loadInfo, loadSkills, browsePath]);

  const handleFileUpload = useCallback(async (file: File) => {
    setKnowledgeLoading("file");
    setKnowledgeSuccess(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.addAgentKnowledge(agentId, fd);
      setKnowledgeSuccess(`"${file.name}" partagé avec ${agentName}. Le project_context est en cours de mise à jour.`);
      setTimeout(() => { loadSkills(); setKnowledgeSuccess(null); }, 6000);
    } catch (e) {
      setKnowledgeSuccess(`Erreur : ${e}`);
    } finally {
      setKnowledgeLoading(null);
    }
  }, [agentId, agentName, loadSkills]);

  const handleUrlSubmit = useCallback(async () => {
    if (!urlInput.trim()) return;
    setKnowledgeLoading("url");
    setKnowledgeSuccess(null);
    try {
      const fd = new FormData();
      fd.append("url", urlInput.trim());
      await api.addAgentKnowledge(agentId, fd);
      setKnowledgeSuccess(`URL partagée avec ${agentName}. Le project_context est en cours de mise à jour.`);
      setUrlInput("");
      setTimeout(() => { loadSkills(); setKnowledgeSuccess(null); }, 6000);
    } catch (e) {
      setKnowledgeSuccess(`Erreur : ${e}`);
    } finally {
      setKnowledgeLoading(null);
    }
  }, [agentId, agentName, urlInput, loadSkills]);

  const handleResearch = useCallback(async () => {
    if (!researchTopic.trim()) return;
    setKnowledgeLoading("research");
    setKnowledgeSuccess(null);
    try {
      await api.launchAgentResearch(agentId, researchTopic.trim());
      setKnowledgeSuccess(`Recherche lancée sur "${researchTopic}". ${agentName} est en train de chercher sur le web (30–90 sec).`);
      setResearchTopic("");
      setTimeout(() => { loadSkills(); setKnowledgeSuccess(null); }, 90000);
    } catch (e) {
      setKnowledgeSuccess(`Erreur : ${e}`);
    } finally {
      setKnowledgeLoading(null);
    }
  }, [agentId, agentName, researchTopic, loadSkills]);

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

  const AUTHOR_COLORS: Record<string, string> = {
    self: "bg-indigo-100 text-indigo-700",
    learning_phase: "bg-violet-100 text-violet-700",
    associate_alex: "bg-amber-100 text-amber-700",
    api: "bg-slate-100 text-slate-600",
  };

  return (
    <div className="h-full flex flex-col">
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
          <Button
            variant="ghost"
            size="sm"
            className="text-slate-400 hover:text-red-600"
            title="Supprimer cet agent"
            onClick={async () => {
              if (!confirm(`Supprimer l'agent ${agentName} ? Cette action est irréversible.`)) return;
              try {
                await api.deleteAgent(agentId);
                window.location.reload();
              } catch (e) {
                alert(`Erreur : ${e}`);
              }
            }}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b shrink-0">
        {(["skills", "knowledge", "files"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => { setActiveTab(tab); setViewingSkill(null); setViewingFile(null); setFileContent(null); }}
            className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {tab === "skills" && <><BookOpen className="w-3.5 h-3.5" /> Skills ({skills.length})</>}
            {tab === "knowledge" && <><Upload className="w-3.5 h-3.5" /> Knowledge</>}
            {tab === "files" && <><FolderOpen className="w-3.5 h-3.5" /> Fichiers</>}
          </button>
        ))}
      </div>

      {/* Skills tab */}
      {activeTab === "skills" && (
        <ScrollArea className="flex-1">
          {/* Viewing a skill — read or edit mode */}
          {viewingSkill && !editingSkill ? (
            <div className="flex flex-col">
              <div className="flex items-center gap-2 px-4 py-2 border-b">
                <button onClick={() => setViewingSkill(null)} className="text-slate-500 hover:text-slate-700">
                  <ArrowLeft className="w-3.5 h-3.5" />
                </button>
                <span className="text-xs font-medium text-slate-700 flex-1">{viewingSkill.name}.md</span>
                <button
                  onClick={() => setEditingSkill({ ...viewingSkill })}
                  className="text-slate-400 hover:text-indigo-600 transition-colors"
                  title="Éditer"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={async () => {
                    if (!confirm(`Supprimer le skill "${viewingSkill.name}" ?`)) return;
                    await api.deleteAgentSkill(agentId, viewingSkill.name);
                    setViewingSkill(null);
                    loadSkills();
                  }}
                  className="text-slate-400 hover:text-red-600 transition-colors"
                  title="Supprimer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <pre className="p-4 text-xs font-mono text-slate-700 whitespace-pre-wrap leading-relaxed">
                {viewingSkill.content}
              </pre>
            </div>
          ) : editingSkill ? (
            <div className="flex flex-col p-4 gap-3">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setEditingSkill(null)}
                  className="text-slate-500 hover:text-slate-700"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
                <span className="text-xs font-medium text-slate-700 flex-1">Éditer : {editingSkill.name}</span>
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
                  Sauvegarder
                </Button>
              </div>
              <textarea
                className="w-full border rounded-md p-3 text-xs font-mono leading-relaxed resize-none min-h-[400px] focus:outline-none focus:ring-2 focus:ring-indigo-400"
                value={editingSkill.content}
                onChange={(e) => setEditingSkill({ ...editingSkill, content: e.target.value })}
              />
            </div>
          ) : newSkillMode ? (
            <div className="flex flex-col p-4 gap-3">
              <div className="flex items-center gap-2">
                <button onClick={() => { setNewSkillMode(false); setNewSkillName(""); setNewSkillContent(""); }} className="text-slate-500 hover:text-slate-700">
                  <X className="w-3.5 h-3.5" />
                </button>
                <input
                  type="text"
                  placeholder="Nom du skill (sans espaces)"
                  value={newSkillName}
                  onChange={(e) => setNewSkillName(e.target.value.replace(/\s+/g, "_"))}
                  className="flex-1 border rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"
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
                  Créer
                </Button>
              </div>
              <textarea
                className="w-full border rounded-md p-3 text-xs font-mono leading-relaxed resize-none min-h-[400px] focus:outline-none focus:ring-2 focus:ring-indigo-400"
                placeholder="Contenu du skill en Markdown…"
                value={newSkillContent}
                onChange={(e) => setNewSkillContent(e.target.value)}
              />
            </div>
          ) : skills.length === 0 ? (
            <div className="text-center py-10 px-4">
              <BookOpen className="w-8 h-8 text-slate-200 mx-auto mb-2" />
              <p className="text-xs text-slate-400">
                Aucun skill documenté. L&apos;agent écrira ses skills après la phase d&apos;apprentissage.
              </p>
              <Button size="sm" variant="outline" className="mt-3 gap-1.5 text-xs" onClick={() => setNewSkillMode(true)}>
                <Plus className="w-3 h-3" /> Nouveau skill
              </Button>
            </div>
          ) : (
            <div className="p-2 space-y-1">
              <div className="flex justify-end px-2 py-1">
                <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={() => setNewSkillMode(true)}>
                  <Plus className="w-3 h-3" /> Nouveau skill
                </Button>
              </div>
              {skills.map((skill) => (
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
                      <p className="text-sm font-medium text-slate-700 truncate">{skill.name}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge
                          variant="outline"
                          className={`text-[10px] px-1.5 py-0 ${AUTHOR_COLORS[skill.author] ?? AUTHOR_COLORS.api}`}
                        >
                          {skill.author === "associate_alex" ? "Alex" : skill.author}
                        </Badge>
                        <span className="text-[10px] text-slate-400">
                          {formatSize(skill.size_bytes)} · {new Date(skill.modified).toLocaleDateString("fr-FR")}
                        </span>
                      </div>
                    </div>
                  </button>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={async () => {
                        const res = await fetch(`${API_BASE}/agents/${agentId}/skills/${skill.name}`);
                        if (res.ok) {
                          const data = await res.json();
                          setEditingSkill({ name: skill.name, content: data.content });
                        }
                      }}
                      className="text-slate-400 hover:text-indigo-600 p-1 rounded"
                      title="Éditer"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                    <button
                      onClick={async () => {
                        if (!confirm(`Supprimer le skill "${skill.name}" ?`)) return;
                        await api.deleteAgentSkill(agentId, skill.name);
                        loadSkills();
                      }}
                      className="text-slate-400 hover:text-red-600 p-1 rounded"
                      title="Supprimer"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 flex-shrink-0 mt-1 group-hover:text-slate-500 transition-colors" />
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
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
                {knowledgeLoading === "file" ? "Partage en cours…" : "Glissez un PDF, DOCX, TXT… ou cliquez"}
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
                {knowledgeLoading === "url" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Ajouter"}
              </Button>
            </div>
            <p className="text-[10px] text-slate-400">Le contenu de la page sera extrait et intégré dans le project_context de {agentName}.</p>
          </div>

          {/* Web research */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Recherche web autonome</p>
              {!webSearchEnabled && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
                  SERPER_API_KEY requis
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <div className="flex-1 flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
                <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <input
                  type="text"
                  placeholder="Sujet à rechercher…"
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
                {knowledgeLoading === "research" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Lancer"}
              </Button>
            </div>
            <p className="text-[10px] text-slate-400">
              {webSearchEnabled
                ? `${agentName} effectuera 3–5 recherches Google, synthétisera les résultats et les sauvegardera dans ses skills.`
                : "Ajoutez SERPER_API_KEY=xxx dans backend/.env pour activer la recherche Google (gratuit sur serper.dev)."}
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
              <pre className="p-4 text-xs font-mono text-slate-700 whitespace-pre-wrap leading-relaxed">
                {fileContent}
              </pre>
            ) : (
              <div className="p-2">
                {entries.length === 0 ? (
                  <p className="text-xs text-slate-400 text-center py-8">Répertoire vide</p>
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
                        {new Date(entry.modified).toLocaleDateString("fr-FR")}
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
