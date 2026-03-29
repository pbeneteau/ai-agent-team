"use client";

/**
 * Project document management page.
 *
 * Ref: TDD-05 Section 15.2, TDD-01 Journey J5 Step 7
 */

import { useParams } from "next/navigation";
import { DocumentManager } from "@/features/projects/document-manager";

export default function DocumentsPage() {
  const params = useParams<{ projectId: string }>();
  return <DocumentManager projectId={params.projectId} />;
}
