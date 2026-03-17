import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpenText,
  Bot,
  Cable,
  Compass,
  LayoutDashboard,
  ListTodo,
  MessageSquare,
  ShieldCheck,
  Users,
} from "lucide-react";

export type ProductDomainId =
  | "command-center"
  | "alex"
  | "context"
  | "execution"
  | "organization"
  | "observability";

export interface ProductNavItem {
  id: string;
  href: string;
  label: string;
  description: string;
  aliases: RegExp[];
  icon?: LucideIcon;
  matchQuery?: Record<string, string>;
  isDefault?: boolean;
  inactiveQueryKeys?: string[];
}

export interface ProductDomain extends ProductNavItem {
  icon: LucideIcon;
}

type SearchLike = Pick<URLSearchParams, "get"> | null | undefined;

export const PRIMARY_PRODUCT_DOMAINS: ProductDomain[] = [
  {
    id: "command-center",
    href: "/",
    icon: LayoutDashboard,
    label: "Command Center",
    description: "Daily control and next actions",
    aliases: [/^\/$/],
  },
  {
    id: "alex",
    href: "/chat",
    icon: MessageSquare,
    label: "Alex",
    description: "Plan work, ask, and shape teams",
    aliases: [/^\/chat(?:\/|$)/, /^\/team-builder(?:\/|$)/],
  },
  {
    id: "context",
    href: "/project-context?section=brief",
    icon: BookOpenText,
    label: "Context",
    description: "Brief, documents, readiness",
    aliases: [/^\/project-context(?:\/|$)/],
  },
  {
    id: "execution",
    href: "/tasks?view=all",
    icon: ListTodo,
    label: "Execution",
    description: "Tasks, blockers, deliverables",
    aliases: [/^\/tasks(?:\/|$)/],
  },
  {
    id: "organization",
    href: "/team?section=teams",
    icon: Users,
    label: "Organization",
    description: "Teams, agents, structure",
    aliases: [/^\/team(?:\/|$)/],
  },
  {
    id: "observability",
    href: "/usage?section=overview",
    icon: Activity,
    label: "Observability",
    description: "Reliability, costs, infrastructure",
    aliases: [/^\/usage(?:\/|$)/, /^\/connections(?:\/|$)/],
  },
];

