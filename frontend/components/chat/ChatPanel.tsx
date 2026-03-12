"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookOpenText, FileText, Loader2, Send, X } from "lucide-react";

import { ChatHomeState } from "@/components/chat/ChatHomeState";
import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import { ChatSurfaceHeader } from "@/components/chat/ChatSurfaceHeader";
import { ChatWorkspaceSidebar } from "@/components/chat/ChatWorkspaceSidebar";
import type { ChatPanelMode } from "@/components/chat/chat-shell";
import {
  buildPendingRequestMeta,
  createChatMessage,
  isSeedHistory,
  normalizeChatHistory,
  shouldHoldStreamingPreview,
  type ChatMessage,
  type ChatMessageSeed,
  type ChatPendingRequest,
} from "@/components/chat/chat-streaming";
import {
  createInitialPlanState,
  planReducer,
  type PlanUiAction,
  type PlanUiState,
} from "@/components/chat/plan-state";
import { UniversalPlanPanel } from "@/components/chat/UniversalPlanPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { api, type Document } from "@/lib/api";
import { createChatWS, type ChatWSMessage, type WSClient } from "@/lib/websocket";
import { cn } from "@/lib/utils";

interface ChatPanelProps {
  onTaskCreated?: (task: unknown) => void;
  onTeamCreated?: (result: unknown) => void;
  storageKey?: string;
  initialMessages?: ChatMessageSeed[];
  mode?: ChatPanelMode;
  inputPlaceholder?: string;
  title?: string;
  description?: string;
  contextLabel?: string;
}

const MAX_STORED = 60;
const DEFAULT_MESSAGES: ChatMessageSeed[] = [
  {
    role: "assistant",
    content:
      "Hi! I’m Alex. I can scope the work, structure the team, and turn your context into explicit next actions. Where would you like to start?",
  },
];

function loadHistory(storageKey: string, fallback: ChatMessageSeed[]): ChatMessage[] {
  if (typeof window === "undefined") {
    return fallback.map((message) => createChatMessage(message));
  }
  try {
    const raw = localStorage.getItem(storageKey);
    if (raw) {
      return normalizeChatHistory(JSON.parse(raw), fallback);
    }
  } catch {}
  return fallback.map((message) => createChatMessage(message));
}

function saveHistory(storageKey: string, messages: ChatMessage[]) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    localStorage.setItem(storageKey, JSON.stringify(messages.slice(-MAX_STORED)));
  } catch {}
}

