"use client";

/**
 * Project card for the codebase grid — code-factory focused.
 *
 * Shows language badge, repo name, task count, relative time.
 */

import Link from "next/link";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { GitBranch, Code } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { ProjectListItem } from "@/lib/types/api";

const LANGUAGE_COLORS: Record<string, string> = {
  TypeScript: "bg-blue-500",
  Python: "bg-yellow-500",
  Go: "bg-cyan-500",
  Rust: "bg-orange-600",
  Java: "bg-red-500",
  "C#": "bg-purple-500",
  Ruby: "bg-red-600",
  PHP: "bg-indigo-400",
  Swift: "bg-orange-500",
  Kotlin: "bg-violet-500",
};

interface ProjectCardProps {
  project: ProjectListItem;
}

export function ProjectCard({ project }: ProjectCardProps) {
  const langColor = project.primary_language
    ? LANGUAGE_COLORS[project.primary_language] ?? "bg-gray-400"
    : null;

  // Extract owner/repo from git URL if available
  const repoShortName = project.git_repo_url
    ? project.git_repo_url.replace(/^https?:\/\/github\.com\//, "").replace(/^https?:\/\/gitlab\.com\//, "").replace(/\.git$/, "")
    : null;

  return (
    <Link href={`/projects/${project.id}`}>
      <Card className="h-full transition-shadow hover:shadow-[var(--shadow-md)] cursor-pointer">
        <CardHeader>
          <div className="flex items-center gap-2">
            <CardTitle className="truncate">{project.name}</CardTitle>
            {project.primary_language && (
              <Badge variant="secondary" className="shrink-0 text-[10px] px-1.5 py-0">
                <span className={`mr-1 inline-block h-2 w-2 rounded-full ${langColor}`} />
                {project.primary_language}
              </Badge>
            )}
          </div>
          {project.description && (
            <CardDescription className="line-clamp-2">{project.description}</CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs text-[var(--color-text-secondary)]">
              {repoShortName ? (
                <span className="flex items-center gap-1 truncate max-w-[140px]">
                  <GitBranch className="h-3 w-3 shrink-0" />
                  {repoShortName}
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <Code className="h-3 w-3" />
                  {project.artifact_count} task{project.artifact_count !== 1 ? "s" : ""}
                </span>
              )}
              {project.framework && (
                <span className="text-[var(--color-text-tertiary)]">{project.framework}</span>
              )}
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