export const DOMAIN_SECONDARY_NAV: Record<ProductDomainId, ProductNavItem[]> = {
  "command-center": [],
  alex: [
    {
      id: "plan-work",
      href: "/chat",
      label: "Plan Work",
      description: "Turn a need into a clear plan and next actions.",
      aliases: [/^\/chat(?:\/|$)/],
      matchQuery: { view: "plan" },
      isDefault: true,
      inactiveQueryKeys: ["view", "mode"],
    },
    {
      id: "design-team",
      href: "/chat?mode=design-team",
      label: "Design Team",
      description: "Shape or evolve the operating team inside Alex.",
      aliases: [/^\/chat(?:\/|$)/, /^\/team-builder(?:\/|$)/],
      matchQuery: { mode: "design-team" },
    },
    {
      id: "ask-alex",
      href: "/chat?view=ask",
      label: "Ask Alex",
      description: "Use Alex as the direct operator-facing conversation surface.",
      aliases: [/^\/chat(?:\/|$)/],
      matchQuery: { view: "ask" },
    },
  ],
  context: [
    {
      id: "brief",
      href: "/project-context?section=brief",
      label: "Brief",
      description: "Published reference and current draft.",
      aliases: [/^\/project-context(?:\/|$)/],
      matchQuery: { section: "brief" },
      isDefault: true,
      inactiveQueryKeys: ["section"],
    },
    {
      id: "documents",
      href: "/project-context?section=documents",
      label: "Documents",
      description: "Shared library and agent briefing.",
      aliases: [/^\/project-context(?:\/|$)/],
      matchQuery: { section: "documents" },
    },
    {
      id: "readiness",
      href: "/project-context?section=readiness",
      label: "Readiness",
      description: "Agent context diagnostics.",
      aliases: [/^\/project-context(?:\/|$)/],
      matchQuery: { section: "readiness" },
    },
    {
      id: "recommendations",
      href: "/project-context?section=recommendations",
      label: "Recommendations",
      description: "Suggested team changes and staffing moves.",
      aliases: [/^\/project-context(?:\/|$)/],
      matchQuery: { section: "recommendations" },
    },
  ],
  execution: [
    {
      id: "all-tasks",
      href: "/tasks?view=all",
      label: "All Tasks",
      description: "Full execution portfolio.",
      aliases: [/^\/tasks(?:\/|$)/],
      matchQuery: { view: "all" },
      isDefault: true,
      inactiveQueryKeys: ["view"],
    },
    {
      id: "running",
      href: "/tasks?view=running",
      label: "Running",
      description: "Active executions in flight.",
      aliases: [/^\/tasks(?:\/|$)/],
      matchQuery: { view: "running" },
    },
    {
      id: "blocked",
      href: "/tasks?view=blocked",
      label: "Blocked",
      description: "Tasks waiting on a decision or fix.",
      aliases: [/^\/tasks(?:\/|$)/],
      matchQuery: { view: "blocked" },
    },
    {
      id: "completed",
      href: "/tasks?view=completed",
      label: "Completed",
      description: "Finished executions and deliverables.",
      aliases: [/^\/tasks(?:\/|$)/],
      matchQuery: { view: "completed" },
    },
  ],
  organization: [
    {
      id: "teams",
      href: "/team?section=teams",
      label: "Teams",
      description: "Operational groupings and structure.",
      aliases: [/^\/team(?:\/|$)/],
      matchQuery: { section: "teams" },
      isDefault: true,
      inactiveQueryKeys: ["section"],
    },
    {
      id: "agents",
      href: "/team?section=agents",
      label: "Agents",
      description: "Agent roster, readiness, and access.",
      aliases: [/^\/team(?:\/|$)/],
      matchQuery: { section: "agents" },
    },
  ],
  observability: [
    {
      id: "overview",
      href: "/usage?section=overview",
      label: "Overview",
      description: "Top-level health and signals.",
      aliases: [/^\/usage(?:\/|$)/],
      matchQuery: { section: "overview" },
      isDefault: true,
      inactiveQueryKeys: ["section"],
    },
    {
      id: "reliability",
      href: "/usage?section=reliability",
      label: "Reliability",
      description: "Flow failures, diagnostics, and action.",
      aliases: [/^\/usage(?:\/|$)/],
      matchQuery: { section: "reliability" },
    },
    {
      id: "costs",
      href: "/usage?section=costs",
      label: "Costs",
      description: "Spend and model coverage.",
      aliases: [/^\/usage(?:\/|$)/],
      matchQuery: { section: "costs" },
    },
    {
      id: "infrastructure",
      href: "/connections",
      label: "Infrastructure",
      description: "MCP and git provider setup.",
      aliases: [/^\/connections(?:\/|$)/],
    },
  ],
};

export function getPrimaryProductDomains(): ProductDomain[] {
  return PRIMARY_PRODUCT_DOMAINS;
}

export function getDomainSecondaryNav(domain: ProductDomainId): ProductNavItem[] {
  return DOMAIN_SECONDARY_NAV[domain];
}

export function getProductDomain(domain: ProductDomainId): ProductDomain {
  const match = PRIMARY_PRODUCT_DOMAINS.find((item) => item.id === domain);
  if (!match) {
    throw new Error(`Unknown product domain: ${domain}`);
  }
  return match;
}

export function getActiveItem<T extends ProductNavItem>(
  items: T[],
  pathname: string,
  searchParams?: SearchLike,
): T | null {
  return items.find((item) => isProductNavItemActive(item, pathname, searchParams)) ?? null;
}

