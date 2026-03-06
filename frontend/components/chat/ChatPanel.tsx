"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { Send, Bot, User, Loader2, Paperclip, FileText, Trash2, ChevronDown, ChevronUp, X, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { WSClient, createChatWS, createTeamBuilderWS } from "@/lib/websocket";
import { api, Document } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant" | "error";
  content: string;
  streaming?: boolean;
}

type ChatMode = "chat" | "team-builder";

interface FormField {
  id: string;
  label: string;
  type: "text" | "textarea" | "select";
  placeholder?: string;
  options?: string[];
  required?: boolean;
}

interface PlanCard {
  title: string;
  description?: string;
  fields: FormField[];
}

interface ChatPanelProps {
  onTaskCreated?: (task: unknown) => void;
}

function extractPlanCard(content: string): PlanCard | null {
  const match = content.match(/```json\s*\n([\s\S]*?)\n```/);
  if (!match) return null;
  try {
    const parsed = JSON.parse(match[1]);
    if (parsed.action === "gather_info" && Array.isArray(parsed.fields)) {
      return { title: parsed.title || "Informations requises", description: parsed.description, fields: parsed.fields };
    }
  } catch {}
  return null;
}

const STORAGE_KEY = "alex_chat_history";
const MAX_STORED = 60;
const DEFAULT_MESSAGES: Message[] = [{
  role: "assistant",
  content: "Bonjour ! Je suis Alex, votre associé IA. Je suis là pour vous aider à construire et gérer votre équipe. Commencez par me parler de votre projet — qu'est-ce que vous créez ?",
}];

function loadHistory(): Message[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as Message[];
  } catch {}
  return DEFAULT_MESSAGES;
}

function saveHistory(messages: Message[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_STORED)));
  } catch {}
}

