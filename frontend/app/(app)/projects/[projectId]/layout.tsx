"use client";

/**
 * Project-scoped layout — project name + tab navigation.
 *
 * Ref: TDD-05 Section 3, Section 15.2
 */

import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjectDetail } from "@/lib/hooks/use-projects";
import { cn } from "@/lib/utils";

const tabs = [
  { label: "Artifacts", href: "" },
  { label: "Brief", href: "/brief" },
  { label: "Documents", href: "/documents" },
];

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ projectId: string }>();
  const pathname = usePathname();
  const projectId = params.projectId;
  const { data: project, isLoading } = useProjectDetail(projectId);

  const basePath = `/projects/${projectId}`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <Link
          href="/projects"
          className="inline-flex items-center gap-1 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
        >
          <ArrowLeft className="h-3 w-3" />
          Projects
        </Link>
        {isLoading ? (
          <Skeleton className="h-7 w-48" />
        ) : (
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
            {project?.name ?? "Project"}
          </h1>
        )}
      </div>

      {/* Tab navigation */}
      <nav className="flex gap-1 border-b border-[var(--color-border-primary)]">
        {tabs.map((tab) => {
          const tabHref = `${basePath}${tab.href}`;
          const isActive =
            tab.href === ""
              ? pathname === basePath
              : pathname.startsWith(tabHref);

          return (
            <Link
              key={tab.href}
              href={tabHref}
              className={cn(
                "relative px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "text-[var(--color-text-primary)]"
                  : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]",
              )}
            >
              {tab.label}
              {isActive && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--color-accent)]" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Content */}
      {children}
    </div>
  );
}
