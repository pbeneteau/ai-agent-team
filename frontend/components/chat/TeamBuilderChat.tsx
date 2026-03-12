"use client";

import { ChatPanel } from "@/components/chat/ChatPanel";

interface TeamBuilderChatProps {
  onTeamCreated?: (data: unknown) => void;
}

const TEAM_BUILDER_INITIAL_MESSAGES = [
  {
    role: "assistant" as const,
    content:
      "Hi! I’m Alex. Describe the project, its constraints, and the expected autonomy level, and I’ll propose a team for you to validate before creation.",
  },
];

export function TeamBuilderChat({ onTeamCreated }: TeamBuilderChatProps) {
  return (
    <ChatPanel
      key="alex-team-builder-chat"
      onTeamCreated={onTeamCreated}
      storageKey="alex_team_builder_history"
      mode="team-builder"
      inputPlaceholder="Describe the project, expected roles, and team guardrails…"
      title="Alex team design"
      description="Describe the context, constraints, and expected outcome. Alex will then structure an agent team for validation before creation."
      contextLabel="Team design"
      initialMessages={TEAM_BUILDER_INITIAL_MESSAGES}
    />
  );
}
