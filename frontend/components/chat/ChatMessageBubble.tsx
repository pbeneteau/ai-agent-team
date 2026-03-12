"use client";

import { AlertCircle, Bot, Loader2, User } from "lucide-react";

import type { ChatMessage, ChatPendingRequest } from "@/components/chat/chat-streaming";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { MarkdownContent } from "@/components/ui/markdown-content";
import { cn } from "@/lib/utils";

interface ChatMessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
  pendingRequest?: ChatPendingRequest | null;
  showWaitingState?: boolean;
}

export function ChatMessageBubble({
  message,
  isStreaming = false,
  pendingRequest,
  showWaitingState = false,
}: ChatMessageBubbleProps) {
  if (message.role === "error") {
    return (
      <div className="flex justify-center">
        <div className="flex max-w-2xl items-start gap-3 rounded-[24px] border border-destructive/15 bg-destructive/5 px-4 py-3 text-sm text-destructive shadow-[0_18px_36px_-28px_rgba(220,38,38,0.45)]">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <span>{message.content}</span>
        </div>
      </div>
    );
  }

  const isAssistant = message.role === "assistant";
  const avatar = isAssistant ? (
    <div className="flex size-8 shrink-0 items-center justify-center rounded-[18px] border border-black/5 bg-white text-primary shadow-[0_14px_28px_-22px_rgba(15,23,42,0.26)]">
      <Bot className="size-4" />
    </div>
  ) : (
    <div className="flex size-8 shrink-0 items-center justify-center rounded-[18px] border border-black/5 bg-white text-muted-foreground shadow-[0_14px_28px_-22px_rgba(15,23,42,0.2)]">
      <User className="size-4" />
    </div>
  );

  return (
    <div className={cn("flex gap-3", isAssistant ? "justify-start" : "justify-end")}>
      {isAssistant ? avatar : null}

      {isAssistant ? (
        <Card
          size="sm"
          className="max-w-[min(46rem,100%)] gap-2 border border-black/5 bg-white/92 shadow-[0_20px_44px_-34px_rgba(15,23,42,0.22)] ring-0"
        >
          <div className="flex items-center gap-2 px-3 pt-3 text-[11px] text-muted-foreground">
            <span className="font-medium text-foreground">Alex</span>
            {message.interrupted ? (
              <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
                Response interrupted
              </Badge>
            ) : null}
            {isStreaming ? (
              <Badge variant="outline" className="border-primary/15 bg-primary/5 text-primary">
                Generating
              </Badge>
            ) : null}
          </div>

          <CardContent className="pb-3 pt-0">
            {showWaitingState && pendingRequest ? (
              <StreamingPlaceholder pendingRequest={pendingRequest} />
            ) : (
              <div className="space-y-3">
                <MarkdownContent
                  content={message.content}
                  className="prose-sm max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
                />
                {isStreaming ? (
                  <div className="flex items-center gap-1.5 text-primary">
                    <span className="size-1.5 animate-pulse rounded-full bg-current [animation-delay:-0.2s]" />
                    <span className="size-1.5 animate-pulse rounded-full bg-current [animation-delay:-0.1s]" />
                    <span className="size-1.5 animate-pulse rounded-full bg-current" />
                  </div>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="max-w-[min(38rem,100%)] rounded-[26px] bg-primary px-4 py-3 text-sm leading-6 text-primary-foreground shadow-[0_22px_40px_-32px_rgba(79,70,229,0.5)]">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      )}

      {isAssistant ? null : avatar}
    </div>
  );
}

function StreamingPlaceholder({ pendingRequest }: { pendingRequest: ChatPendingRequest }) {
  const { Icon } = pendingRequest;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-primary/75">
        <Icon className="size-3.5" />
        Preparing
      </div>

      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">{pendingRequest.label}</p>
        <p className="text-sm leading-6 text-muted-foreground">{pendingRequest.detail}</p>
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" />
        The response will appear as soon as it is stable.
      </div>
    </div>
  );
}
