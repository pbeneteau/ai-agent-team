"use client";

import { Suspense } from "react";
import { ChatPanel } from "@/components/chat/ChatPanel";

export default function ChatPage() {
  return (
    <div className="h-full min-h-0">
      <Suspense fallback={<div className="h-full min-h-0 bg-[var(--ops-canvas)]" />}>
        <ChatPanel key="alex-main-chat" />
      </Suspense>
    </div>
  );
}
