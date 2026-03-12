import type { LucideIcon } from "lucide-react";
import {
  BarChart2,
  BookOpenText,
  Cable,
  LayoutDashboard,
  ListTodo,
  MessageSquare,
  Users,
} from "lucide-react";

export interface NavigationItem {
  href: string;
  icon: LucideIcon;
  label: string;
  description: string;
  aliases: RegExp[];
}

export const SIDEBAR_NAV_ITEMS: NavigationItem[] = [
  {
    href: "/",
    icon: LayoutDashboard,
    label: "Operations",
    description: "Daily control center",
    aliases: [/^\/$/],
  },
  {
    href: "/chat",
    icon: MessageSquare,
    label: "Alex",
    description: "Plan, arbitrate, launch",
    aliases: [/^\/chat(?:\/|$)/, /^\/team-builder(?:\/|$)/],
  },
  {
    href: "/project-context",
    icon: BookOpenText,
    label: "Brief & Documents",
    description: "Project source of truth",
    aliases: [/^\/project-context(?:\/|$)/],
  },
  {
    href: "/team",
    icon: Users,
    label: "Teams & Agents",
    description: "Structure, readiness, workspaces",
    aliases: [/^\/team(?:\/|$)/],
  },
  {
    href: "/tasks",
    icon: ListTodo,
    label: "Tasks",
    description: "Plans, execution, deliverables",
    aliases: [/^\/tasks(?:\/|$)/],
  },
  {
    href: "/connections",
    icon: Cable,
    label: "Connections",
    description: "MCP servers and tool access",
    aliases: [/^\/connections(?:\/|$)/],
  },
  {
    href: "/usage",
    icon: BarChart2,
    label: "AI Observability",
    description: "Costs, flows, diagnostics",
    aliases: [/^\/usage(?:\/|$)/],
  },
];
