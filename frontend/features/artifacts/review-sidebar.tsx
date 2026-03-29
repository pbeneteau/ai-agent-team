"use client";

/**
 * Review sidebar — sources, assumptions, cost, comments tabs.
 *
 * Ref: TDD-05 Section 10.1-10.2
 */

import { ExternalLink, Lightbulb, DollarSign, MessageSquare } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import type { VersionItem, IterateRequest } from "@/lib/types/api";

interface ReviewSidebarProps {
  version: VersionItem | null;
  comments?: CommentItem[];
}

interface CommentItem {
  id: string;
  highlighted_text: string;
  instruction: string;
  resulting_version: number | null;
  created_at: string;
}

export function ReviewSidebar({ version, comments = [] }: ReviewSidebarProps) {
  if (!version) return null;

  const sources = version.sources ?? [];
  const assumptions = version.assumptions ?? [];
  const costUsd = version.token_cost_usd ?? 0;
  const inputTokens = version.input_tokens ?? 0;
  const outputTokens = version.output_tokens ?? 0;

  return (
    <div className="space-y-5">
      {/* Sources */}
      <section>
        <h3 className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-primary)]">
          <ExternalLink className="h-4 w-4 text-[var(--color-text-secondary)]" />
          Sources ({sources.length})
        </h3>
        {sources.length > 0 ? (
          <ul className="mt-2 space-y-1">
            {sources.map((source, i) => (
              <li key={i} className="text-xs text-[var(--color-text-secondary)] truncate">
                {isUrl(source) ? (
                  <a
                    href={source}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[var(--color-accent)] hover:underline"
                  >
                    {source}
                  </a>
                ) : (
                  source
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-[var(--color-text-tertiary)]">No sources cited.</p>
        )}
      </section>

      <Separator />

      {/* Assumptions */}
      <section>
        <h3 className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-primary)]">
          <Lightbulb className="h-4 w-4 text-[var(--color-text-secondary)]" />
          Assumptions ({assumptions.length})
        </h3>
        {assumptions.length > 0 ? (
          <ul className="mt-2 space-y-2">
            {assumptions.map((assumption, i) => (
              <li
                key={i}
                className="rounded-[var(--radius-sm)] bg-[var(--color-warning-subtle)] px-2.5 py-1.5 text-xs text-[var(--color-warning)]"
              >
                {assumption}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-[var(--color-text-tertiary)]">No assumptions made.</p>
        )}
      </section>

      <Separator />

      {/* Cost */}
      <section>
        <h3 className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-primary)]">
          <DollarSign className="h-4 w-4 text-[var(--color-text-secondary)]" />
          Cost
        </h3>
        <div className="mt-1 space-y-0.5">
          <p className="text-sm font-medium text-[var(--color-text-primary)]">${costUsd.toFixed(2)}</p>
          <p className="text-xs text-[var(--color-text-tertiary)]">
            {inputTokens.toLocaleString()} in / {outputTokens.toLocaleString()} out
          </p>
        </div>
      </section>

      <Separator />

      {/* Comments */}
      <section>
        <h3 className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-primary)]">
          <MessageSquare className="h-4 w-4 text-[var(--color-text-secondary)]" />
          Comments ({comments.length})
        </h3>
        {comments.length > 0 ? (
          <ul className="mt-2 space-y-3">
            {comments.map((comment) => (
              <li key={comment.id} className="space-y-1">
                <p className="text-xs italic text-[var(--color-text-tertiary)] truncate">
                  &ldquo;{truncate(comment.highlighted_text, 60)}&rdquo;
                </p>
                <p className="text-xs text-[var(--color-text-secondary)]">{comment.instruction}</p>
                {comment.resulting_version && (
                  <p className="text-[10px] text-[var(--color-text-tertiary)]">
                    &rarr; v{comment.resulting_version}
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-[var(--color-text-tertiary)]">
            Select text in the document to add a comment.
          </p>
        )}
      </section>
    </div>
  );
}

function isUrl(s: string): boolean {
  return s.startsWith("http://") || s.startsWith("https://");
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + "..." : s;
}
