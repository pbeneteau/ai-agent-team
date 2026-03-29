"use client";

/**
 * Error boundary for (app) route group.
 *
 * Ref: TDD-05 Section 17.2
 */

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20" role="alert">
      <AlertTriangle className="h-10 w-10 text-[var(--color-danger)]" />
      <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">
        Something went wrong
      </h2>
      <p className="max-w-md text-center text-sm text-[var(--color-text-secondary)]">
        {error.message || "An unexpected error occurred. Please try again."}
      </p>
      <Button onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
