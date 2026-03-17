import { Suspense } from "react";
import { ProjectContextHub } from "@/components/project-context/ProjectContextHub";

export default function ProjectContextPage() {
  return (
    <Suspense fallback={<div className="h-full min-h-0 bg-[var(--ops-canvas)]" />}>
      <ProjectContextHub />
    </Suspense>
  );
}
