"use client";

/**
 * Project card for the project grid.
 *
 * Ref: TDD-05 Section 15.1
 */

import Link from "next/link";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { ProjectListItem } from "@/lib/types/api";

interface ProjectCardProps {
  project: ProjectListItem;
}

export function ProjectCard({ project }: ProjectCardProps) {
  return (
    <Link href={`/projects/${project.id}`}>
      <Card className="h-full transition-shadow hover:shadow-[var(--shadow-md)] cursor-pointer">
        <CardHeader>
          <CardTitle className="truncate">{project.name}</CardTitle>
          {project.description && (
            <CardDescription className="line-clamp-2">{project.description}</CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)]">
              <FileText className="h-3.5 w-3.5" />
              <span>{project.artifact_count} artifact{project.artifact_count !== 1 ? "s" : ""}</span>
            </div>
            <span className="text-xs text-[var(--color-text-tertiary)]">
              {formatDistanceToNow(new Date(project.created_at), { addSuffix: true })}
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
