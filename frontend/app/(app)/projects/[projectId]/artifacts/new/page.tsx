"use client";

/**
 * New artifact page — Smart Brief form + delegation.
 *
 * Ref: TDD-05 Section 8, TDD-01 Journeys J2/J3
 */

import { useParams } from "next/navigation";
import { SmartBriefForm } from "@/features/artifacts/smart-brief-form";

export default function NewArtifactPage() {
  const params = useParams<{ projectId: string }>();

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">New Task</h2>
        <p className="text-sm text-[var(--color-text-secondary)]">
          Describe the code you need. Your AI team will plan, build, and review.
        </p>
      </div>
      <SmartBriefForm projectId={params.projectId} />
    </div>
  );
}
