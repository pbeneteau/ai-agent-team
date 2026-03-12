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

export type ChatPanelMode = "chat" | "team-builder";

export interface ChatHomePrompt {
  id: string;
  title: string;
  description: string;
  prompt: string;
  Icon: LucideIcon;
}

export interface ChatWorkspaceLink {
  href: string;
  label: string;
  description: string;
  Icon: LucideIcon;
  mode: ChatPanelMode;
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

const TEAM_BUILDER_HOME_PROMPTS: ChatHomePrompt[] = [
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

const WORKSPACE_LINKS: ChatWorkspaceLink[] = [
  {
    href: "/chat",
    label: "Alex orchestration",
    description: "Scope tasks, arbitrate, and define next actions.",
    Icon: MessageSquarePlus,
    mode: "chat",
  },
  {
    href: "/team-builder",
    label: "Alex team design",
    description: "Design or evolve the agent structure.",
    Icon: Users2,
    mode: "team-builder",
  },
];

export function getChatHomePrompts(mode: ChatPanelMode): ChatHomePrompt[] {
  return mode === "team-builder" ? TEAM_BUILDER_HOME_PROMPTS : CHAT_HOME_PROMPTS;
}

export function getWorkspaceLinks(): ChatWorkspaceLink[] {
  return WORKSPACE_LINKS;
}
