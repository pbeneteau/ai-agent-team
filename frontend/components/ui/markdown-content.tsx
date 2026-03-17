"use client";

import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export function MarkdownContent({ content, className }: MarkdownContentProps) {
  return (
    <div
      className={cn(
        "prose prose-slate max-w-none",
        "prose-headings:font-semibold prose-headings:text-[var(--ops-ink)]",
        "prose-p:text-[var(--ops-muted-ink)] prose-p:leading-7",
        "prose-li:text-[var(--ops-muted-ink)] prose-li:leading-7",
        "prose-strong:text-[var(--ops-ink)]",
        "prose-a:text-primary hover:prose-a:text-primary/80",
        "prose-code:text-[var(--ops-ink)]",
        "prose-table:text-sm",
        "prose-blockquote:border-l-[var(--ops-border-strong)] prose-blockquote:text-[var(--ops-muted-ink)]",
        "[&_img]:rounded-[16px] [&_img]:border [&_img]:border-[var(--ops-border)]",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code(props) {
            const { children, className: codeClassName, ...rest } = props;
            const inline = !codeClassName;
            if (inline) {
              return (
                <code
                  className={cn(
                    "rounded-md border border-[var(--ops-border)] bg-[var(--ops-surface-muted)] px-1.5 py-0.5 text-[0.9em] font-medium text-[var(--ops-ink)]",
                    codeClassName,
                  )}
                  {...rest}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className={cn(
                  "block bg-transparent p-0 text-[13px] leading-6 text-[var(--ops-ink)] before:content-none after:content-none",
                  codeClassName,
                )}
                {...rest}
              >
                {children as ReactNode}
              </code>
            );
          },
          pre(props) {
            const { children, className: preClassName, ...rest } = props;
            return (
              <pre
                className={cn(
                  "overflow-x-auto rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-strong)] px-4 py-4 text-[var(--ops-ink)] shadow-none",
                  preClassName,
                )}
                {...rest}
              >
                {children}
              </pre>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
