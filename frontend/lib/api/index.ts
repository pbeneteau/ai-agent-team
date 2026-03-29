/**
 * Unified API client — all domain methods.
 *
 * Ref: TDD-05 Section 5.2
 *
 * Usage:
 *   import { api } from "@/lib/api";
 *   const projects = await api.projects.list();
 */

import { request } from "@/lib/api-client";
import { artifacts, briefs } from "./artifacts";
import { gitProviders } from "./git-providers";
import { mcp } from "./mcp";
import { onboarding } from "./onboarding";
import { projects } from "./projects";
import { roster } from "./roster";
import { usage } from "./usage";
import { workspace } from "./workspace";
import type { HealthResponse } from "@/lib/types/api";

export const api = {
  onboarding,
  roster,
  projects,
  artifacts,
  briefs,
  gitProviders,
  mcp,
  usage,
  workspace,
  health: {
    check: () => request<HealthResponse>("/health"),
  },
} as const;
