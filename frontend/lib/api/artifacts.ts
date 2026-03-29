import { API_BASE, qs, request } from "@/lib/api-client";
import type {
  ArtifactFilters,
  ArtifactListItem,
  ArtifactResponse,
  ArtifactStatusResponse,
  CreateArtifactRequest,
  DelegateConfirmResponse,
  DelegatePreviewResponse,
  DelegateRequest,
  IterateRequest,
  IterateResponse,
  PaginatedResponse,
  StandaloneSufficiencyRequest,
  SufficiencyResponse,
  VersionItem,
} from "@/lib/types/api";

export const artifacts = {
  create: (data: CreateArtifactRequest) =>
    request<ArtifactResponse>("/artifacts", { method: "POST", body: JSON.stringify(data) }),

  get: (id: string) => request<ArtifactResponse>(`/artifacts/${id}`),

  getStatus: (id: string) => request<ArtifactStatusResponse>(`/artifacts/${id}/status`),

  validate: (id: string) =>
    request<SufficiencyResponse>(`/artifacts/${id}/validate`, { method: "POST" }),

  delegate: (id: string, data?: DelegateRequest) =>
    request<DelegatePreviewResponse | DelegateConfirmResponse>(`/artifacts/${id}/delegate`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),

  getVersions: (id: string) => request<{ items: VersionItem[] }>(`/artifacts/${id}/versions`),

  getFile: (id: string, version: number, path: string) =>
    fetch(`${API_BASE}/artifacts/${id}/versions/${version}/files/${path}`).then((r) => r.text()),

  iterate: (id: string, data: IterateRequest) =>
    request<IterateResponse>(`/artifacts/${id}/iterate`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  approve: (id: string) =>
    request<{ status: string }>(`/artifacts/${id}/approve`, { method: "PATCH" }),

  cancel: (id: string) =>
    request<{ status: string }>(`/artifacts/${id}/cancel`, { method: "PATCH" }),

  retry: (id: string) =>
    request<ArtifactResponse>(`/artifacts/${id}/retry`, { method: "POST" }),

  listByProject: (projectId: string, params?: ArtifactFilters) =>
    request<PaginatedResponse<ArtifactListItem>>(
      `/projects/${projectId}/artifacts?${qs(params as Record<string, unknown>)}`,
    ),
};

export const briefs = {
  sufficiencyCheck: (data: StandaloneSufficiencyRequest) =>
    request<SufficiencyResponse>("/briefs/sufficiency-check", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
