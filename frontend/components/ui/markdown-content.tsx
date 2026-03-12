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
        "prose-headings:font-semibold prose-headings:text-slate-900",
        "prose-p:text-slate-700 prose-p:leading-7",
        "prose-li:text-slate-700 prose-li:leading-7",
        "prose-strong:text-slate-900",
        "prose-a:text-blue-600 hover:prose-a:text-blue-700",
        "prose-code:text-slate-900",
        "prose-table:text-sm",
        "prose-blockquote:border-l-slate-300 prose-blockquote:text-slate-600",
        "[&_img]:rounded-xl [&_img]:border [&_img]:border-slate-200",
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
                    "rounded-md bg-slate-100 px-1.5 py-0.5 text-[0.9em] font-medium text-slate-900",
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
                  "block bg-transparent p-0 text-[13px] leading-6 text-slate-100 before:content-none after:content-none",
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
                  "overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950 px-4 py-4 text-slate-100 shadow-sm",
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
