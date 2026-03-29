"use client";

/**
 * Artifact action buttons — Approve + Cancel.
 *
 * Ref: TDD-05 Section 10.2, TDD-01 J2 Step 14
 */

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { CheckCircle, XCircle, Loader2, AlertCircle } from "lucide-react";
import { useApproveArtifact, useCancelArtifact } from "@/lib/hooks/use-artifacts";
import type { ArtifactType } from "@/lib/types/api";

interface ArtifactActionsProps {
  artifactId: string;
  artifactType: ArtifactType;
}

export function ArtifactActions({ artifactId, artifactType }: ArtifactActionsProps) {
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const approveArtifact = useApproveArtifact();
  const cancelArtifact = useCancelArtifact();

  const handleApprove = useCallback(() => {
    approveArtifact.mutate(artifactId, {
      onSuccess: () => toast.success("Artifact approved"),
      onError: (error) => toast.error(error.message || "Failed to approve"),
    });
  }, [artifactId, approveArtifact]);

  const handleCancel = useCallback(() => {
    cancelArtifact.mutate(artifactId, {
      onSuccess: () => {
        setShowCancelDialog(false);
        toast.success("Artifact cancelled");
      },
      onError: (error) => toast.error(error.message || "Failed to cancel"),
    });
  }, [artifactId, cancelArtifact]);

  return (
    <>
      <div className="flex items-center gap-2">
        {/* Prose artifacts have an in-app Approve button; code artifacts approve via PR merge */}
        {artifactType === "prose" && (
          <Button onClick={handleApprove} disabled={approveArtifact.isPending}>
            {approveArtifact.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <CheckCircle className="h-4 w-4" />
            )}
            Approve
          </Button>
        )}
        <Button variant="outline" onClick={() => setShowCancelDialog(true)}>
          <XCircle className="h-4 w-4" />
          Cancel
        </Button>
      </div>

      <Dialog open={showCancelDialog} onOpenChange={setShowCancelDialog}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-[var(--color-danger)]" />
              Cancel Artifact
            </DialogTitle>
            <DialogDescription>
              Are you sure? This artifact will be permanently cancelled.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCancelDialog(false)}>
              Keep
            </Button>
            <Button variant="destructive" onClick={handleCancel} disabled={cancelArtifact.isPending}>
              {cancelArtifact.isPending ? (
                <>
                  <Loader2 className="animate-spin" />
                  Cancelling...
                </>
              ) : (
                "Cancel Artifact"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
