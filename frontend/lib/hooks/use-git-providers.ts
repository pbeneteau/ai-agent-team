/**
 * TanStack Query hooks for Git Providers.
 *
 * Ref: TDD-05 Section 4.1
 * Used by the Smart Brief form for code artifacts.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { CreateGitConnectionRequest } from "@/lib/types/api";

export function useGitConnections() {
  return useQuery({
    queryKey: queryKeys.gitProviders.list(),
    queryFn: () => api.gitProviders.list(),
    staleTime: 60_000,
  });
}

export function useGitRepos(connectionId: string) {
  return useQuery({
    queryKey: queryKeys.gitProviders.repos(connectionId),
    queryFn: () => api.gitProviders.listRepos(connectionId),
    staleTime: 60_000,
    enabled: !!connectionId,
  });
}

export function useCreateGitConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateGitConnectionRequest) => api.gitProviders.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.gitProviders.all() });
    },
  });
}

export function useTestGitConnection() {
  return useMutation({
    mutationFn: (id: string) => api.gitProviders.test(id),
  });
}

export function useConfigureWebhook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ connectionId, owner, repo }: { connectionId: string; owner: string; repo: string }) =>
      api.gitProviders.configureWebhook(connectionId, owner, repo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.gitProviders.all() });
    },
  });
}

export function useDeleteGitConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.gitProviders.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.gitProviders.all() });
    },
  });
}
