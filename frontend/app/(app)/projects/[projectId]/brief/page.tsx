"use client";

/**
 * Project brief editor page.
 *
 * Ref: TDD-05 Section 15.2, TDD-01 Journey J5 Steps 4-6
 */

import { useParams } from "next/navigation";
import { BriefEditor } from "@/features/projects/brief-editor";

export default function BriefPage() {
  const params = useParams<{ projectId: string }>();
  return <BriefEditor projectId={params.projectId} />;
}
