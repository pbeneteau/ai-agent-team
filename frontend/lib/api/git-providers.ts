import { request } from "@/lib/api-client";
import type {
  CreateGitConnectionRequest,
  GitConnectionItem,
  GitRepoListResponse,
  TestGitConnectionResponse,
  WebhookConfiguredResponse,
} from "@/lib/types/api";

export const gitProviders = {
  list: () => request<{ items: GitConnectionItem[] }>("/git-providers/connections"),

  create: (data: CreateGitConnectionRequest) =>
    request<GitConnectionItem>("/git-providers/connections", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  test: (id: string) =>
    request<TestGitConnectionResponse>(`/git-providers/connections/${id}/test`, {
      method: "POST",
    }),

  listRepos: (id: string) =>
    request<GitRepoListResponse>(`/git-providers/connections/${id}/repos`),

  configureWebhook: (id: string, owner: string, repo: string) =>
    request<WebhookConfiguredResponse>(
      `/git-providers/connections/${id}/repos/${owner}/${repo}/webhook`,
      { method: "POST" },
    ),

  delete: (id: string) =>
    request<void>(`/git-providers/connections/${id}`, { method: "DELETE" }),
};