export function ChatPanel({
  onTaskCreated,
  onTeamCreated,
  storageKey = "alex_chat_history",
  initialMessages = DEFAULT_MESSAGES,
  mode = "chat",
  inputPlaceholder = "Write to Alex… (@ to cite a document, Enter to send)",
  title = "Alex",
  description = "Scoping and orchestration surface for turning a need into an explicit plan, useful sources, and a clear next action.",
  contextLabel = "Primary orchestration",
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadHistory(storageKey, initialMessages));
  const [streamingMessage, setStreamingMessage] = useState<ChatMessage | null>(null);
  const [input, setInput] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [planState, setPlanState] = useState<PlanUiState>(createInitialPlanState);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [showDocs, setShowDocs] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [taggedDocs, setTaggedDocs] = useState<Document[]>([]);
  const [pendingRequest, setPendingRequest] = useState<ChatPendingRequest | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const wsRef = useRef<WSClient<ChatWSMessage> | null>(null);
  const scrollViewportRef = useRef<HTMLDivElement>(null);
  const streamingMessageRef = useRef<ChatMessage | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const loadDocuments = useCallback(() => {
    api.getDocuments().then(setDocuments).catch(() => {});
  }, []);

  const appendUserMessage = useCallback(
    (content: string) => {
      const userMessage = createChatMessage({ role: "user", content });
      setMessages((prev) => (isSeedHistory(prev, initialMessages) ? [userMessage] : [...prev, userMessage]));
    },
    [initialMessages],
  );

  const transitionPlan = useCallback((action: PlanUiAction) => {
    setPlanState((current) => planReducer(current, action));
  }, []);

  const resetConversation = useCallback(() => {
    setMessages(initialMessages.map((message) => createChatMessage(message)));
    setStreamingMessage(null);
    streamingMessageRef.current = null;
    setPendingRequest(null);
    setIsStreaming(false);
    setInput("");
    setTaggedDocs([]);
    setMentionQuery(null);
    setShowDocs(false);
    transitionPlan({ type: "reset" });
    shouldAutoScrollRef.current = true;
    try {
      localStorage.removeItem(storageKey);
    } catch {}
  }, [initialMessages, storageKey, transitionPlan]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior) => {
    const viewport = scrollViewportRef.current;
    if (!viewport) {
      return;
    }
    viewport.scrollTo({ top: viewport.scrollHeight, behavior });
  }, []);

  const updateAutoScroll = useCallback(() => {
    const viewport = scrollViewportRef.current;
    if (!viewport) {
      return;
    }
    const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 96;
  }, []);

  const flushStreamingMessage = useCallback((options?: { interrupted?: boolean }) => {
    const current = streamingMessageRef.current;
    streamingMessageRef.current = null;
    setStreamingMessage(null);

    if (!current || !current.content.trim()) {
      return;
    }

    setMessages((prev) => [
      ...prev,
      options?.interrupted ? { ...current, interrupted: true } : current,
    ]);
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    shouldAutoScrollRef.current = true;
    scrollViewportRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [mode, storageKey]);

  useEffect(() => {
    saveHistory(storageKey, messages);
  }, [messages, storageKey]);

  const handleSubmitPlan = useCallback(() => {
    const form = planState.form;
    if (!form) {
      return;
    }
    const missing = form.fields.filter(
      (field) => field.required && !planState.formValues[field.id]?.trim(),
    );
    if (missing.length > 0) {
      return;
    }
    const summary = form.fields
      .map((field) => `${field.label}: ${planState.formValues[field.id] || "(not provided)"}`)
      .join("\n");
    appendUserMessage(`Here are my answers for "${form.title}":\n${summary}`);
    setPendingRequest(buildPendingRequestMeta({ content: form.title, source: "form" }));
    shouldAutoScrollRef.current = true;
    wsRef.current?.send({
      type: "form_response",
      values: planState.formValues,
      form_title: form.title,
    });
    transitionPlan({ type: "submit_form" });
  }, [appendUserMessage, planState.form, planState.formValues, transitionPlan]);

  const handleConfirmPlan = useCallback(() => {
    if (!planState.draft || !planState.sessionId) {
      return;
    }
    transitionPlan({ type: "request_confirm" });
    setPendingRequest(buildPendingRequestMeta({ content: planState.draft.title, source: "confirm" }));
    wsRef.current?.send({
      type: "plan_confirm",
      session_id: planState.sessionId,
      draft_id: planState.draft.id,
    });
  }, [planState.draft, planState.sessionId, transitionPlan]);

  const handleCancelPlan = useCallback(() => {
    if (planState.form && planState.phase === "form") {
      transitionPlan({ type: "reset" });
      return;
    }
    if (!planState.draft || !planState.sessionId) {
      transitionPlan({ type: "reset" });
      return;
    }
    wsRef.current?.send({
      type: "plan_cancel",
      session_id: planState.sessionId,
      draft_id: planState.draft.id,
    });
  }, [planState.draft, planState.form, planState.phase, planState.sessionId, transitionPlan]);

  const handleRevisePlan = useCallback(() => {
    if (!planState.draft || !planState.sessionId) {
      return;
    }
    const revision = planState.revisionText.trim();
    const clarificationEntries = Object.entries(planState.clarificationValues).filter(([, value]) => value.trim());
    const clarificationSummary =
      clarificationEntries.length > 0
        ? clarificationEntries.map(([field, value]) => `${field}: ${value}`).join("\n")
        : "";
    const message = [clarificationSummary, revision].filter(Boolean).join("\n");
    appendUserMessage(message || "Je veux une version revisee de cette proposition.");
    setPendingRequest(buildPendingRequestMeta({ content: revision || planState.draft.title, source: "revision" }));
    shouldAutoScrollRef.current = true;
    transitionPlan({ type: "revising", backendState: "discovery" });
    wsRef.current?.send({
      type: "plan_revise",
      session_id: planState.sessionId,
      draft_id: planState.draft.id,
      content: revision,
      clarification_values: planState.clarificationValues,
    });
  }, [
    appendUserMessage,
    planState.clarificationValues,
    planState.draft,
    planState.revisionText,
    planState.sessionId,
    transitionPlan,
  ]);

  const mentionSuggestions = useMemo(() => {
    if (mentionQuery === null) {
      return [];
    }
    const query = mentionQuery.toLowerCase();
    return documents.filter((document) => document.filename.toLowerCase().includes(query)).slice(0, 6);
  }, [documents, mentionQuery]);

  const requestedDocumentId = searchParams.get("doc");
  const requestedTaggedDocument = useMemo(() => {
    if (!requestedDocumentId) {
      return null;
    }
    return documents.find((document) => document.id === requestedDocumentId) ?? null;
  }, [documents, requestedDocumentId]);

  const activeTaggedDocs = useMemo(() => {
    if (!requestedTaggedDocument) {
      return taggedDocs;
    }
    return taggedDocs.some((document) => document.id === requestedTaggedDocument.id)
      ? taggedDocs
      : [...taggedDocs, requestedTaggedDocument];
  }, [requestedTaggedDocument, taggedDocs]);

  const clearRequestedDocumentParam = useCallback(() => {
    if (!requestedDocumentId) {
      return;
    }
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.delete("doc");
    const nextUrl = nextParams.size > 0 ? `${pathname}?${nextParams.toString()}` : pathname;
    router.replace(nextUrl, { scroll: false });
  }, [pathname, requestedDocumentId, router, searchParams]);

  useEffect(() => {
    if (!requestedTaggedDocument) {
      return;
    }

    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea) {
        return;
      }
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    });
  }, [requestedTaggedDocument]);

  const handleInputChange = useCallback((event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = event.target.value;
    setInput(value);
    const cursor = event.target.selectionStart ?? value.length;
    const textBeforeCursor = value.slice(0, cursor);
    const match = textBeforeCursor.match(/@([\w.\-]*)$/);
    setMentionQuery(match ? match[1] : null);
  }, []);

  const selectMention = useCallback(
    (document: Document) => {
      const cursor = textareaRef.current?.selectionStart ?? input.length;
      const before = input.slice(0, cursor).replace(/@[\w.\-]*$/, "");
      const after = input.slice(cursor);
      setInput(before + after);
      setMentionQuery(null);
      setTaggedDocs((prev) => (prev.find((entry) => entry.id === document.id) ? prev : [...prev, document]));
      textareaRef.current?.focus();
    },
    [input],
  );

  const removeTaggedDoc = useCallback((id: string) => {
    setTaggedDocs((prev) => prev.filter((document) => document.id !== id));
    if (requestedTaggedDocument?.id === id) {
      clearRequestedDocumentParam();
    }
  }, [clearRequestedDocumentParam, requestedTaggedDocument?.id]);

  useEffect(() => {
    const ws = createChatWS();
    wsRef.current = ws;
    ws.connect();

    const unsub = ws.onMessage((msg) => {
      switch (msg.type) {
        case "stream_start":
          setIsStreaming(true);
          shouldAutoScrollRef.current = true;
          {
            const nextMessage = createChatMessage({ role: "assistant", content: "" });
            streamingMessageRef.current = nextMessage;
            setStreamingMessage(nextMessage);
          }
          break;
        case "stream_chunk":
          setStreamingMessage((current) => {
            const nextMessage =
              current ??
              createChatMessage({
                role: "assistant",
                content: "",
              });
            const updated = {
              ...nextMessage,
              content: `${nextMessage.content}${String(msg.data ?? "")}`,
            };
            streamingMessageRef.current = updated;
            return updated;
          });
          break;
        case "stream_end":
          setIsStreaming(false);
          flushStreamingMessage();
          setPendingRequest(null);
          break;
        case "plan_form": {
          const payload = msg.data ?? {};
          setPendingRequest(null);
          transitionPlan({
            type: "show_form",
            sessionId: payload.session_id ?? null,
            form: payload.form ?? null,
          });
          break;
        }
        case "plan_preview": {
          const payload = msg.data ?? {};
          setPendingRequest(null);
          transitionPlan({
            type: "show_draft",
            sessionId: payload.session_id ?? null,
            backendState: payload.state ?? null,
            draft: payload.draft ?? null,
            error: payload.last_error ?? null,
          });
          break;
        }
        case "plan_revising":
          setPendingRequest(null);
          transitionPlan({ type: "revising", backendState: "discovery" });
          break;
        case "plan_executing":
          setPendingRequest(null);
          transitionPlan({ type: "executing", backendState: "executing" });
          break;
        case "plan_completed": {
          const payload = msg.data ?? {};
          setPendingRequest(null);
          transitionPlan({ type: "completed" });
          if (payload.kind === "team" && onTeamCreated) {
            onTeamCreated(payload.result);
          }
          setMessages((prev) => [
            ...prev,
            createChatMessage({
              role: "assistant",
              content:
                payload.kind === "team"
                  ? "The team has been created. I am now starting its initialization."
                  : "The task has been created and launched.",
            }),
          ]);
          shouldAutoScrollRef.current = true;
          break;
        }
        case "plan_cancelled":
          setPendingRequest(null);
          transitionPlan({ type: "cancelled", backendState: "cancelled" });
          break;
        case "plan_failed": {
          const payload = msg.data ?? {};
          setPendingRequest(null);
          transitionPlan({
            type: "failed",
            backendState: payload.state ?? null,
            error: payload.error ?? "Unknown error",
            draft: payload.draft ?? undefined,
          });
          break;
        }
        case "navigate":
          if (msg.data?.to === "team-builder") {
            router.push("/team-builder");
          }
          break;
        case "error":
          setIsStreaming(false);
          flushStreamingMessage({ interrupted: true });
          setPendingRequest(null);
          setMessages((prev) => {
            return [
              ...prev,
              createChatMessage({ role: "error", content: String(msg.data ?? "Unknown error") }),
            ];
          });
          break;
        case "team_created":
          if (onTeamCreated) {
            onTeamCreated(msg.data);
          }
          setMessages((prev) => [
            ...prev,
            createChatMessage({
              role: "assistant",
              content: "Team created successfully. You can find it in Teams & Agents.",
            }),
          ]);
          shouldAutoScrollRef.current = true;
          break;
        case "task_created":
          if (onTaskCreated) {
            onTaskCreated(msg.data);
          }
          break;
        default:
          break;
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
  }, [flushStreamingMessage, onTaskCreated, onTeamCreated, router, transitionPlan]);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return;
    }
    scrollToBottom(streamingMessage ? "auto" : "smooth");
  }, [messages, planState.draft, planState.form, scrollToBottom, showDocs, streamingMessage]);

  const sendMessage = useCallback(() => {
    const content = input.trim();
    if (!content || isStreaming) {
      return;
    }
    const displayContent = activeTaggedDocs.length > 0
      ? `${activeTaggedDocs.map((document) => `@${document.filename}`).join(" ")} ${content}`
      : content;
    appendUserMessage(displayContent);
    setPendingRequest(buildPendingRequestMeta({ content, taggedDocumentCount: activeTaggedDocs.length }));
    shouldAutoScrollRef.current = true;
    wsRef.current?.send({
      type: "chat",
      content,
      tagged_doc_ids: activeTaggedDocs.map((document) => document.id),
    });
    setInput("");
    setTaggedDocs([]);
    setMentionQuery(null);
    clearRequestedDocumentParam();
  }, [activeTaggedDocs, appendUserMessage, clearRequestedDocumentParam, input, isStreaming]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
      }
    },
    [sendMessage],
  );

  const showPlanPanel = planState.form !== null || planState.draft !== null;
  const showWaitingState = streamingMessage ? shouldHoldStreamingPreview(streamingMessage.content) : true;
  const showHomeState =
    !showPlanPanel &&
    !streamingMessage &&
    (messages.length === 0 || isSeedHistory(messages, initialMessages));
  const conversationStatusLabel = showPlanPanel
    ? "Plan in progress"
    : isStreaming
      ? "Response in progress"
      : showHomeState
        ? "Home"
        : "Active conversation";

  return (
    <div className={cn("relative flex h-full min-h-0 flex-col overflow-hidden bg-[var(--ops-canvas)]")}>
      <div className="min-h-0 flex-1 p-4 md:p-5">
        <div className="mx-auto flex h-full max-w-[1600px] overflow-hidden rounded-[30px] border border-[var(--ops-border)] bg-[var(--ops-surface)] shadow-[var(--ops-shadow)] backdrop-blur">
          <ChatWorkspaceSidebar
            mode={mode}
            title={title}
            description={description}
            contextLabel={contextLabel}
            showDocs={showDocs}
            documents={documents}
            attachedDocuments={activeTaggedDocs}
          />

          <div className="flex min-w-0 flex-1 flex-col bg-[radial-gradient(circle_at_top,rgba(255,255,253,0.98),rgba(247,244,237,0.9))]">
            <ChatSurfaceHeader
              mode={mode}
              contextLabel={conversationStatusLabel}
              isConnected={isConnected}
              showDocs={showDocs}
              documentCount={documents.length}
              attachedDocumentCount={activeTaggedDocs.length}
              onToggleDocs={() => setShowDocs((value) => !value)}
              onResetConversation={resetConversation}
            />

            {showPlanPanel ? (
              <div className="border-b border-black/5 bg-white/45 px-5 py-5 md:px-8">
                <div className="mx-auto max-w-4xl">
                  <UniversalPlanPanel
                    phase={planState.phase}
                    form={planState.form}
                    formValues={planState.formValues}
                    draft={planState.draft}
                    error={planState.error}
                    backendState={planState.backendState}
                    revisionText={planState.revisionText}
                    clarificationValues={planState.clarificationValues}
                    documentLabelsById={Object.fromEntries(documents.map((document) => [document.id, document.filename]))}
                    onFieldChange={(fieldId, value) => transitionPlan({ type: "update_form_value", fieldId, value })}
                    onFormCancel={() => transitionPlan({ type: "reset" })}
                    onFormSubmit={handleSubmitPlan}
                    onRevisionTextChange={(value) => transitionPlan({ type: "set_revision_text", value })}
                    onClarificationValueChange={(fieldPath, value) =>
                      transitionPlan({ type: "update_clarification_value", fieldPath, value })
                    }
                    onConfirm={handleConfirmPlan}
                    onCancel={handleCancelPlan}
                    onRevise={handleRevisePlan}
                  />
                </div>
              </div>
            ) : null}

            <div className="relative min-h-0 flex-1">
              {showHomeState ? (
                <ChatHomeState
                  mode={mode}
                  title={title}
                  description={description}
                  onSelectPrompt={(prompt) => {
                    setInput(prompt);
                    setMentionQuery(null);
                    requestAnimationFrame(() => {
                      const textarea = textareaRef.current;
                      if (!textarea) {
                        return;
                      }
                      textarea.focus();
                      textarea.scrollTop = 0;
                      textarea.scrollLeft = 0;
                      textarea.setSelectionRange(prompt.length, prompt.length);
                    });
                  }}
                />
              ) : (
                <div ref={scrollViewportRef} onScroll={updateAutoScroll} className="absolute inset-0 overflow-y-auto">
                  <div className="mx-auto flex min-h-full max-w-4xl flex-col gap-6 px-6 py-8 md:px-10">
                    {messages.map((message) => (
                      <ChatMessageBubble key={message.id} message={message} />
                    ))}

                    {streamingMessage ? (
                      <ChatMessageBubble
                        message={streamingMessage}
                        isStreaming
                        pendingRequest={pendingRequest ?? buildPendingRequestMeta({ content: "" })}
                        showWaitingState={showWaitingState}
                      />
                    ) : null}
                  </div>
                </div>
              )}
            </div>

            <div className="border-t border-black/5 bg-white/72 px-4 py-4 backdrop-blur md:px-6">
              <div className="mx-auto max-w-4xl space-y-3">
                {activeTaggedDocs.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {activeTaggedDocs.map((document) => (
                      <Badge
                        key={document.id}
                        variant="secondary"
                        className="h-auto gap-1 rounded-full bg-primary/8 px-2.5 py-1 text-primary"
                      >
                        <FileText className="size-3" />
                        {document.filename}
                        <button onClick={() => removeTaggedDoc(document.id)} className="rounded-full hover:text-primary/80">
                          <X className="size-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                ) : null}

                <div className="relative">
                  {mentionQuery !== null && mentionSuggestions.length > 0 ? (
                    <div className="absolute bottom-full left-0 z-30 mb-3 w-full max-w-sm">
                      <Card size="sm" className="gap-0 border border-black/6 bg-white shadow-[0_24px_40px_-32px_rgba(15,23,42,0.28)] ring-0">
                        <div className="border-b border-black/5 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                          Documents
                        </div>
                        <div className="p-1">
                          {mentionSuggestions.map((document) => (
                            <button
                              key={document.id}
                              onMouseDown={(event) => {
                                event.preventDefault();
                                selectMention(document);
                              }}
                              className="flex w-full items-center gap-2.5 rounded-2xl px-3 py-2 text-left text-sm transition-colors hover:bg-muted/70"
                            >
                              <FileText className="size-4 shrink-0 text-primary" />
                              <span className="truncate font-medium text-foreground">{document.filename}</span>
                              <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                                {document.chunk_count}c
                              </span>
                            </button>
                          ))}
                        </div>
                      </Card>
                    </div>
                  ) : null}

                  {mentionQuery !== null && documents.length === 0 ? (
                    <div className="absolute bottom-full left-0 z-30 mb-3 w-full max-w-sm">
                      <Card size="sm" className="bg-white shadow-[0_24px_40px_-32px_rgba(15,23,42,0.28)] ring-0">
                        <div className="space-y-2 px-3 py-3 text-sm text-muted-foreground">
                          <p>No document available. Open the context hub to add or manage sources.</p>
                          <Link href="/project-context" className="inline-flex text-xs font-medium text-primary hover:underline">
                            Go to project context
                          </Link>
                        </div>
                      </Card>
                    </div>
                  ) : null}

                  <div className="overflow-hidden rounded-[28px] border border-black/6 bg-white shadow-[0_22px_40px_-34px_rgba(15,23,42,0.28)]">
                    <Textarea
                      ref={textareaRef}
                      value={input}
                      onChange={handleInputChange}
                      onKeyDown={(event) => {
                        if (mentionQuery !== null && mentionSuggestions.length > 0) {
                          if (event.key === "Escape") {
                            event.preventDefault();
                            setMentionQuery(null);
                            return;
                          }
                          if (event.key === "Enter") {
                            event.preventDefault();
                            selectMention(mentionSuggestions[0]);
                            return;
                          }
                        }
                        handleKeyDown(event);
                      }}
                      placeholder={inputPlaceholder}
                      className="max-h-[220px] min-h-[104px] resize-none border-0 bg-transparent px-5 pb-16 pt-5 text-sm leading-6 shadow-none focus-visible:border-0 focus-visible:ring-0"
                      disabled={isStreaming}
                    />

                    <div className="flex flex-col gap-3 border-t border-black/5 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                        <span>@ to cite a document</span>
                        <span>Documents and broadcasts live in Project Context</span>
                        <span>Enter to send</span>
                        <span>Shift + Enter for a new line</span>
                      </div>

                      <div className="flex items-center justify-end gap-2">
                        <Link href="/project-context">
                          <Button variant="ghost" size="sm" className="rounded-2xl gap-2">
                            <BookOpenText className="size-4" />
                            Project context
                          </Button>
                        </Link>

                        <Button
                          onClick={sendMessage}
                          disabled={!input.trim() || isStreaming || !isConnected}
                          className="rounded-full px-4 shadow-sm"
                        >
                          {isStreaming ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                          {isStreaming ? "Alex is responding…" : "Send"}
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
