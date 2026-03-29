"use client";

/**
 * Engineering context editor — structured sections for code-factory projects.
 *
 * Phase 4 of CODE_FACTORY_UI_OVERHAUL.md
 *
 * Each section is independently editable. All sections are concatenated
 * into the existing `brief_draft` field for backward compatibility with
 * the backend (no schema change needed).
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Loader2,
  Save,
  Upload,
  ChevronDown,
  ChevronRight,
  Blocks,
  BookOpen,
  TestTube,
  Plug,
  Database,
  Cloud,
} from "lucide-react";
import { useProjectContext, useSaveDraft, usePublishBrief } from "@/lib/hooks/use-projects";

// ---------------------------------------------------------------------------
// Section definitions
// ---------------------------------------------------------------------------

interface SectionDef {
  key: string;
  label: string;
  icon: React.ElementType;
  placeholder: string;
}

const SECTIONS: SectionDef[] = [
  {
    key: "architecture",
    label: "Architecture Overview",
    icon: Blocks,
    placeholder:
      "Monorepo with Nx. Backend: FastAPI + SQLAlchemy (async). Frontend: Next.js 15 App Router. Celery + Redis for background tasks. PostgreSQL 16 + pgvector.",
  },
  {
    key: "code_standards",
    label: "Code Standards & Conventions",
    icon: BookOpen,
    placeholder:
      "Use ruff for linting. Type hints on all public functions. No relative imports. snake_case for Python, camelCase for TypeScript. Max function length: 50 lines.",
  },
  {
    key: "testing",
    label: "Testing Requirements",
    icon: TestTube,
    placeholder:
      "Unit tests required for all business logic. E2E with Playwright. Min 80% coverage on new code. pytest for backend, vitest for frontend.",
  },
  {
    key: "api_conventions",
    label: "API Conventions",
    icon: Plug,
    placeholder:
      "REST with /api prefix. snake_case fields. Cursor-based pagination on all list endpoints. 201 for creation, 204 for deletion. Standard error envelope.",
  },
  {
    key: "database",
    label: "Database & Schema Notes",
    icon: Database,
    placeholder:
      "PostgreSQL 16 + pgvector. Alembic for migrations. TEXT PKs (UUID v4). All timestamps TIMESTAMPTZ. FK dependency order for migrations.",
  },
  {
    key: "deployment",
    label: "Deployment & Infrastructure",
    icon: Cloud,
    placeholder:
      "Docker Compose for dev. GitHub Actions CI (backend + frontend + e2e). Deploy to AWS ECS. Staging environment mirrors prod.",
  },
];

const SECTION_SEPARATOR = "\n\n---\n\n";
const SECTION_HEADER_PREFIX = "## ";

// ---------------------------------------------------------------------------
// Parse / serialize helpers
// ---------------------------------------------------------------------------

function parseSections(content: string): Record<string, string> {
  const result: Record<string, string> = {};
  if (!content.trim()) return result;

  // Try to parse structured format: ## Section Header\ncontent
  for (const section of SECTIONS) {
    const header = `${SECTION_HEADER_PREFIX}${section.label}`;
    const headerIdx = content.indexOf(header);
    if (headerIdx === -1) continue;

    const afterHeader = headerIdx + header.length;
    // Find the next section header or end of string
    let endIdx = content.length;
    for (const other of SECTIONS) {
      if (other.key === section.key) continue;
      const otherHeader = `${SECTION_HEADER_PREFIX}${other.label}`;
      const otherIdx = content.indexOf(otherHeader, afterHeader);
      if (otherIdx !== -1 && otherIdx < endIdx) {
        endIdx = otherIdx;
      }
    }

    const sectionContent = content.slice(afterHeader, endIdx).replace(/^[\n\-\s]+/, "").replace(/[\n\-\s]+$/, "");
    if (sectionContent) {
      result[section.key] = sectionContent;
    }
  }

  // If no structured sections found, put everything in architecture
  if (Object.keys(result).length === 0 && content.trim()) {
    result.architecture = content.trim();
  }

  return result;
}

function serializeSections(sections: Record<string, string>): string {
  const parts: string[] = [];
  for (const def of SECTIONS) {
    const value = sections[def.key]?.trim();
    if (value) {
      parts.push(`${SECTION_HEADER_PREFIX}${def.label}\n\n${value}`);
    }
  }
  return parts.join(SECTION_SEPARATOR);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface BriefEditorProps {
  projectId: string;
}

export function BriefEditor({ projectId }: BriefEditorProps) {
  const { data: context, isLoading } = useProjectContext(projectId);
  const saveDraft = useSaveDraft(projectId);
  const publishBrief = usePublishBrief(projectId);

  const [sections, setSections] = useState<Record<string, string>>({});
  const [initialized, setInitialized] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(["architecture"]));
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initialize from server
  useEffect(() => {
    if (context && !initialized) {
      const raw = context.draft ?? context.published ?? "";
      setSections(parseSections(raw));
      setInitialized(true);
      // Expand sections that have content
      const withContent = new Set(
        SECTIONS.filter((s) => {
          const parsed = parseSections(raw);
          return parsed[s.key]?.trim();
        }).map((s) => s.key),
      );
      if (withContent.size === 0) withContent.add("architecture");
      setExpandedSections(withContent);
    }
  }, [context, initialized]);

  // Serialize and auto-save
  const debouncedSave = useCallback(
    (updated: Record<string, string>) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const serialized = serializeSections(updated);
        saveDraft.mutate(serialized, {
          onSuccess: () => setLastSaved(new Date()),
          onError: () => toast.error("Failed to save draft"),
        });
      }, 2000);
    },
    [saveDraft],
  );

  const handleSectionChange = useCallback(
    (key: string, value: string) => {
      setSections((prev) => {
        const updated = { ...prev, [key]: value };
        debouncedSave(updated);
        return updated;
      });
    },
    [debouncedSave],
  );

  const toggleSection = useCallback((key: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handlePublish = () => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }

    const serialized = serializeSections(sections);
    saveDraft.mutate(serialized, {
      onSuccess: () => {
        publishBrief.mutate(undefined, {
          onSuccess: () => {
            toast.success("Context published. All agents have been rebriefed.");
            setLastSaved(new Date());
          },
          onError: (error) => {
            toast.error(error.message || "Failed to publish context");
          },
        });
      },
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const currentSerialized = serializeSections(sections);
  const isDraft = currentSerialized !== (context?.published ?? "");
  const hasPublished = !!context?.published;
  const hasContent = Object.values(sections).some((v) => v.trim());

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
            Engineering Context
          </h2>
          {hasPublished && !isDraft && (
            <Badge
              variant="outline"
              className="bg-[var(--color-success-subtle)] text-[var(--color-success)]"
            >
              Published
            </Badge>
          )}
          {isDraft && (
            <Badge
              variant="outline"
              className="bg-[var(--color-warning-subtle)] text-[var(--color-warning)]"
            >
              Draft
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {lastSaved && (
            <span className="text-xs text-[var(--color-text-tertiary)]">
              <Save className="mr-1 inline h-3 w-3" />
              Saved
            </span>
          )}
          {saveDraft.isPending && (
            <span className="text-xs text-[var(--color-text-tertiary)]">
              <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />
              Saving...
            </span>
          )}
        </div>
      </div>

      <p className="text-xs text-[var(--color-text-tertiary)]">
        Define the engineering standards and architecture that all agents will follow.
        Sections are auto-saved and concatenated when published.
      </p>

      {/* Structured sections */}
      <div className="space-y-2">
        {SECTIONS.map((section) => {
          const Icon = section.icon;
          const isExpanded = expandedSections.has(section.key);
          const value = sections[section.key] ?? "";
          const hasValue = value.trim().length > 0;

          return (
            <div
              key={section.key}
              className="rounded-[var(--radius-lg)] border border-[var(--color-border-primary)] overflow-hidden"
            >
              <button
                type="button"
                onClick={() => toggleSection(section.key)}
                className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)] transition-colors"
              >
                {isExpanded ? (
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-tertiary)]" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-tertiary)]" />
                )}
                <Icon className="h-4 w-4 shrink-0 text-[var(--color-text-secondary)]" />
                <span>{section.label}</span>
                {hasValue && !isExpanded && (
                  <span className="ml-auto text-xs text-[var(--color-text-tertiary)] truncate max-w-[200px]">
                    {value.slice(0, 60)}{value.length > 60 ? "..." : ""}
                  </span>
                )}
                {hasValue && (
                  <span className="ml-auto shrink-0 h-1.5 w-1.5 rounded-full bg-[var(--color-accent)]" />
                )}
              </button>
              {isExpanded && (
                <div className="px-4 pb-4">
                  <Textarea
                    value={value}
                    onChange={(e) => handleSectionChange(section.key, e.target.value)}
                    placeholder={section.placeholder}
                    className="min-h-[100px]"
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--color-text-tertiary)]">
          {hasPublished && context?.published_at
            ? `Last published: ${new Date(context.published_at).toLocaleDateString()}`
            : "Not yet published"}
        </p>
        <Button
          onClick={handlePublish}
          disabled={publishBrief.isPending || !hasContent}
        >
          {publishBrief.isPending ? (
            <>
              <Loader2 className="animate-spin" />
              Publishing...
            </>
          ) : (
            <>
              <Upload className="h-4 w-4" />
              Publish Context
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
