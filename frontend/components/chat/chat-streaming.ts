"use client";

import type { LucideIcon } from "lucide-react";
import { BookOpenText, Code2, ListChecks, Sparkles } from "lucide-react";

export type ChatMessageRole = "user" | "assistant" | "error";
export type ChatRequestKind = "code" | "document" | "plan" | "general";

export interface ChatMessage {
  id: string;
  role: ChatMessageRole;
  content: string;
  createdAt: string;
  interrupted?: boolean;
}

export interface ChatMessageSeed {
  role: ChatMessageRole;
  content: string;
  interrupted?: boolean;
}

export interface ChatPendingRequest {
  kind: ChatRequestKind;
  label: string;
  detail: string;
  Icon: LucideIcon;
}

interface PendingCopy {
  label: string;
  detail: string;
  Icon: LucideIcon;
}

const CODE_PATTERN =
  /\b(code|bug|debug|error|refactor|function|component|script|regex|api|sql|tsx|ts|jsx|js|python|backend|frontend)\b/i;
const PLAN_PATTERN =
  /\b(plan|roadmap|step|task|team|agent|orchestration|organize)\b/i;
const DOCUMENT_PATTERN =
  /\b(document|pdf|brief|spec|context|notes?|source|sources?)\b/i;

const PENDING_COPY: Record<ChatRequestKind, PendingCopy> = {
  code: {
    label: "Alex is preparing a technical answer",
    detail: "He is formatting the code and explanations before showing them.",
    Icon: Code2,
  },
  document: {
    label: "Alex is reviewing the relevant context",
    detail: "He is filtering the documents and keeping only the relevant parts.",
    Icon: BookOpenText,
  },
  plan: {
    label: "Alex is structuring the next step",
    detail: "He is organizing a proposal that is clear, executable, and concise.",
    Icon: ListChecks,
  },
  general: {
    label: "Alex is drafting the response",
    detail: "He is assembling a clean response before displaying it.",
    Icon: Sparkles,
  },
};

let messageSequence = 0;

export function createChatMessage(seed: ChatMessageSeed & Partial<Pick<ChatMessage, "id" | "createdAt">>): ChatMessage {
  return {
    id: seed.id ?? `chat-message-${Date.now()}-${messageSequence++}`,
    role: seed.role,
    content: seed.content,
    createdAt: seed.createdAt ?? new Date().toISOString(),
    interrupted: seed.interrupted,
  };
}

export function normalizeChatHistory(raw: unknown, fallback: ChatMessageSeed[]): ChatMessage[] {
  if (!Array.isArray(raw)) {
    return fallback.map((message) => createChatMessage(message));
  }

  const normalized = raw
    .filter((entry): entry is Record<string, unknown> => typeof entry === "object" && entry !== null)
    .map((entry) => {
      const role = entry.role;
      const content = entry.content;
      if ((role !== "user" && role !== "assistant" && role !== "error") || typeof content !== "string") {
        return null;
      }
      return createChatMessage({
        id: typeof entry.id === "string" ? entry.id : undefined,
        createdAt: typeof entry.createdAt === "string" ? entry.createdAt : undefined,
        role,
        content,
        interrupted: entry.interrupted === true,
      });
    })
    .filter((message): message is ChatMessage => message !== null);

  return normalized.length > 0 ? normalized : fallback.map((message) => createChatMessage(message));
}

export function isSeedHistory(messages: ChatMessage[], seeds: ChatMessageSeed[]): boolean {
  if (messages.length !== seeds.length) {
    return false;
  }

  return messages.every((message, index) => {
    const seed = seeds[index];
    return Boolean(seed) && message.role === seed.role && message.content === seed.content && !message.interrupted;
  });
}

export function buildPendingRequestMeta(options: {
  content: string;
  taggedDocumentCount?: number;
  source?: "chat" | "form" | "revision" | "confirm";
}): ChatPendingRequest {
  const { content, taggedDocumentCount = 0, source = "chat" } = options;

  if (source !== "chat") {
    return { kind: "plan", ...PENDING_COPY.plan };
  }

  if (taggedDocumentCount > 0 || DOCUMENT_PATTERN.test(content)) {
    return { kind: "document", ...PENDING_COPY.document };
  }

  if (CODE_PATTERN.test(content) || content.includes("```")) {
    return { kind: "code", ...PENDING_COPY.code };
  }

  if (PLAN_PATTERN.test(content)) {
    return { kind: "plan", ...PENDING_COPY.plan };
  }

  return { kind: "general", ...PENDING_COPY.general };
}

export function shouldHoldStreamingPreview(content: string): boolean {
  const trimmed = content.trim();
  if (!trimmed) {
    return true;
  }

  if (/^```[\w-]*\s*$/.test(trimmed)) {
    return true;
  }

  if (trimmed.startsWith("```") && !trimmed.includes("\n```")) {
    return true;
  }

  if ((trimmed.startsWith("{") || trimmed.startsWith("[")) && trimmed.length < 220) {
    return true;
  }

  if (trimmed.startsWith("---") && trimmed.length < 160) {
    return true;
  }

  const symbolMatches = trimmed.match(/[{}[\]`:_<>]/g);
  const symbolRatio = symbolMatches ? symbolMatches.length / trimmed.length : 0;
  return trimmed.length < 80 && symbolRatio > 0.18;
}
