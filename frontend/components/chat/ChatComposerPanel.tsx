"use client";

import Link from "next/link";
import type { ChangeEvent, KeyboardEvent, RefObject } from "react";
import { BookOpenText, FileText, Loader2, Send, X } from "lucide-react";

import type { Document } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

interface ChatComposerPanelProps {
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  input: string;
  inputPlaceholder: string;
  isStreaming: boolean;
  isConnected: boolean;
  documents: Document[];
  activeTaggedDocs: Document[];
  mentionQuery: string | null;
  mentionSuggestions: Document[];
  onInputChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (event: KeyboardEvent) => void;
  onSelectMention: (document: Document) => void;
  onRemoveTaggedDoc: (id: string) => void;
  onSendMessage: () => void;
}

export function ChatComposerPanel({
  textareaRef,
  input,
  inputPlaceholder,
  isStreaming,
  isConnected,
  documents,
  activeTaggedDocs,
  mentionQuery,
  mentionSuggestions,
  onInputChange,
  onKeyDown,
  onSelectMention,
  onRemoveTaggedDoc,
  onSendMessage,
}: ChatComposerPanelProps) {
  return (
    <div className="border-t border-[var(--ops-border)] bg-[var(--ops-surface-strong)] px-4 py-4 md:px-5">
      <div className="mx-auto max-w-4xl space-y-3">
        {activeTaggedDocs.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {activeTaggedDocs.map((document) => (
              <Badge key={document.id} variant="outline" className="h-auto gap-1 px-2.5 py-1 text-primary">
                <FileText className="size-3" />
                {document.filename}
                <button onClick={() => onRemoveTaggedDoc(document.id)} className="rounded-full hover:text-primary/80">
                  <X className="size-3" />
                </button>
              </Badge>
            ))}
          </div>
        ) : null}

        <div className="relative">
          {mentionQuery !== null && mentionSuggestions.length > 0 ? (
            <div className="absolute bottom-full left-0 z-30 mb-3 w-full max-w-sm">
              <Card size="sm" className="gap-0">
                <div className="border-b border-[var(--ops-border)] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  Documents
                </div>
                <div className="p-1">
                  {mentionSuggestions.map((document) => (
                    <button
                      key={document.id}
                      onMouseDown={(event) => {
                        event.preventDefault();
                        onSelectMention(document);
                      }}
                      className="flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2 text-left text-sm transition-colors hover:bg-[var(--ops-control-hover)]"
                    >
                      <FileText className="size-4 shrink-0 text-primary" />
                      <span className="truncate font-medium text-foreground">{document.filename}</span>
                      <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                        {document.chunk_count}c
                      </span>
                    </button>
                  ))}
                </div>
              </Card>
            </div>
          ) : null}

          {mentionQuery !== null && documents.length === 0 ? (
            <div className="absolute bottom-full left-0 z-30 mb-3 w-full max-w-sm">
              <Card size="sm">
                <div className="space-y-2 px-3 py-3 text-sm text-muted-foreground">
                  <p>No document available. Open Context to add or manage sources.</p>
                  <Link href="/project-context?section=documents" className="inline-flex text-xs font-medium text-primary hover:underline">
                    Open documents
                  </Link>
                </div>
              </Card>
            </div>
          ) : null}

          <div className="overflow-hidden rounded-[18px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)]">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={onInputChange}
              onKeyDown={onKeyDown}
              placeholder={inputPlaceholder}
              className="max-h-[220px] min-h-[96px] resize-none border-0 bg-transparent px-4 pb-14 pt-4 text-sm leading-6 shadow-none focus-visible:border-0 focus-visible:ring-0"
              disabled={isStreaming}
            />

            <div className="flex flex-col gap-3 border-t border-[var(--ops-border)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>@ to cite a document</span>
                <span>Enter to send</span>
                <span>Shift + Enter for a new line</span>
              </div>

              <div className="flex items-center justify-end gap-2">
                <Link href="/project-context?section=documents">
                  <Button variant="ghost" size="sm" className="gap-2">
                    <BookOpenText className="size-4" />
                    Context
                  </Button>
                </Link>

                <Button
                  onClick={onSendMessage}
                  disabled={!input.trim() || isStreaming || !isConnected}
                  className="px-4"
                >
                  {isStreaming ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                  {isStreaming ? "Alex is responding…" : "Send"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
