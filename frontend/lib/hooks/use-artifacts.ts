/**
 * TanStack Query hooks for the Artifacts domain.
 *
 * Ref: TDD-05 Section 4.1
 * Stale times:
 *   - Artifact list: 10s
 *   - Artifact status: 0s (always fresh — heartbeat polling)
 *   - Artifact versions: 60s (immutable once created)
 *   - File content: Infinity (immutable within a version)
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type {
  ArtifactFilters,
  CreateArtifactRequest,
  DelegateRequest,
  IterateRequest,
} from "@/lib/types/api";

export function useArtifactList(projectId: string, filters?: ArtifactFilters) {
  return useQuery({
    queryKey: queryKeys.artifacts.list(projectId, filters),
    queryFn: () => api.artifacts.listByProject(projectId, filters),
    staleTime: 10_000,
    enabled: !!projectId,
  });
}

export function useArtifactDetail(id: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.detail(id),
    queryFn: () => api.artifacts.get(id),
    staleTime: 10_000,
    enabled: !!id,
  });
}

export function useArtifactStatus(id: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.status(id),
    queryFn: () => api.artifacts.getStatus(id),
    staleTime: 0, // Always fresh
    refetchInterval: (query) =>
      query.state.data?.status === "drafting" ? 3_000 : false,
    enabled: !!id,
  });
}

export function useArtifactVersions(id: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.versions(id),
    queryFn: () => api.artifacts.getVersions(id),
    staleTime: 60_000,
    enabled: !!id,
  });
}

export function useArtifactFile(id: string, version: number, path: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.file(id, version, path),
    queryFn: () => api.artifacts.getFile(id, version, path),
    staleTime: Infinity, // Files within a version never change
    enabled: !!id && !!path,
  });
}

export function useValidateArtifact(id: string) {
  return useMutation({
    mutationFn: () => api.artifacts.validate(id),
  });
}

export function useCreateArtifact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateArtifactRequest) => api.artifacts.create(data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: queryKeys.artifacts.list(data.project_id) });
    },
  });
}

export function useDelegateArtifact(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data?: DelegateRequest) => api.artifacts.delegate(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.artifacts.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.artifacts.status(id) });
    },
  });
}

export function useIterateArtifact(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: IterateRequest) => api.artifacts.iterate(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.artifacts.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.artifacts.status(id) });
    },
  });
}

export function useApproveArtifact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.artifacts.approve(id),
    onMutate: async (id) => {
      // Optimistic update
      await qc.cancelQueries({ queryKey: queryKeys.artifacts.detail(id) });
      const prev = qc.getQueryData(queryKeys.artifacts.detail(id));
      qc.setQueryData(queryKeys.artifacts.detail(id), (old: Record<string, unknown> | undefined) =>
        old ? { ...old, status: "approved" } : old,
      );
      return { prev };
    },
    onError: (_err, id, context) => {
      if (context?.prev) {
        qc.setQueryData(queryKeys.artifacts.detail(id), context.prev);
      }
    },
    onSettled: (_data, _err, id) => {
      qc.invalidateQueries({ queryKey: queryKeys.artifacts.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.artifacts.all() });
    },
  });
}

export function useCancelArtifact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.artifacts.cancel(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: queryKeys.artifacts.detail(id) });
      const prev = qc.getQueryData(queryKeys.artifacts.detail(id));
      qc.setQueryData(queryKeys.artifacts.detail(id), (old: Record<string, unknown> | undefined) =>
        old ? { ...old, status: "cancelled" } : old,
      );
      return { prev };
    },
    onError: (_err, id, context) => {
      if (context?.prev) {
        qc.setQueryData(queryKeys.artifacts.detail(id), context.prev);
      }
    },
    onSettled: (_data, _err, id) => {
      qc.invalidateQueries({ queryKey: queryKeys.artifacts.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.artifacts.all() });
    },
  });
}
