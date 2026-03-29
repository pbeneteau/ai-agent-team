"use client";

/**
 * Prose viewer — renders markdown content with text selection support.
 *
 * Ref: TDD-05 Section 10.2, TDD-01 J2 Step 10
 * Renders via react-markdown + remark-gfm.
 * Text selection events are handled by the useTextSelection hook.
 */

import { useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTextSelection } from "@/lib/hooks/use-text-selection";

interface ProseViewerProps {
  content: string;
}

export function ProseViewer({ content }: ProseViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  useTextSelection(containerRef);

  return (
    <div
      ref={containerRef}
      className="prose-viewer prose prose-sm max-w-none text-[var(--color-text-primary)]
        prose-headings:text-[var(--color-text-primary)] prose-headings:font-semibold
        prose-p:text-[var(--color-text-primary)] prose-p:leading-relaxed
        prose-a:text-[var(--color-accent)] prose-a:no-underline hover:prose-a:underline
        prose-strong:text-[var(--color-text-primary)] prose-strong:font-semibold
        prose-code:rounded-[var(--radius-sm)] prose-code:bg-[var(--color-bg-tertiary)] prose-code:px-1.5 prose-code:py-0.5 prose-code:text-[var(--color-text-primary)] prose-code:font-mono prose-code:text-[0.85em] prose-code:before:content-[''] prose-code:after:content-['']
        prose-pre:rounded-[var(--radius-md)] prose-pre:bg-[var(--color-bg-tertiary)] prose-pre:border prose-pre:border-[var(--color-border-primary)]
        prose-blockquote:border-l-[var(--color-accent)] prose-blockquote:text-[var(--color-text-secondary)]
        prose-th:text-left prose-th:text-[var(--color-text-primary)]
        prose-td:text-[var(--color-text-primary)]
        prose-hr:border-[var(--color-border-primary)]
        prose-li:text-[var(--color-text-primary)]
        prose-img:rounded-[var(--radius-md)]
      "
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
