"use client";

/**
 * Code viewer — syntax-highlighted file content with line numbers.
 *
 * Phase 6 of CODE_FACTORY_UI_OVERHAUL.md
 * Uses shiki for syntax highlighting with language auto-detection.
 */

import { useEffect, useState } from "react";
import { codeToHtml } from "shiki";
import { Skeleton } from "@/components/ui/skeleton";

// ---------------------------------------------------------------------------
// Language detection from file extension
// ---------------------------------------------------------------------------

const EXT_TO_LANG: Record<string, string> = {
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  py: "python",
  rs: "rust",
  go: "go",
  java: "java",
  kt: "kotlin",
  swift: "swift",
  rb: "ruby",
  php: "php",
  cs: "csharp",
  cpp: "cpp",
  c: "c",
  h: "c",
  css: "css",
  scss: "scss",
  html: "html",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  md: "markdown",
  sql: "sql",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  dockerfile: "dockerfile",
  xml: "xml",
  graphql: "graphql",
  prisma: "prisma",
  env: "dotenv",
  gitignore: "text",
  txt: "text",
};

function detectLanguage(filePath: string): string {
  const fileName = filePath.split("/").pop() ?? "";

  // Check full filename first (Dockerfile, Makefile, etc.)
  const lowerName = fileName.toLowerCase();
  if (lowerName === "dockerfile") return "dockerfile";
  if (lowerName === "makefile") return "makefile";

  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  return EXT_TO_LANG[ext] ?? "text";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface CodeViewerProps {
  content: string;
  filePath: string;
  onLineClick?: (lineNumber: number) => void;
}

export function CodeViewer({ content, filePath, onLineClick }: CodeViewerProps) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState(false);

  const lang = detectLanguage(filePath);

  useEffect(() => {
    let cancelled = false;

    async function highlight() {
      try {
        const result = await codeToHtml(content, {
          lang,
          theme: "github-dark-default",
        });
        if (!cancelled) {
          setHtml(result);
          setError(false);
        }
      } catch {
        // Fallback: if shiki doesn't support the language, show plain
        if (!cancelled) {
          setError(true);
        }
      }
    }

    setHtml(null);
    highlight();

    return () => {
      cancelled = true;
    };
  }, [content, lang]);

  if (html === null && !error) {
    return (
      <div className="space-y-2 p-4">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  if (error) {
    // Plain text fallback with line numbers
    return <PlainViewer content={content} onLineClick={onLineClick} />;
  }

  return (
    <div className="overflow-x-auto">
      <div
        className="code-viewer text-sm [&_pre]:!bg-transparent [&_pre]:!p-4 [&_pre]:!m-0 [&_code]:!text-xs [&_code]:font-mono"
        dangerouslySetInnerHTML={{ __html: html! }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plain text fallback
// ---------------------------------------------------------------------------

function PlainViewer({
  content,
  onLineClick,
}: {
  content: string;
  onLineClick?: (lineNumber: number) => void;
}) {
  const lines = content.split("\n");

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <tbody>
          {lines.map((line, i) => (
            <tr key={i} className="hover:bg-[var(--color-bg-tertiary)]">
              <td
                className="select-none px-3 py-0.5 text-right text-[var(--color-text-tertiary)] w-12 cursor-pointer"
                onClick={() => onLineClick?.(i + 1)}
              >
                {i + 1}
              </td>
              <td className="px-3 py-0.5 whitespace-pre text-[var(--color-text-primary)]">
                {line || "\u00A0"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
