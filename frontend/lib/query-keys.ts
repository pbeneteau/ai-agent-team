/**
 * TanStack Query key factory.
 *
 * Ref: TDD-05 Section 4.1
 * Convention: [domain, action, ...params]
 */

import type { ArtifactFilters, RosterFilters } from "@/lib/types/api";

export const queryKeys = {
  // Roster
  roster: {
    all: () => ["roster"] as const,
    list: (filters?: RosterFilters) => ["roster", "list", filters] as const,
    detail: (id: string) => ["roster", id] as const,
    skills: (id: string, category?: string) => ["roster", id, "skills", category] as const,
    learningProfile: (id: string) => ["roster", id, "learning-profile"] as const,
    recommendations: (id: string) => ["roster", id, "recommendations"] as const,
    globalReadiness: () => ["roster", "readiness", "global"] as const,
  },

  // Projects
  projects: {
    all: () => ["projects"] as const,
    list: (cursor?: string) => ["projects", "list", cursor] as const,
    detail: (id: string) => ["projects", id] as const,
    context: (id: string) => ["projects", id, "context"] as const,
    documents: (id: string) => ["projects", id, "documents"] as const,
  },

  // Artifacts
  artifacts: {
    all: () => ["artifacts"] as const,
    list: (projectId: string, filters?: ArtifactFilters) =>
      ["artifacts", "list", projectId, filters] as const,
    detail: (id: string) => ["artifacts", id] as const,
    status: (id: string) => ["artifacts", id, "status"] as const,
    versions: (id: string) => ["artifacts", id, "versions"] as const,
    file: (id: string, version: number, path: string) =>
      ["artifacts", id, "versions", version, "files", path] as const,
  },

  // Integrations
  gitProviders: {
    all: () => ["git-providers"] as const,
    list: () => ["git-providers", "list"] as const,
    repos: (connectionId: string) => ["git-providers", connectionId, "repos"] as const,
  },

  mcp: {
    all: () => ["mcp"] as const,
    list: () => ["mcp", "list"] as const,
  },

  // Usage
  usage: {
    all: () => ["usage"] as const,
    stats: (period?: string) => ["usage", "stats", period] as const,
  },
} as const;
