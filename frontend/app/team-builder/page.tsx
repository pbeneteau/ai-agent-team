"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { buildAlexWorkspaceHref } from "@/components/chat/chat-shell";

export default function TeamBuilderPage() {
  return (
    <div className="h-full min-h-0">
      <Suspense fallback={<div className="h-full min-h-0 bg-[var(--ops-canvas)]" />}>
        <TeamBuilderAlias />
      </Suspense>
    </div>
  );
}

function TeamBuilderAlias() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const docId = searchParams.get("doc") ?? undefined;
    router.replace(buildAlexWorkspaceHref({ mode: "design-team", docId }));
  }, [router, searchParams]);

  return <div className="h-full min-h-0 bg-[var(--ops-canvas)]" />;
}
