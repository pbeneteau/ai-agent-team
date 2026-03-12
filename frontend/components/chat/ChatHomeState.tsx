"use client";

import { ArrowRight, Sparkles } from "lucide-react";

import type { ChatPanelMode } from "@/components/chat/chat-shell";
import { getChatHomePrompts } from "@/components/chat/chat-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface ChatHomeStateProps {
  mode: ChatPanelMode;
  title: string;
  description: string;
  onSelectPrompt: (prompt: string) => void;
}

export function ChatHomeState({ mode, title, description, onSelectPrompt }: ChatHomeStateProps) {
  const prompts = getChatHomePrompts(mode);
  const eyebrow = mode === "team-builder" ? "Team architecture" : "Alex control desk";
  const heading =
    mode === "team-builder"
      ? "Let’s define the team you need"
      : "How do you want to move the project forward?";
  const sourceHint =
    mode === "team-builder"
      ? "The global brief and shared documents remain the reference. Here, Alex designs the right team structure from that foundation."
      : "The global brief and shared documents remain the reference. Here, Alex uses them to plan and arbitrate.";

  return (
    <div className="flex min-h-full items-center justify-center px-6 py-10">
      <div className="w-full max-w-4xl space-y-10">
        <div className="mx-auto flex max-w-2xl flex-col items-center text-center">
          <div className="flex size-16 items-center justify-center rounded-[28px] border border-black/5 bg-white shadow-[0_12px_35px_-24px_rgba(15,23,42,0.28)]">
            <Sparkles className="size-6 text-primary" />
          </div>

          <div className="mt-6 space-y-3">
            <p className="text-xs font-medium uppercase tracking-[0.28em] text-muted-foreground">{eyebrow}</p>
            <h1 className="text-balance text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
              {heading}
            </h1>
            <p className="text-balance text-base leading-7 text-muted-foreground">
              {description || title}
            </p>
          </div>

          <div className="mt-5 rounded-2xl border border-[var(--ops-border)] bg-[var(--ops-surface-strong)] px-4 py-3 text-left shadow-[0_18px_45px_-36px_rgba(15,23,42,0.22)]">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--ops-muted-ink)]">
              Source of truth
            </p>
            <p className="mt-2 text-sm leading-6 text-[var(--ops-ink)]">{sourceHint}</p>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {prompts.map((prompt) => (
            <button
              key={prompt.id}
              type="button"
              onClick={() => onSelectPrompt(prompt.prompt)}
              className="text-left"
            >
              <Card className="h-full gap-0 border border-black/5 bg-white/92 shadow-[0_18px_45px_-36px_rgba(15,23,42,0.28)] transition-all duration-200 hover:-translate-y-0.5 hover:border-black/8 hover:bg-white hover:shadow-[0_22px_50px_-30px_rgba(15,23,42,0.25)]">
                <CardContent className="flex h-full flex-col gap-5 p-5">
                  <div className="flex size-10 items-center justify-center rounded-2xl bg-primary/8 text-primary">
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

        <div className="flex justify-center">
          <Button variant="ghost" className="rounded-full px-4 text-muted-foreground">
            Alex can also start from a free-form instruction, a cited document, or an already published brief.
          </Button>
        </div>
      </div>
    </div>
  );
}
