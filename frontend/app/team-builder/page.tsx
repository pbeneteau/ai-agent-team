"use client";

import { Suspense } from "react";
import { useRouter } from "next/navigation";
import { TeamBuilderChat } from "@/components/chat/TeamBuilderChat";

export default function TeamBuilderPage() {
  const router = useRouter();

  return (
    <div className="h-full min-h-0">
      <Suspense fallback={<div className="h-full min-h-0 bg-[var(--ops-canvas)]" />}>
        <TeamBuilderChat
          onTeamCreated={() => {
            setTimeout(() => router.push("/team"), 2000);
          }}
        />
      </Suspense>
    </div>
  );
}
