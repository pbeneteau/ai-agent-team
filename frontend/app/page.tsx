"use client";

/**
 * Root page — redirect guard.
 *
 * Ref: TDD-05 Section 13.2
 * Checks if workspace is onboarded via GET /api/roster/readiness/global.
 * If total_agents === 0 or error → /onboarding
 * Otherwise → /projects
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useGlobalReadiness } from "@/lib/hooks/use-roster";
import { Skeleton } from "@/components/ui/skeleton";

export default function RootPage() {
  const router = useRouter();
  const { data, isLoading, isError } = useGlobalReadiness();

  useEffect(() => {
    if (isLoading) return;

    if (isError || !data || data.total_agents === 0) {
      router.replace("/onboarding");
    } else {
      router.replace("/projects");
    }
  }, [data, isLoading, isError, router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="space-y-3 text-center">
        <Skeleton className="mx-auto h-10 w-10 rounded-full" />
        <Skeleton className="h-4 w-32" />
      </div>
    </div>
  );
}