export function getActivePrimaryDomain(pathname: string): ProductDomain {
  const match = PRIMARY_PRODUCT_DOMAINS.find((item) =>
    item.aliases.some((matcher) => matcher.test(pathname)),
  );
  return match ?? PRIMARY_PRODUCT_DOMAINS[0];
}

export function isProductNavItemActive(
  item: ProductNavItem,
  pathname: string,
  searchParams?: SearchLike,
): boolean {
  if (!item.aliases.some((matcher) => matcher.test(pathname))) {
    return false;
  }
  const hasInactiveQuery = item.inactiveQueryKeys?.some((key) => searchParams?.get(key) !== null) ?? false;
  if (!item.matchQuery) {
    return !hasInactiveQuery;
  }
  const matchesQuery = Object.entries(item.matchQuery).every(
    ([key, value]) => searchParams?.get(key) === value,
  );
  if (matchesQuery) {
    return true;
  }
  if (!item.isDefault) {
    return false;
  }
  if (hasInactiveQuery) {
    return false;
  }
  return Object.keys(item.matchQuery).every((key) => searchParams?.get(key) === null);
}

export function getAlexWorkspaceLinks(): ProductNavItem[] {
  return DOMAIN_SECONDARY_NAV.alex;
}

export function getDomainShortcut(domain: ProductDomainId, itemId: string): ProductNavItem | null {
  return DOMAIN_SECONDARY_NAV[domain].find((item) => item.id === itemId) ?? null;
}

export const OBSERVABILITY_INFRASTRUCTURE_ITEM = DOMAIN_SECONDARY_NAV.observability.find(
  (item) => item.id === "infrastructure",
);

export const OBSERVABILITY_OVERVIEW_ITEM = DOMAIN_SECONDARY_NAV.observability.find(
  (item) => item.id === "overview",
);

export const ALEX_PLAN_WORK_ITEM = DOMAIN_SECONDARY_NAV.alex.find(
  (item) => item.id === "plan-work",
);

export const ALEX_ASK_ITEM = DOMAIN_SECONDARY_NAV.alex.find((item) => item.id === "ask-alex");

export const ALEX_TEAM_DESIGN_ITEM = DOMAIN_SECONDARY_NAV.alex.find(
  (item) => item.id === "design-team",
);

export const CONTEXT_DOCUMENTS_ITEM = DOMAIN_SECONDARY_NAV.context.find(
  (item) => item.id === "documents",
);

export const EXECUTION_ALL_TASKS_ITEM = DOMAIN_SECONDARY_NAV.execution.find(
  (item) => item.id === "all-tasks",
);

export const ORGANIZATION_TEAMS_ITEM = DOMAIN_SECONDARY_NAV.organization.find(
  (item) => item.id === "teams",
);

export const OBSERVABILITY_COSTS_ITEM = DOMAIN_SECONDARY_NAV.observability.find(
  (item) => item.id === "costs",
);

export const OBSERVABILITY_RELIABILITY_ITEM = DOMAIN_SECONDARY_NAV.observability.find(
  (item) => item.id === "reliability",
);

export const COMMAND_CENTER_DOMAIN = getProductDomain("command-center");
export const ALEX_DOMAIN = getProductDomain("alex");
export const CONTEXT_DOMAIN = getProductDomain("context");
export const EXECUTION_DOMAIN = getProductDomain("execution");
export const ORGANIZATION_DOMAIN = getProductDomain("organization");
export const OBSERVABILITY_DOMAIN = getProductDomain("observability");

export const DOMAIN_LEAD_ICONS: Record<ProductDomainId, LucideIcon> = {
  "command-center": LayoutDashboard,
  alex: Bot,
  context: BookOpenText,
  execution: Compass,
  organization: Users,
  observability: ShieldCheck,
};

export const INFRASTRUCTURE_ICON = Cable;
