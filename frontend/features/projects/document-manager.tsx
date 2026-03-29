"use client";

/**
 * Document manager — drag-and-drop upload + document list.
 *
 * Ref: TDD-05 Section 15.2, TDD-01 Journey J5 Step 7
 */

import { useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Upload, Trash2, FileText, Loader2, AlertCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { useProjectDocuments, useUploadDocument, useDeleteDocument } from "@/lib/hooks/use-projects";
import type { DocumentItem } from "@/lib/types/api";

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB
const ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/json",
  "application/x-yaml",
  "text/yaml",
];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const statusConfig: Record<DocumentItem["processing_status"], { label: string; variant: "outline" | "default" | "secondary" | "destructive" }> = {
  pending: { label: "Pending", variant: "outline" },
  processing: { label: "Processing", variant: "secondary" },
  ready: { label: "Ready", variant: "default" },
  failed: { label: "Failed", variant: "destructive" },
};

interface DocumentManagerProps {
  projectId: string;
}

export function DocumentManager({ projectId }: DocumentManagerProps) {
  const { data, isLoading } = useProjectDocuments(projectId);
  const uploadDoc = useUploadDocument(projectId);
  const deleteDoc = useDeleteDocument(projectId);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentItem | null>(null);

  const handleUpload = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;

      for (const file of Array.from(files)) {
        if (file.size > MAX_FILE_SIZE) {
          toast.error(`${file.name} exceeds 20 MB limit`);
          continue;
        }

        const formData = new FormData();
        formData.append("file", file);

        uploadDoc.mutate(formData, {
          onSuccess: () => toast.success(`${file.name} uploaded`),
          onError: (error) => toast.error(error.message || `Failed to upload ${file.name}`),
        });
      }
    },
    [uploadDoc],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      handleUpload(e.dataTransfer.files);
    },
    [handleUpload],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const confirmDelete = useCallback(() => {
    if (!deleteTarget) return;
    deleteDoc.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success(`${deleteTarget.filename} deleted`);
        setDeleteTarget(null);
      },
      onError: (error) => toast.error(error.message || "Failed to delete document"),
    });
  }, [deleteTarget, deleteDoc]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full rounded-[var(--radius-lg)]" />
        {[1, 2].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  const documents = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Documents</h2>
        <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
          <Upload className="h-3.5 w-3.5" />
          Upload
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md,.csv,.json,.yaml,.yml"
          className="hidden"
          onChange={(e) => handleUpload(e.target.files)}
        />
      </div>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`flex flex-col items-center justify-center gap-2 rounded-[var(--radius-lg)] border-2 border-dashed p-8 transition-colors ${
          isDragging
            ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
            : "border-[var(--color-border-primary)] hover:border-[var(--color-border-secondary)]"
        }`}
      >
        <Upload className="h-6 w-6 text-[var(--color-text-tertiary)]" />
        <p className="text-sm text-[var(--color-text-secondary)]">
          Drag & drop files here, or click Upload
        </p>
        <p className="text-xs text-[var(--color-text-tertiary)]">
          PDF, DOCX, TXT, MD, CSV, JSON, YAML — max 20 MB
        </p>
      </div>

      {/* Document list */}
      {documents.length > 0 && (
        <div className="divide-y divide-[var(--color-border-primary)] rounded-[var(--radius-lg)] border border-[var(--color-border-primary)]">
          {documents.map((doc) => {
            const status = statusConfig[doc.processing_status];
            return (
              <div
                key={doc.id}
                className="flex items-center justify-between px-4 py-3"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <FileText className="h-4 w-4 shrink-0 text-[var(--color-text-secondary)]" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                      {doc.filename}
                    </p>
                    <p className="text-xs text-[var(--color-text-tertiary)]">
                      {formatFileSize(doc.size_bytes)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant={status.variant}>{status.label}</Badge>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    onClick={() => setDeleteTarget(doc)}
                    aria-label={`Delete ${doc.filename}`}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {documents.length === 0 && (
        <p className="py-4 text-center text-sm text-[var(--color-text-tertiary)]">
          No documents uploaded yet. Upload reference materials for your agents.
        </p>
      )}

      {/* Delete confirmation dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-[var(--color-danger)]" />
              Delete Document
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>{deleteTarget?.filename}</strong>? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={deleteDoc.isPending}>
              {deleteDoc.isPending ? (
                <>
                  <Loader2 className="animate-spin" />
                  Deleting...
                </>
              ) : (
                "Delete"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
