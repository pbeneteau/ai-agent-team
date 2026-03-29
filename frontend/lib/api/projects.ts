import { qs, request } from "@/lib/api-client";
import type {
  BriefContext,
  CreateProjectRequest,
  DocumentItem,
  PaginatedResponse,
  ProjectDetail,
  ProjectListItem,
  UpdateProjectRequest,
} from "@/lib/types/api";

export const projects = {
  list: (params?: { cursor?: string; limit?: number }) =>
    request<PaginatedResponse<ProjectListItem>>(`/projects?${qs(params as Record<string, unknown>)}`),

  get: (id: string) => request<ProjectDetail>(`/projects/${id}`),

  create: (data: CreateProjectRequest) =>
    request<ProjectDetail>("/projects", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: UpdateProjectRequest) =>
    request<ProjectDetail>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  delete: (id: string) =>
    request<void>(`/projects/${id}`, {
      method: "DELETE",
      headers: { "X-Confirm-Delete": "true" },
    }),

  getContext: (id: string) => request<BriefContext>(`/projects/${id}/context`),

  saveDraft: (id: string, content: string) =>
    request<{ draft: string }>(`/projects/${id}/context/draft`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),

  publish: (id: string) =>
    request<{ fingerprint: string; published_at: string }>(`/projects/${id}/context/publish`, {
      method: "POST",
    }),

  listDocuments: (id: string) =>
    request<PaginatedResponse<DocumentItem>>(`/projects/${id}/documents`),

  uploadDocument: (id: string, formData: FormData) =>
    request<DocumentItem>(`/projects/${id}/documents`, {
      method: "POST",
      body: formData,
    }),

  deleteDocument: (id: string, docId: string) =>
    request<void>(`/projects/${id}/documents/${docId}`, { method: "DELETE" }),
};
