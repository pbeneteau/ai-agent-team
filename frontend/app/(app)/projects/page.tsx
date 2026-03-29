"use client";

/**
 * Projects list page — grid of project cards + "New Project" button.
 *
 * Ref: TDD-05 Section 15.1, TDD-01 Journey J5 Steps 1-2
 */

import { useState, useCallback } from "react";
import { FolderKanban, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjectList } from "@/lib/hooks/use-projects";
import { ProjectCard } from "@/features/projects/project-card";
import { CreateProjectDialog } from "@/features/projects/create-project-dialog";
import { CursorPagination } from "@/components/shared/cursor-pagination";
import type { ProjectListItem } from "@/lib/types/api";

export default function ProjectsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [cursor, setCursor] = useState<string | undefined>();
  const [allProjects, setAllProjects] = useState<ProjectListItem[]>([]);
  const { data, isLoading } = useProjectList(cursor);

  // Merge paginated results
  const projects = cursor ? allProjects : (data?.items ?? []);
  const hasMore = data?.has_more ?? false;

  const loadMore = useCallback(() => {
    if (data?.next_cursor) {
      setAllProjects((prev) => [...prev, ...(data.items ?? [])]);
      setCursor(data.next_cursor);
    }
  }, [data]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FolderKanban className="h-6 w-6 text-[var(--color-accent)]" />
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">Projects</h1>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" />
          New Project
        </Button>
      </div>

      {isLoading && !cursor ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-36 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-20">
          <FolderKanban className="h-10 w-10 text-[var(--color-text-tertiary)]" />
          <p className="text-sm text-[var(--color-text-secondary)]">
            No projects yet. Create your first project to get started.
          </p>
          <Button variant="outline" onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            Create Project
          </Button>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
          <CursorPagination hasMore={hasMore} isLoading={isLoading} onLoadMore={loadMore} />
        </>
      )}

      <CreateProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
