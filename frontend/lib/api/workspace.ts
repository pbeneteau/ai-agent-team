import { request } from "@/lib/api-client";
import type {
  PaginatedResponse,
  Workspace,
  WorkspaceDocument,
  WorkspaceUpdateRequest,
} from "@/lib/types/api";

export const workspace = {
  get: () => request<Workspace>("/workspace"),

  update: (data: WorkspaceUpdateRequest) =>
    request<Workspace>("/workspace", { method: "PATCH", body: JSON.stringify(data) }),

  listDocuments: () =>
    request<PaginatedResponse<WorkspaceDocument>>("/workspace/documents"),

  uploadDocument: (formData: FormData) =>
    request<WorkspaceDocument>("/workspace/documents", { method: "POST", body: formData }),

  deleteDocument: (docId: string) =>
    request<void>(`/workspace/documents/${docId}`, { method: "DELETE" }),
};
