/**
 * TanStack Query hooks for the Projects domain.
 *
 * Ref: TDD-05 Section 4.1
 * Stale time: 60s (projects rarely change during a session)
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { CreateProjectRequest, UpdateProjectRequest } from "@/lib/types/api";

const PROJECTS_STALE = 60_000;
const DOCUMENTS_STALE = 60_000;

export function useProjectList(cursor?: string) {
  return useQuery({
    queryKey: queryKeys.projects.list(cursor),
    queryFn: () => api.projects.list({ cursor }),
    staleTime: PROJECTS_STALE,
  });
}

export function useProjectDetail(id: string) {
  return useQuery({
    queryKey: queryKeys.projects.detail(id),
    queryFn: () => api.projects.get(id),
    staleTime: PROJECTS_STALE,
    enabled: !!id,
  });
}

export function useProjectContext(id: string) {
  return useQuery({
    queryKey: queryKeys.projects.context(id),
    queryFn: () => api.projects.getContext(id),
    staleTime: PROJECTS_STALE,
    enabled: !!id,
  });
}

export function useProjectDocuments(id: string) {
  return useQuery({
    queryKey: queryKeys.projects.documents(id),
    queryFn: () => api.projects.listDocuments(id),
    staleTime: DOCUMENTS_STALE,
    enabled: !!id,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateProjectRequest) => api.projects.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.all() });
    },
  });
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateProjectRequest) => api.projects.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.projects.all() });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.projects.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.all() });
    },
  });
}

export function useSaveDraft(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => api.projects.saveDraft(id, content),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.context(id) });
    },
  });
}

export function usePublishBrief(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.projects.publish(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.context(id) });
      qc.invalidateQueries({ queryKey: queryKeys.projects.detail(id) });
    },
  });
}

export function useUploadDocument(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (formData: FormData) => api.projects.uploadDocument(projectId, formData),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.documents(projectId) });
    },
  });
}

export function useDeleteDocument(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (docId: string) => api.projects.deleteDocument(projectId, docId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.documents(projectId) });
    },
  });
}
