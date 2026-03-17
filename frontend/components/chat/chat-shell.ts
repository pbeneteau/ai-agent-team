"use client";

import type { LucideIcon } from "lucide-react";
import {
  BookOpenText,
  ClipboardList,
  Compass,
  FolderKanban,
  MessageSquarePlus,
  Network,
  Users2,
} from "lucide-react";

import { getAlexWorkspaceLinks, type ProductNavItem } from "@/lib/config/product-navigation";

export type ChatPanelMode = "chat" | "design-team";
export type ChatEntryView = "plan" | "ask";
export interface AlexWorkspaceHrefOptions {
  view?: ChatEntryView;
  mode?: ChatPanelMode;
  docId?: string;
}

export interface ChatHomePrompt {
  id: string;
  title: string;
  description: string;
  prompt: string;
  Icon: LucideIcon;
}

const CHAT_HOME_PROMPTS: ChatHomePrompt[] = [
  {
    id: "scope-task",
    title: "Scope a task",
    description: "Turn an idea into a clear objective, deliverable, and execution path.",
    prompt:
      "Help me scope a new team task: objective, expected deliverable, constraints, and the right assignment.",
    Icon: ClipboardList,
  },
  {
    id: "brief-agents",
    title: "Brief the agents",
    description: "Prepare a useful instruction set before starting execution.",
    prompt:
      "Help me write a clear briefing for the agents covering the project, expectations, and guardrails.",
    Icon: Network,
  },
  {
    id: "use-document",
    title: "Use a document",
    description: "Turn a document into decisions, actions, and reusable context.",
    prompt:
      "I have a document to share. Help me extract the key decisions, constraints, and useful next actions.",
    Icon: BookOpenText,
  },
  {
    id: "organize-next",
    title: "Organize what comes next",
    description: "Clarify next steps and distribute the work.",
    prompt:
      "Help me organize the next project steps and distribute the work across the agents.",
    Icon: FolderKanban,
  },
];

const ASK_ALEX_HOME_PROMPTS: ChatHomePrompt[] = [
  {
    id: "clarify-direction",
    title: "Clarify direction",
    description: "Pressure-test a choice before committing execution capacity.",
    prompt: "I need a sharp recommendation between several directions. Help me decide and explain the trade-offs.",
    Icon: Compass,
  },
  {
    id: "review-signal",
    title: "Review a signal",
    description: "Interpret a blocker, warning, or runtime signal quickly.",
    prompt: "Help me understand this blocker or signal, what it means, and what I should do next.",
    Icon: ClipboardList,
  },
  {
    id: "read-document",
    title: "Interrogate a document",
    description: "Use Alex as a fast analytical layer over existing context.",
    prompt: "I want to ask targeted questions about a document or brief and get concise operator guidance.",
    Icon: BookOpenText,
  },
  {
    id: "operator-brief",
    title: "Get operator guidance",
    description: "Ask for the next action without launching a broader planning sequence.",
    prompt: "Given the current project state, what is the smartest next operator move right now?",
    Icon: MessageSquarePlus,
  },
];

const DESIGN_TEAM_HOME_PROMPTS: ChatHomePrompt[] = [
  {
    id: "mvp-team",
    title: "Compose an MVP team",
    description: "Define the minimum useful team to start quickly and cleanly.",
    prompt:
      "Help me define a minimal agent team to launch the project with the right roles.",
    Icon: Users2,
  },
  {
    id: "role-map",
    title: "Define the roles",
    description: "Identify specializations, interfaces, and responsibilities.",
    prompt:
      "Help me define the roles, specializations, and responsibility boundaries of the agent team.",
    Icon: ClipboardList,
  },
  {
    id: "launch-coverage",
    title: "Cover a launch",
    description: "Prepare a coherent team around a concrete business need.",
    prompt:
      "I am preparing a launch. Propose a coherent agent team to cover strategy, execution, and follow-through.",
    Icon: Compass,
  },
  {
    id: "doc-driven-team",
    title: "Start from a document",
    description: "Build the ideal team from a brief or project spec.",
    prompt:
      "Using a project brief, help me determine which agents to create and how to organize them.",
    Icon: BookOpenText,
  },
];

function getWorkspaceLinkIcon(itemId: string): LucideIcon {
  switch (itemId) {
    case "plan-work":
      return MessageSquarePlus;
    case "design-team":
      return Users2;
    case "ask-alex":
      return Compass;
    default:
      return FolderKanban;
  }
}

export interface ChatWorkspaceLink extends ProductNavItem {
  Icon: LucideIcon;
  mode: ChatPanelMode;
}

export function buildAlexWorkspaceHref({
  view = "plan",
  mode = "chat",
  docId,
}: AlexWorkspaceHrefOptions = {}): string {
  const params = new URLSearchParams();

  if (mode === "design-team") {
    params.set("mode", "design-team");
  }
  if (mode === "chat" && view === "ask") {
    params.set("view", "ask");
  }
  if (docId) {
    params.set("doc", docId);
  }

  const query = params.toString();
  return query ? `/chat?${query}` : "/chat";
}

export function getChatHomePrompts(mode: ChatPanelMode, view: ChatEntryView = "plan"): ChatHomePrompt[] {
  if (mode === "design-team") {
    return DESIGN_TEAM_HOME_PROMPTS;
  }
  return view === "ask" ? ASK_ALEX_HOME_PROMPTS : CHAT_HOME_PROMPTS;
}

export function getWorkspaceLinks(): ChatWorkspaceLink[] {
  return getAlexWorkspaceLinks().map((item) => ({
    ...item,
    Icon: getWorkspaceLinkIcon(item.id),
    mode: item.id === "design-team" ? "design-team" : "chat",
  }));
}
