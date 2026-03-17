"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ChatComposerPanel } from "@/components/chat/ChatComposerPanel";
import { ChatHomeState } from "@/components/chat/ChatHomeState";
import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import { ChatPlanDock } from "@/components/chat/ChatPlanDock";
import { ChatSurfaceHeader } from "@/components/chat/ChatSurfaceHeader";
import { ChatWorkspaceSidebar } from "@/components/chat/ChatWorkspaceSidebar";
import { buildAlexWorkspaceHref, type ChatEntryView, type ChatPanelMode } from "@/components/chat/chat-shell";
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
import { api, type Document } from "@/lib/api";
import { createChatWS, type ChatWSMessage, type WSClient } from "@/lib/websocket";
import { cn } from "@/lib/utils";

interface ChatPanelProps {
  onTaskCreated?: (task: unknown) => void;
  onTeamCreated?: (result: unknown) => void;
  storageKey?: string;
  historyKeys?: string[];
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

function loadHistory(storageKeys: string[], fallback: ChatMessageSeed[]): ChatMessage[] {
  if (typeof window === "undefined") {
    return fallback.map((message) => createChatMessage(message));
  }
  try {
    for (const storageKey of storageKeys) {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        return normalizeChatHistory(JSON.parse(raw), fallback);
      }
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
  historyKeys,
  initialMessages = DEFAULT_MESSAGES,
  mode = "chat",
  inputPlaceholder = "Write to Alex… (@ to cite a document, Enter to send)",
  title = "Alex",
  description = "Scoping and orchestration surface for turning a need into an explicit plan, useful sources, and a clear next action.",
  contextLabel = "Primary orchestration",
}: ChatPanelProps) {
  const effectiveHistoryKeys = useMemo(() => historyKeys ?? [storageKey], [historyKeys, storageKey]);
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadHistory(effectiveHistoryKeys, initialMessages));
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
  const chatEntryView: ChatEntryView =
    mode === "chat" && searchParams.get("view") === "ask" ? "ask" : "plan";

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
      effectiveHistoryKeys.forEach((key) => localStorage.removeItem(key));
    } catch {}
  }, [effectiveHistoryKeys, initialMessages, transitionPlan]);

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
          if (msg.data?.to === "team-builder" || msg.data?.to === "design-team") {
            router.push(buildAlexWorkspaceHref({ mode: "design-team" }));
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
              content: "Team created successfully. You can find it in Organization.",
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
  const statusLabel = showPlanPanel
    ? "Plan in progress"
    : isStreaming
      ? "Response in progress"
      : showHomeState
        ? "Home"
        : "Active conversation";
  const workflowLabel =
    mode === "design-team"
      ? "Design Team"
      : chatEntryView === "ask"
        ? "Ask Alex"
        : "Plan Work";
  const planPhaseLabel =
    planState.phase === "form"
      ? "Guided form"
      : planState.phase === "review"
        ? "Review"
        : planState.phase === "executing"
          ? "Executing"
          : planState.phase === "revising"
            ? "Revising"
            : "Draft";
  const planDockTitle =
    mode === "design-team" ? "Review the team before creation" : "Review the plan before launch";
  const planDockDescription =
    mode === "design-team"
      ? "Alex keeps team design in the main workflow and waits for explicit confirmation before creation."
      : "Planning remains explicit and backend-authoritative before any task is launched.";

  return (
    <div
      data-page-archetype="conversation"
      className={cn("relative flex h-full min-h-0 flex-col overflow-hidden bg-[var(--ops-canvas)]")}
    >
      <div className="min-h-0 flex-1 px-3 py-3 md:px-4 md:py-4 lg:px-5 lg:py-5">
        <div className="mx-auto flex h-full max-w-[1600px] overflow-hidden rounded-[22px] border border-[var(--ops-border)] bg-[var(--ops-surface)] shadow-[0_12px_28px_-24px_rgba(15,23,42,0.16)]">
          <ChatWorkspaceSidebar
            mode={mode}
            title={title}
            description={description}
            contextLabel={contextLabel}
            showDocs={showDocs}
            documents={documents}
            attachedDocuments={activeTaggedDocs}
          />

          <div className="flex min-w-0 flex-1 flex-col bg-[color:rgba(249,247,241,0.92)]">
            <ChatSurfaceHeader
              mode={mode}
              workflowLabel={workflowLabel}
              statusLabel={statusLabel}
              isConnected={isConnected}
              showDocs={showDocs}
              documentCount={documents.length}
              attachedDocumentCount={activeTaggedDocs.length}
              onToggleDocs={() => setShowDocs((value) => !value)}
              onResetConversation={resetConversation}
            />

            <div
              className={cn(
                "min-h-0 flex-1",
                showPlanPanel && "flex flex-col xl:grid xl:grid-cols-[minmax(360px,440px)_minmax(0,1fr)]",
              )}
            >
              {showPlanPanel ? (
                <div className="border-b border-[var(--ops-border)] bg-[var(--ops-surface-muted)] px-5 py-4 md:px-6 xl:border-b-0 xl:border-r xl:px-5 xl:py-5">
                  <ChatPlanDock
                    eyebrow={mode === "design-team" ? "Team design workflow" : "Planning workflow"}
                    title={planDockTitle}
                    description={planDockDescription}
                    phaseLabel={planPhaseLabel}
                    backendState={planState.backendState}
                    attachedDocumentCount={activeTaggedDocs.length}
                  >
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
                  </ChatPlanDock>
                </div>
              ) : null}

              <div className="relative min-h-0 flex-1">
                {showHomeState ? (
                  <ChatHomeState
                    mode={mode}
                    view={chatEntryView}
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
                    <div className="mx-auto flex min-h-full max-w-4xl flex-col gap-4 px-5 py-6 md:px-7">
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
            </div>

            <ChatComposerPanel
              textareaRef={textareaRef}
              input={input}
              inputPlaceholder={inputPlaceholder}
              isStreaming={isStreaming}
              isConnected={isConnected}
              documents={documents}
              activeTaggedDocs={activeTaggedDocs}
              mentionQuery={mentionQuery}
              mentionSuggestions={mentionSuggestions}
              onInputChange={handleInputChange}
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
              onSelectMention={selectMention}
              onRemoveTaggedDoc={removeTaggedDoc}
              onSendMessage={sendMessage}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
