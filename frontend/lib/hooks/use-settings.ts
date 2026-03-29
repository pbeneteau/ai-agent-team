/**
 * TanStack Query hooks for Settings: MCP connections & Usage.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { CreateMcpConnectionRequest } from "@/lib/types/api";

// ── MCP ────────────────────────────────────────────────────────────────

export function useMcpConnections() {
  return useQuery({
    queryKey: queryKeys.mcp.list(),
    queryFn: () => api.mcp.list(),
    staleTime: 60_000,
  });
}

export function useCreateMcpConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateMcpConnectionRequest) => api.mcp.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mcp.all() });
    },
  });
}

export function useTestMcpConnection() {
  return useMutation({
    mutationFn: (id: string) => api.mcp.test(id),
  });
}

export function useDiscoverMcpTools() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.mcp.discoverTools(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mcp.all() });
    },
  });
}

export function useDeleteMcpConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.mcp.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mcp.all() });
    },
  });
}

// ── Usage ──────────────────────────────────────────────────────────────

export function useUsageStats(period?: string) {
  return useQuery({
    queryKey: queryKeys.usage.stats(period),
    queryFn: () => api.usage.getStats(period),
    staleTime: 120_000,
  });
}

export function useUpdateBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (amount: number) => api.usage.updateBudget(amount),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.usage.all() });
    },
  });
}
