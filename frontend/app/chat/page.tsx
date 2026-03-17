"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { ChatPanel } from "@/components/chat/ChatPanel";

const DESIGN_TEAM_INITIAL_MESSAGES = [
  {
    role: "assistant" as const,
    content:
      "Hi! I’m Alex. Describe the project, constraints, and expected autonomy level, and I’ll propose a team for you to validate before creation.",
  },
];

export default function ChatPage() {
  return (
    <div className="h-full min-h-0">
      <Suspense fallback={<div className="h-full min-h-0 bg-[var(--ops-canvas)]" />}>
        <ChatPageContent />
      </Suspense>
    </div>
  );
}

function ChatPageContent() {
  const searchParams = useSearchParams();
  const mode = searchParams.get("mode") === "design-team" ? "design-team" : "chat";
  const view = mode === "chat" && searchParams.get("view") === "ask" ? "ask" : "plan";

  return (
    <ChatPanel
      key={`alex-main-chat-${mode}-${view}`}
      mode={mode}
      storageKey={mode === "design-team" ? "alex_design_team_history" : "alex_chat_history"}
      historyKeys={mode === "design-team" ? ["alex_design_team_history", "alex_team_builder_history"] : undefined}
      initialMessages={mode === "design-team" ? DESIGN_TEAM_INITIAL_MESSAGES : undefined}
      title="Alex"
      description={
        mode === "design-team"
          ? "Shape or evolve the operating team directly inside Alex."
          : view === "ask"
          ? "Direct operator conversation for decisions, clarifications, and fast interpretation of the current state."
          : "Use Alex to turn a need into an explicit plan, the right context, and the clearest next action."
      }
      contextLabel={mode === "design-team" ? "Design Team" : view === "ask" ? "Ask Alex" : "Plan Work"}
      inputPlaceholder={
        mode === "design-team"
          ? "Describe the project, expected roles, and team guardrails…"
          : view === "ask"
          ? "Ask Alex a direct question… (@ to cite a document, Enter to send)"
          : "Describe the work to scope… (@ to cite a document, Enter to send)"
      }
    />
  );
}
