/**
 * TanStack Query hooks for the Roster domain.
 *
 * Ref: TDD-05 Section 4.1
 * Stale time: 30s (agents change status infrequently; WS handles urgent updates)
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { CreateAgentRequest, RosterFilters, UpdateAgentRequest } from "@/lib/types/api";

const ROSTER_STALE = 30_000;

export function useRosterList(filters?: RosterFilters) {
  return useQuery({
    queryKey: queryKeys.roster.list(filters),
    queryFn: () => api.roster.list(filters),
    staleTime: ROSTER_STALE,
  });
}

export function useAgentDetail(id: string) {
  return useQuery({
    queryKey: queryKeys.roster.detail(id),
    queryFn: () => api.roster.get(id),
    staleTime: ROSTER_STALE,
    enabled: !!id,
  });
}

export function useAgentSkills(id: string, category?: string) {
  return useQuery({
    queryKey: queryKeys.roster.skills(id, category),
    queryFn: () => api.roster.getSkills(id, category),
    staleTime: ROSTER_STALE,
    enabled: !!id,
  });
}

export function useLearningProfile(id: string) {
  return useQuery({
    queryKey: queryKeys.roster.learningProfile(id),
    queryFn: () => api.roster.getLearningProfile(id),
    staleTime: ROSTER_STALE,
    enabled: !!id,
  });
}

export function useGlobalReadiness() {
  return useQuery({
    queryKey: queryKeys.roster.globalReadiness(),
    queryFn: () => api.roster.globalReadiness(),
    staleTime: ROSTER_STALE,
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateAgentRequest) => api.roster.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.roster.all() });
    },
  });
}

export function useUpdateAgent(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateAgentRequest) => api.roster.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.roster.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.roster.all() });
    },
  });
}

export function useArchiveAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.roster.archive(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: queryKeys.roster.all() });
      const prev = qc.getQueriesData({ queryKey: queryKeys.roster.all() });
      qc.setQueriesData(
        { queryKey: queryKeys.roster.all() },
        (old: unknown) => {
          if (!old || typeof old !== "object") return old;
          const data = old as { items?: Array<{ id: string }> };
          if (data.items) {
            return { ...data, items: data.items.filter((a) => a.id !== id) };
          }
          return old;
        },
      );
      return { prev };
    },
    onError: (_err, _id, context) => {
      if (context?.prev) {
        for (const [key, data] of context.prev) {
          qc.setQueryData(key, data);
        }
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: queryKeys.roster.all() });
    },
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.roster.deletePermanent(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.roster.all() });
    },
  });
}

export function useTriggerResearch(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (topic: string) => api.roster.triggerResearch(id, topic),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.roster.detail(id) });
    },
  });
}

export function useTriggerReflection(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.roster.triggerReflection(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.roster.detail(id) });
    },
  });
}

export function useAgentRecommendations(id: string) {
  return useQuery({
    queryKey: queryKeys.roster.recommendations(id),
    queryFn: () => api.roster.getRecommendations(id),
    staleTime: ROSTER_STALE,
    enabled: !!id,
  });
}