export function ChatPanel({ onTaskCreated }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>(DEFAULT_MESSAGES);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [input, setInput] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [mode, setMode] = useState<ChatMode>("chat");
  const [planCard, setPlanCard] = useState<PlanCard | null>(null);
  const [planValues, setPlanValues] = useState<Record<string, string>>({});
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [showDocs, setShowDocs] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [taggedDocs, setTaggedDocs] = useState<Document[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const wsRef = useRef<WSClient | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadDocuments = useCallback(() => {
    api.getDocuments().then(setDocuments).catch(() => {});
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const handleSubmitPlan = useCallback(() => {
    if (!planCard) return;
    const missing = planCard.fields.filter((f) => f.required && !planValues[f.id]);
    if (missing.length) return;
    const summary = planCard.fields
      .map((f) => `**${f.label}** : ${planValues[f.id] || "(non renseigné)"}`)
      .join("\n");
    const userMsg = `Voici mes réponses pour "${planCard.title}":\n${summary}`;
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setPlanCard(null);
    setPlanValues({});
    wsRef.current?.send({ type: "form_response", values: planValues, form_title: planCard.title });
  }, [planCard, planValues]);

  const uploadFile = useCallback(async (file: File) => {
    setIsUploading(true);
    setShowDocs(true);
    try {
      await api.uploadDocument(file);
      loadDocuments();
    } catch (err) {
      console.error("Upload failed:", err);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [loadDocuments]);

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
  }, [uploadFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) uploadFile(file);
  }, [uploadFile]);

  // --- @ mention logic ---

  const mentionSuggestions = useMemo(() => {
    if (mentionQuery === null) return [];
    const q = mentionQuery.toLowerCase();
    return documents.filter((d) => d.filename.toLowerCase().includes(q)).slice(0, 6);
  }, [mentionQuery, documents]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInput(val);

    // Detect @ trigger: look at the word right before the cursor
    const cursor = e.target.selectionStart ?? val.length;
    const textBeforeCursor = val.slice(0, cursor);
    const match = textBeforeCursor.match(/@([\w.\-]*)$/);
    if (match) {
      setMentionQuery(match[1]); // empty string = show all
    } else {
      setMentionQuery(null);
    }
  }, []);

  const selectMention = useCallback((doc: Document) => {
    // Remove the @query text from the input
    const cursor = textareaRef.current?.selectionStart ?? input.length;
    const before = input.slice(0, cursor).replace(/@[\w.\-]*$/, "");
    const after = input.slice(cursor);
    setInput(before + after);
    setMentionQuery(null);

    // Add to tagged docs if not already there
    setTaggedDocs((prev) =>
      prev.find((d) => d.id === doc.id) ? prev : [...prev, doc]
    );
    textareaRef.current?.focus();
  }, [input]);

  const removeTaggedDoc = useCallback((id: string) => {
    setTaggedDocs((prev) => prev.filter((d) => d.id !== id));
  }, []);

  const handleDeleteDocument = useCallback(async (id: string, filename: string) => {
    if (!confirm(`Supprimer le document "${filename}" ? Cette action est irréversible.`)) return;
    await api.deleteDocument(id).catch(() => {});
    loadDocuments();
  }, [loadDocuments]);

  const [briefingDocId, setBriefingDocId] = useState<string | null>(null);

  useEffect(() => {
    setMessages(loadHistory());
    setHistoryLoaded(true);
  }, []);

  const handleBriefAgents = useCallback(async (doc: Document) => {
    setBriefingDocId(doc.id);
    try {
      await api.briefAgentsWithDocument(doc.id);
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: `📚 Je mets à jour le **project_context** de tous les agents avec le contenu de **${doc.filename}**. Chaque agent recevra les informations pertinentes pour son rôle dans les prochaines secondes.`,
      }]);
    } catch {
      // silent
    } finally {
      setBriefingDocId(null);
    }
  }, []);

  // Persist messages to localStorage whenever they change
  useEffect(() => {
    if (!historyLoaded) return;
    saveHistory(messages.filter((m) => !m.streaming));
  }, [historyLoaded, messages]);

  // Connect/reconnect WS when mode changes
  useEffect(() => {
    const ws = mode === "team-builder" ? createTeamBuilderWS() : createChatWS();
    wsRef.current = ws;
    ws.connect();

    const unsub = ws.onMessage((msg) => {
      if (msg.type === "stream_start") {
        setIsStreaming(true);
        setMessages((prev) => [...prev, { role: "assistant", content: "", streaming: true }]);
      } else if (msg.type === "stream_chunk") {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.streaming) {
            return [...prev.slice(0, -1), { ...last, content: last.content + (msg.data as string) }];
          }
          return prev;
        });
      } else if (msg.type === "stream_end") {
        setIsStreaming(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.streaming) {
            return [...prev.slice(0, -1), { ...last, streaming: false }];
          }
          return prev;
        });
        // After stream ends, check if the last message contains a gather_info action
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant") {
            const plan = extractPlanCard(last.content);
            if (plan) setTimeout(() => setPlanCard(plan), 100);
          }
          return prev;
        });
      } else if (msg.type === "error") {
        setIsStreaming(false);
        setMessages((prev) => {
          const filtered = prev[prev.length - 1]?.streaming ? prev.slice(0, -1) : prev;
          return [...filtered, { role: "error", content: msg.data as string }];
        });
      } else if (msg.type === "navigate") {
        const to = (msg.data as { to: string }).to;
        if (to === "team-builder") {
          // Switch to team-builder mode inline — no extra message, Alex's response already handles the transition
          setMode("team-builder");
        }
      } else if (msg.type === "team_confirmed") {
        setMessages((prev) => [...prev, {
          role: "assistant",
          content: "✅ Proposition d'équipe validée. Confirmation de la création…",
        }]);
        wsRef.current?.send({ type: "confirm_team" });
      } else if (msg.type === "team_created") {
        setMode("chat");
        setPlanCard(null);
        setMessages((prev) => [...prev, {
          role: "assistant",
          content: "🎉 Équipe créée avec succès ! Vos agents sont en cours d'initialisation. Vous pouvez les voir dans **Mon Équipe**.",
        }]);
      } else if (msg.type === "task_created" && onTaskCreated) {
        onTaskCreated(msg.data);
      }
    });

    const checkConnection = setInterval(() => {
      setIsConnected(ws.readyState === WebSocket.OPEN);
    }, 1000);

    return () => {
      unsub();
      clearInterval(checkConnection);
      ws.disconnect();
    };
  }, [mode, onTaskCreated]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(() => {
    const content = input.trim();
    if (!content || isStreaming) return;

    const displayContent = taggedDocs.length
      ? `${taggedDocs.map((d) => `@${d.filename}`).join(" ")} ${content}`
      : content;

    setMessages((prev) => [...prev, { role: "user", content: displayContent }]);
    wsRef.current?.send({
      type: "chat",
      content,
      tagged_doc_ids: taggedDocs.map((d) => d.id),
    });
    setInput("");
    setTaggedDocs([]);
    setMentionQuery(null);
  }, [input, isStreaming, taggedDocs]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div
      className={cn("flex flex-col h-full relative", isDragging && "ring-2 ring-inset ring-indigo-400")}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Always-mounted hidden file input — must not be inside a conditional block */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.txt,.md,.csv,.json,.yaml,.yml"
        className="hidden"
        onChange={handleFileInputChange}
      />

      {/* Drag overlay */}
      {isDragging && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-indigo-50/90 border-2 border-dashed border-indigo-400 rounded-lg pointer-events-none">
          <div className="text-center">
            <Paperclip className="w-10 h-10 text-indigo-500 mx-auto mb-2" />
            <p className="text-sm font-medium text-indigo-700">Déposez le fichier ici</p>
            <p className="text-xs text-indigo-500">PDF, DOCX, TXT, MD, CSV…</p>
          </div>
        </div>
      )}
      {/* Status bar */}
      <div className="flex items-center justify-between gap-2 px-4 py-2 border-b bg-slate-50">
        <div className="flex items-center gap-2">
          <div className={cn("w-2 h-2 rounded-full", isConnected ? "bg-green-500" : "bg-red-400")} />
          <span className="text-xs text-muted-foreground">
            {isConnected ? "Connecté à Alex" : "Reconnexion…"}
          </span>
          {mode === "team-builder" && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 text-xs font-medium">
              Mode création d&apos;équipe
              <button onClick={() => setMode("chat")} className="hover:text-violet-900 ml-0.5">
                <X className="w-3 h-3" />
              </button>
            </span>
          )}
        </div>
        <button
          onClick={() => setShowDocs((v) => !v)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <FileText className="w-3.5 h-3.5" />
          {documents.length > 0 ? `${documents.length} document(s)` : "Documents"}
          {showDocs ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      </div>

      {/* Documents panel */}
      {showDocs && (
        <div className="border-b bg-slate-50/80 px-4 py-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-600">Documents partagés avec Alex</span>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs gap-1.5"
              disabled={isUploading}
              onClick={() => fileInputRef.current?.click()}
            >
              {isUploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Paperclip className="w-3.5 h-3.5" />}
              {isUploading ? "Envoi…" : "Ajouter un fichier"}
            </Button>
          </div>
          {documents.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">
              Aucun document — glissez un PDF, DOCX ou texte pour donner du contexte à Alex.
            </p>
          ) : (
            <div className="space-y-1">
              {documents.map((doc) => (
                <div key={doc.id} className="flex items-center justify-between gap-2 rounded-md bg-white border px-3 py-1.5 text-xs">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                    <span className="truncate font-medium">{doc.filename}</span>
                    <span className="text-muted-foreground shrink-0">
                      {doc.chunk_count} chunk{doc.chunk_count !== 1 ? "s" : ""}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => handleBriefAgents(doc)}
                      disabled={briefingDocId === doc.id}
                      title="Partager comme contexte projet — met à jour le project_context de tous les agents"
                      className="text-muted-foreground hover:text-violet-600 transition-colors disabled:opacity-40"
                    >
                      {briefingDocId === doc.id
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <BookOpen className="w-3.5 h-3.5" />}
                    </button>
                    <button
                      onClick={() => handleDeleteDocument(doc.id, doc.filename)}
                      className="text-muted-foreground hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto min-h-0 p-4">
        <div className="space-y-4 max-w-3xl mx-auto">
          {messages.map((msg, i) => {
            if (msg.role === "error") {
              return (
                <div key={i} className="flex justify-center">
                  <div className="flex items-start gap-2 max-w-[90%] rounded-xl px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm">
                    <span className="shrink-0 mt-0.5">⚠️</span>
                    <span>{msg.content}</span>
                  </div>
                </div>
              );
            }
            return (
              <div
                key={i}
                className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}
              >
                {msg.role === "assistant" && (
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center flex-shrink-0 mt-1">
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                )}
                <div
                  className={cn(
                    "max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                    msg.role === "user"
                      ? "bg-indigo-600 text-white rounded-tr-sm"
                      : "bg-white border border-slate-200 text-slate-800 rounded-tl-sm shadow-sm"
                  )}
                >
                  <MessageContent content={msg.content} />
                  {msg.streaming && (
                    <span className="inline-block w-1 h-4 ml-1 bg-current animate-pulse rounded" />
                  )}
                </div>
                {msg.role === "user" && (
                  <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center flex-shrink-0 mt-1">
                    <User className="w-4 h-4 text-slate-600" />
                  </div>
                )}
              </div>
            );
          })}
          {/* Plan card — dynamic form when Alex needs structured input */}
          {planCard && (
            <div className="mx-auto max-w-2xl rounded-2xl border border-violet-200 bg-violet-50 p-5 space-y-4 shadow-sm">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shrink-0">
                  <Bot className="w-4 h-4 text-white" />
                </div>
                <div>
                  <p className="font-semibold text-slate-800 text-sm">{planCard.title}</p>
                  {planCard.description && <p className="text-xs text-slate-500 mt-0.5">{planCard.description}</p>}
                </div>
              </div>
              <div className="space-y-3">
                {planCard.fields.map((field) => (
                  <div key={field.id}>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      {field.label}{field.required && <span className="text-red-500 ml-0.5">*</span>}
                    </label>
                    {field.type === "select" && field.options ? (
                      <select
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
                        value={planValues[field.id] || ""}
                        onChange={(e) => setPlanValues((v) => ({ ...v, [field.id]: e.target.value }))}
                      >
                        <option value="">Choisir…</option>
                        {field.options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                      </select>
                    ) : field.type === "textarea" ? (
                      <textarea
                        rows={3}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-violet-400"
                        placeholder={field.placeholder}
                        value={planValues[field.id] || ""}
                        onChange={(e) => setPlanValues((v) => ({ ...v, [field.id]: e.target.value }))}
                      />
                    ) : (
                      <input
                        type="text"
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
                        placeholder={field.placeholder}
                        value={planValues[field.id] || ""}
                        onChange={(e) => setPlanValues((v) => ({ ...v, [field.id]: e.target.value }))}
                      />
                    )}
                  </div>
                ))}
              </div>
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => { setPlanCard(null); setPlanValues({}); }}
                  className="px-4 py-2 rounded-lg text-xs font-medium text-slate-600 hover:bg-white border border-slate-200 transition-colors"
                >
                  Annuler
                </button>
                <button
                  onClick={handleSubmitPlan}
                  className="px-4 py-2 rounded-lg text-xs font-medium bg-violet-600 text-white hover:bg-violet-700 transition-colors"
                >
                  Envoyer
                </button>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t p-4 bg-white">
        <div className="max-w-3xl mx-auto space-y-2">

          {/* Tagged document chips */}
          {taggedDocs.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {taggedDocs.map((doc) => (
                <span
                  key={doc.id}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-medium"
                >
                  <FileText className="w-3 h-3" />
                  {doc.filename}
                  <button onClick={() => removeTaggedDoc(doc.id)} className="hover:text-indigo-900 ml-0.5">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <div className="flex-1 relative">

              {/* @ mention dropdown */}
              {mentionQuery !== null && mentionSuggestions.length > 0 && (
                <div className="absolute bottom-full mb-1 left-0 w-72 bg-white border border-slate-200 rounded-lg shadow-lg z-50 overflow-hidden">
                  <div className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 uppercase tracking-wider border-b">
                    Documents
                  </div>
                  {mentionSuggestions.map((doc) => (
                    <button
                      key={doc.id}
                      onMouseDown={(e) => { e.preventDefault(); selectMention(doc); }}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-sm hover:bg-indigo-50 text-left transition-colors"
                    >
                      <FileText className="w-4 h-4 text-indigo-500 shrink-0" />
                      <span className="truncate font-medium">{doc.filename}</span>
                      <span className="text-xs text-slate-400 shrink-0 ml-auto">
                        {doc.chunk_count}c
                      </span>
                    </button>
                  ))}
                  {documents.length === 0 && (
                    <p className="px-3 py-2 text-xs text-slate-400 italic">
                      Aucun document — uploadez-en un avec le trombone.
                    </p>
                  )}
                </div>
              )}
              {mentionQuery !== null && documents.length === 0 && (
                <div className="absolute bottom-full mb-1 left-0 w-72 bg-white border border-slate-200 rounded-lg shadow-lg z-50 overflow-hidden">
                  <div className="px-3 py-2 text-xs text-slate-400 italic">
                    Aucun document disponible — uploadez-en un avec 📎.
                  </div>
                </div>
              )}

              <Textarea
                ref={textareaRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={(e) => {
                  if (mentionQuery !== null && mentionSuggestions.length > 0) {
                    if (e.key === "Escape") { e.preventDefault(); setMentionQuery(null); return; }
                    if (e.key === "Enter" && mentionSuggestions.length > 0) {
                      e.preventDefault(); selectMention(mentionSuggestions[0]); return;
                    }
                  }
                  handleKeyDown(e);
                }}
                placeholder="Écrivez à Alex… (@ pour citer un document, Entrée pour envoyer)"
                className="resize-none min-h-[60px] max-h-[160px] pr-10"
                disabled={isStreaming}
              />
              <button
                title="Joindre un document"
                disabled={isUploading}
                onClick={() => fileInputRef.current?.click()}
                className="absolute bottom-2 right-2 text-muted-foreground hover:text-indigo-600 transition-colors disabled:opacity-40"
              >
                {isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Paperclip className="w-4 h-4" />}
              </button>
            </div>
            <Button
              onClick={sendMessage}
              disabled={!input.trim() || isStreaming || !isConnected}
              className="self-end bg-indigo-600 hover:bg-indigo-700"
            >
              {isStreaming ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageContent({ content }: { content: string }) {
  // Strip JSON code blocks from display
  const cleaned = content.replace(/```json[\s\S]*?```/g, "").trim();
  return <span className="whitespace-pre-wrap">{cleaned || content}</span>;
}
