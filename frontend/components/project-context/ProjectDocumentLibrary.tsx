"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { BookOpen, Eye, FileText, Loader2, Paperclip, Search, Send, Trash2, Users } from "lucide-react";

import type { Document, DocumentPreview } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface ProjectDocumentLibraryProps {
  documents: Document[];
  loading: boolean;
  isUploading: boolean;
  uploadDescription: string;
  preview: DocumentPreview | null;
  previewLoadingId: string | null;
  briefingDocId: string | null;
  onUploadDescriptionChange: (value: string) => void;
  onUploadClick: () => void;
  onPreview: (document: Document) => void;
  onClosePreview: () => void;
  onBriefAgents: (document: Document) => void;
  onDeleteDocument: (document: Document) => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatChunkCount(count: number): string {
  return `${count} chunk${count > 1 ? "s" : ""}`;
}

export function ProjectDocumentLibrary({
  documents,
  loading,
  isUploading,
  uploadDescription,
  preview,
  previewLoadingId,
  briefingDocId,
  onUploadDescriptionChange,
  onUploadClick,
  onPreview,
  onClosePreview,
  onBriefAgents,
  onDeleteDocument,
}: ProjectDocumentLibraryProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [showAllDocuments, setShowAllDocuments] = useState(false);

  const filteredDocuments = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return documents;
    }

    return documents.filter((document) =>
      [document.filename, document.description, document.content_type]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(query)),
    );
  }, [documents, searchQuery]);

  const documentCountLabel = `${documents.length} document${documents.length > 1 ? "s" : ""}`;
  const isSearching = searchQuery.trim().length > 0;
  const visibleDocuments = isSearching || showAllDocuments ? filteredDocuments : filteredDocuments.slice(0, 5);
  const hiddenDocumentCount = Math.max(0, filteredDocuments.length - visibleDocuments.length);

  return (
    <div className="space-y-4">
      <Card className="border-black/5 bg-white/92 shadow-[0_18px_46px_-34px_rgba(15,23,42,0.2)] ring-0">
        <CardHeader className="border-b border-black/5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="text-base">Document library</CardTitle>
                <Badge variant="outline" className="border-black/6 bg-white text-muted-foreground">
                  {documentCountLabel}
                </Badge>
              </div>

              <CardDescription>
                Documents added here become a clear foundation for chat, tasks, and context broadcasts to agents.
              </CardDescription>
            </div>

            <div className="grid gap-2 sm:grid-cols-[minmax(0,260px)_minmax(0,300px)_auto] sm:items-center">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search for a document"
                  className="h-9 rounded-full bg-white pl-9"
                />
              </div>

              <Input
                value={uploadDescription}
                onChange={(event) => onUploadDescriptionChange(event.target.value)}
                placeholder="Helpful description for the next document"
                className="h-9 rounded-full bg-white"
              />

              <Button onClick={onUploadClick} disabled={isUploading} className="rounded-full gap-2">
                {isUploading ? <Loader2 className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
                {isUploading ? "Uploading…" : "Add"}
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-4 pt-4">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading documents…
            </div>
          ) : documents.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-black/8 bg-muted/30 px-4 py-8 text-sm text-muted-foreground">
              No shared document yet. Add a brief, a PDF, a spec, or an internal source to feed Alex and the agents.
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-black/8 bg-muted/30 px-4 py-8 text-sm text-muted-foreground">
              No document matches this search.
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-black/5 bg-[#fafaf7] px-4 py-3 text-xs text-muted-foreground">
                <span>
                  {isSearching
                    ? `${filteredDocuments.length} result${filteredDocuments.length > 1 ? "s" : ""} for this search.`
                    : "Compact view: the 5 most recent documents stay visible first."}
                </span>
                <span>Citation alias: `@document-name`</span>
              </div>

              <div className="overflow-hidden rounded-2xl border border-black/5 bg-[#fcfcfa]">
                <div className="hidden grid-cols-[minmax(0,1.8fr)_150px_120px_140px_auto] items-center gap-4 border-b border-black/5 bg-white/86 px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 lg:grid">
                  <span>Document</span>
                  <span>Added on</span>
                  <span>Size</span>
                  <span>Citation</span>
                  <span className="text-right">Actions</span>
                </div>

                <div className="divide-y divide-black/5">
                  {visibleDocuments.map((document) => {
                    const isPreviewing = previewLoadingId === document.id;
                    const isBriefing = briefingDocId === document.id;
                    const description =
                      document.description?.trim() ||
                      "No description provided. The file remains available for chat and agent broadcasts.";

                    return (
                      <div key={document.id} className="px-4 py-4">
                        <div className="hidden items-center gap-4 lg:grid lg:grid-cols-[minmax(0,1.8fr)_150px_120px_140px_auto]">
                          <div className="flex min-w-0 items-start gap-3">
                            <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-2xl bg-primary/8 text-primary">
                              <FileText className="size-4" />
                            </div>

                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium text-foreground">{document.filename}</p>
                              <p className="mt-1 truncate text-xs text-muted-foreground">{description}</p>
                            </div>
                          </div>

                          <div className="text-xs text-muted-foreground">{formatDate(document.created_at)}</div>

                          <div className="space-y-1 text-xs text-muted-foreground">
                            <p>{formatSize(document.size_bytes)}</p>
                            <p>{formatChunkCount(document.chunk_count)}</p>
                          </div>

                          <div>
                            <Badge variant="outline" className="border-black/6 bg-white text-muted-foreground">
                              @{document.filename}
                            </Badge>
                          </div>

                          <div className="flex flex-wrap justify-end gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              className="rounded-full"
                              onClick={() => onPreview(document)}
                            >
                              {isPreviewing ? <Loader2 className="size-3.5 animate-spin" /> : <Eye className="size-3.5" />}
                              Preview
                            </Button>

                            <Link href={`/chat?doc=${document.id}`}>
                              <Button variant="outline" size="sm" className="rounded-full gap-2">
                                <Send className="size-3.5" />
                                Cite
                              </Button>
                            </Link>

                            <Link href={`/team-builder?doc=${document.id}`}>
                              <Button variant="outline" size="sm" className="rounded-full gap-2">
                                <Users className="size-3.5" />
                                Design team
                              </Button>
                            </Link>

                            <Button
                              variant="outline"
                              size="sm"
                              className="rounded-full gap-2"
                              disabled={isBriefing}
                              onClick={() => onBriefAgents(document)}
                            >
                              {isBriefing ? <Loader2 className="size-3.5 animate-spin" /> : <BookOpen className="size-3.5" />}
                              Broadcast
                            </Button>

                            <Button
                              variant="ghost"
                              size="sm"
                              className="rounded-full text-destructive hover:text-destructive"
                              onClick={() => onDeleteDocument(document)}
                            >
                              <Trash2 className="size-3.5" />
                              Delete
                            </Button>
                          </div>
                        </div>

                        <div className="space-y-3 lg:hidden">
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-2xl bg-primary/8 text-primary">
                              <FileText className="size-4" />
                            </div>

                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium text-foreground">{document.filename}</p>
                              <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{description}</p>
                            </div>
                          </div>

                          <div className="flex flex-wrap gap-2">
                            <Badge variant="outline" className="border-black/6 bg-white text-muted-foreground">
                              @{document.filename}
                            </Badge>
                            <Badge variant="secondary" className="bg-muted text-muted-foreground">
                              {formatChunkCount(document.chunk_count)}
                            </Badge>
                            <Badge variant="secondary" className="bg-muted text-muted-foreground">
                              {formatSize(document.size_bytes)}
                            </Badge>
                            <Badge variant="secondary" className="bg-muted text-muted-foreground">
                              {formatDate(document.created_at)}
                            </Badge>
                          </div>

                          <div className="flex flex-wrap gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              className="rounded-full"
                              onClick={() => onPreview(document)}
                            >
                              {isPreviewing ? <Loader2 className="size-3.5 animate-spin" /> : <Eye className="size-3.5" />}
                              Preview
                            </Button>

                            <Link href={`/chat?doc=${document.id}`}>
                              <Button variant="outline" size="sm" className="rounded-full gap-2">
                                <Send className="size-3.5" />
                                Cite
                              </Button>
                            </Link>

                            <Link href={`/team-builder?doc=${document.id}`}>
                              <Button variant="outline" size="sm" className="rounded-full gap-2">
                                <Users className="size-3.5" />
                                Design team
                              </Button>
                            </Link>

                            <Button
                              variant="outline"
                              size="sm"
                              className="rounded-full gap-2"
                              disabled={isBriefing}
                              onClick={() => onBriefAgents(document)}
                            >
                              {isBriefing ? <Loader2 className="size-3.5 animate-spin" /> : <BookOpen className="size-3.5" />}
                              Broadcast
                            </Button>

                            <Button
                              variant="ghost"
                              size="sm"
                              className="rounded-full text-destructive hover:text-destructive"
                              onClick={() => onDeleteDocument(document)}
                            >
                              <Trash2 className="size-3.5" />
                              Delete
                            </Button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {!isSearching && hiddenDocumentCount > 0 ? (
                <div className="flex justify-center">
                  <Button
                    type="button"
                    variant="outline"
                    className="rounded-full"
                    onClick={() => setShowAllDocuments((current) => !current)}
                  >
                    {showAllDocuments
                      ? "Back to compact view"
                      : `View full library (${hiddenDocumentCount} more document${hiddenDocumentCount > 1 ? "s" : ""})`}
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      {preview ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-6 py-8 backdrop-blur-sm">
          <Card className="max-h-[85vh] w-full max-w-4xl border-black/6 bg-white shadow-[0_42px_120px_-52px_rgba(15,23,42,0.38)] ring-0">
            <CardHeader className="border-b border-black/5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <CardTitle className="text-base">{preview.filename}</CardTitle>
                  <CardDescription>
                    {formatDate(preview.created_at)} · {formatSize(preview.size_bytes)} · {formatChunkCount(preview.chunk_count)}
                  </CardDescription>
                </div>

                <Button variant="ghost" size="sm" className="rounded-full" onClick={onClosePreview}>
                  Close
                </Button>
              </div>
            </CardHeader>

            <CardContent className="space-y-4 overflow-y-auto pt-4">
              {preview.description ? (
                <div className="rounded-2xl border border-black/5 bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
                  {preview.description}
                </div>
              ) : null}

              <div className="rounded-2xl border border-black/5 bg-[#f8f8f6] px-4 py-4">
                <pre className="whitespace-pre-wrap text-sm leading-6 text-foreground">
                  {preview.preview || "No text preview available."}
                </pre>
              </div>

              {preview.truncated ? (
                <p className="text-xs text-muted-foreground">
                  Preview truncated to keep reading fast. The full document is still used on the backend for context and retrieval.
                </p>
              ) : null}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
