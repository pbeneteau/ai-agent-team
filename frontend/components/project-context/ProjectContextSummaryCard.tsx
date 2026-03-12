"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, FolderOpen, Loader2 } from "lucide-react";

import { api, type ProjectContextState } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface ProjectContextSummaryCardProps {
  compact?: boolean;
}

export function ProjectContextSummaryCard({ compact = false }: ProjectContextSummaryCardProps) {
  const [contextState, setContextState] = useState<ProjectContextState | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getProjectContext()
      .then((data) => setContextState(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const context = contextState?.active ?? null;
  const hasContext = Boolean(context?.name || context?.description);

  return (
    <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.2)] ring-0">
      <CardHeader className="border-b border-black/5">
        <div className="flex items-start gap-3">
          <div className="flex size-10 items-center justify-center rounded-2xl bg-primary/8 text-primary">
            <FolderOpen className="size-4" />
          </div>

          <div className="min-w-0 flex-1 space-y-1">
            <CardTitle className="text-base">Project context</CardTitle>
            <CardDescription>
              The global brief, sources, and knowledge diagnostics now live in a dedicated hub.
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pt-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading project context…
          </div>
        ) : hasContext ? (
          <>
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium text-foreground">{context?.name}</p>
                <Badge variant="outline" className="border-black/8 bg-white text-[10px] text-muted-foreground">
                  {context?.status === "published" ? `Published rev ${context?.revision}` : `Draft rev ${context?.revision}`}
                </Badge>
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                {context?.description}
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              {context?.domain ? <Badge variant="outline">{context.domain}</Badge> : null}
              {context?.short_term_goal ? (
                <Badge variant="secondary" className="bg-primary/8 text-primary">
                  Focus: {context.short_term_goal}
                </Badge>
              ) : null}
              {context?.tech_stack ? (
                <Badge variant="outline" className="max-w-full truncate">
                  Stack: {context.tech_stack}
                </Badge>
              ) : null}
            </div>
          </>
        ) : (
          <p className="text-sm leading-6 text-muted-foreground">
            No project brief is defined yet. Open the hub to set the frame, add documents, and see what agents are missing.
          </p>
        )}

        <div className="flex justify-end">
          <Link href="/project-context">
            <Button variant={compact ? "outline" : "default"} className="gap-2">
              Open context hub
              <ArrowRight className="size-4" />
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
