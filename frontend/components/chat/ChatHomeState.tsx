"use client";

import { ArrowRight, Sparkles } from "lucide-react";

import type { ChatEntryView, ChatPanelMode } from "@/components/chat/chat-shell";
import { getChatHomePrompts } from "@/components/chat/chat-shell";
import { Card, CardContent } from "@/components/ui/card";

interface ChatHomeStateProps {
  mode: ChatPanelMode;
  view?: ChatEntryView;
  title: string;
  description: string;
  onSelectPrompt: (prompt: string) => void;
}

export function ChatHomeState({ mode, view = "plan", title, description, onSelectPrompt }: ChatHomeStateProps) {
  const prompts = getChatHomePrompts(mode, view);
  const eyebrow =
    mode === "design-team" ? "Team design" : view === "ask" ? "Direct guidance" : "Plan work";
  const heading = mode === "design-team"
    ? "Let’s define the team you need"
    : view === "ask"
      ? "What do you need to understand or decide?"
      : "How do you want to move the project forward?";
  const sourceHint =
    mode === "design-team"
      ? "Uses the current brief and shared documents as the team-design baseline."
      : view === "ask"
        ? "Uses current context without forcing a broader planning sequence."
        : "Uses current context to produce an explicit plan and next actions.";

  return (
    <div className="flex min-h-full items-center justify-center px-6 py-10">
      <div className="w-full max-w-4xl space-y-7">
        <div className="mx-auto flex max-w-2xl flex-col items-center text-center">
          <div className="flex size-12 items-center justify-center rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)]">
            <Sparkles className="size-5 text-primary" />
          </div>

          <div className="mt-4 space-y-3">
            <p className="text-xs font-medium uppercase tracking-[0.28em] text-muted-foreground">{eyebrow}</p>
            <h1 className="text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
              {heading}
            </h1>
            <p className="text-balance text-base leading-7 text-muted-foreground">
              {description || title}
            </p>
          </div>

          <p className="mt-4 rounded-[14px] border border-[var(--ops-border)] bg-[var(--ops-surface-strong)] px-4 py-2 text-sm text-[var(--ops-muted-ink)]">
            {sourceHint}
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {prompts.map((prompt) => (
            <button
              key={prompt.id}
              type="button"
              onClick={() => onSelectPrompt(prompt.prompt)}
              className="text-left"
            >
              <Card className="h-full gap-0 transition-colors duration-200 hover:border-[var(--ops-border-strong)] hover:bg-[var(--ops-surface-elevated)]">
                <CardContent className="flex h-full flex-col gap-4 p-4">
                  <div className="flex size-8 items-center justify-center rounded-[12px] bg-primary/8 text-primary">
                    <prompt.Icon className="size-4" />
                  </div>

                  <div className="space-y-2">
                    <p className="text-sm font-medium text-foreground">{prompt.title}</p>
                    <p className="text-sm leading-6 text-muted-foreground">{prompt.description}</p>
                  </div>

                  <div className="mt-auto flex items-center gap-2 text-xs font-medium text-primary">
                    Use this prompt
                    <ArrowRight className="size-3.5" />
                  </div>
                </CardContent>
              </Card>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
