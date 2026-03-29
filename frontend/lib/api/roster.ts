import { qs, request } from "@/lib/api-client";
import type {
  ActionResponse,
  AgentDetail,
  AgentListItem,
  CreateAgentRequest,
  GlobalReadiness,
  LearningProfile,
  PaginatedResponse,
  RosterFilters,
  SkillsListResponse,
  UpdateAgentRequest,
} from "@/lib/types/api";

export const roster = {
  list: (params?: RosterFilters) =>
    request<PaginatedResponse<AgentListItem>>(`/roster?${qs(params as Record<string, unknown>)}`),

  get: (id: string) => request<AgentDetail>(`/roster/${id}`),

  create: (data: CreateAgentRequest) =>
    request<AgentDetail>("/roster", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: UpdateAgentRequest) =>
    request<AgentDetail>(`/roster/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  archive: (id: string) => request<ActionResponse>(`/roster/${id}`, { method: "DELETE" }),

  restore: (id: string) => request<ActionResponse>(`/roster/${id}/restore`, { method: "POST" }),

  deletePermanent: (id: string) =>
    request<void>(`/roster/${id}/permanent`, { method: "DELETE" }),

  getSkills: (id: string, category?: string) =>
    request<SkillsListResponse>(`/roster/${id}/skills?${qs({ category })}`),

  getLearningProfile: (id: string) =>
    request<LearningProfile>(`/roster/${id}/learning-profile`),

  triggerResearch: (id: string, topic: string) =>
    request<ActionResponse>(`/roster/${id}/research`, {
      method: "POST",
      body: JSON.stringify({ topic }),
    }),

  triggerReflection: (id: string) =>
    request<ActionResponse>(`/roster/${id}/reflect`, { method: "POST" }),

  uploadKnowledge: (id: string, formData: FormData) =>
    request<ActionResponse>(`/roster/${id}/knowledge`, {
      method: "POST",
      body: formData,
    }),

  getRecommendations: (id: string) =>
    request<{ items: unknown[] }>(`/roster/${id}/knowledge-recommendations`),

  applyRecommendation: (id: string, recId: string) =>
    request<ActionResponse>(`/roster/${id}/knowledge-recommendations/${recId}/apply`, {
      method: "POST",
    }),

  dismissRecommendation: (id: string, recId: string) =>
    request<ActionResponse>(`/roster/${id}/knowledge-recommendations/${recId}/dismiss`, {
      method: "POST",
    }),

  globalReadiness: () => request<GlobalReadiness>("/roster/readiness/global"),
};
