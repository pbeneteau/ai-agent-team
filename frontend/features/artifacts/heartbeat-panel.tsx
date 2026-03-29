"use client";

/**
 * Heartbeat panel — execution progress display.
 *
 * Ref: TDD-05 Section 9, TDD-01 Journey J2 Step 8
 *
 * Shows step indicators, progress bar, live cost counter, cancel button.
 * Polls every 3s via useArtifactStatus (already configured in hooks).
 * WebSocket `execution.wave_completed` events trigger immediate invalidation.
 */

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { CheckCircle, Loader2, Circle, XCircle, AlertCircle } from "lucide-react";
import { useCancelArtifact } from "@/lib/hooks/use-artifacts";
import type { ArtifactStatusResponse } from "@/lib/types/api";

interface HeartbeatPanelProps {
  artifactId: string;
  title: string;
  status: ArtifactStatusResponse;
}

export function HeartbeatPanel({ artifactId, title, status }: HeartbeatPanelProps) {
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const cancelArtifact = useCancelArtifact();

  const wave = status.wave;
  const currentStep = wave?.current_step ?? 0;
  const totalSteps = wave?.total_steps ?? 1;
  const stepLabels = wave?.step_labels ?? [];
  const costUsd = wave?.cost_usd ?? 0;
  const progressPct = totalSteps > 0 ? Math.round((currentStep / totalSteps) * 100) : 0;

  const handleCancel = useCallback(() => {
    cancelArtifact.mutate(artifactId, {
      onSuccess: () => {
        setShowCancelDialog(false);
        toast.success("Execution cancelled. Completed work is preserved.");
      },
      onError: (error) => {
        toast.error(error.message || "Failed to cancel execution");
      },
    });
  }, [artifactId, cancelArtifact]);

  return (
    <div className="mx-auto max-w-lg space-y-6 py-8">
      <div className="text-center space-y-2">
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">{title}</h2>
        <p className="text-sm text-[var(--color-text-secondary)]">
          {wave?.status === "queued" ? "Queued..." : "Drafting..."}
        </p>
      </div>

      {/* Step indicators */}
      <div className="space-y-2">
        {stepLabels.map((label, i) => {
          const stepNum = i + 1;
          const isComplete = stepNum < currentStep;
          const isActive = stepNum === currentStep;
          const isPending = stepNum > currentStep;

          return (
            <div key={i} className="flex items-center gap-3">
              {isComplete ? (
                <CheckCircle className="h-5 w-5 shrink-0 text-[var(--color-success)]" />
              ) : isActive ? (
                <Loader2 className="h-5 w-5 shrink-0 animate-spin text-[var(--color-accent)]" />
              ) : (
                <Circle className="h-5 w-5 shrink-0 text-[var(--color-text-tertiary)]" />
              )}
              <span
                className={`text-sm ${
                  isComplete
                    ? "text-[var(--color-text-secondary)]"
                    : isActive
                      ? "font-medium text-[var(--color-text-primary)]"
                      : "text-[var(--color-text-tertiary)]"
                }`}
              >
                Step {stepNum}/{totalSteps}: {label}
              </span>
            </div>
          );
        })}

        {stepLabels.length === 0 && (
          <div className="flex items-center gap-3">
            <Loader2 className="h-5 w-5 shrink-0 animate-spin text-[var(--color-accent)]" />
            <span className="text-sm text-[var(--color-text-primary)]">Processing...</span>
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-[var(--color-text-primary)]">Progress</span>
          <span className="tabular-nums text-[var(--color-text-secondary)]">{progressPct}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-bg-tertiary)]">
          <div
            className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-300"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Cost + estimate */}
      <div className="flex items-center justify-center gap-4 text-sm text-[var(--color-text-secondary)]">
        <span>Cost: ${costUsd.toFixed(2)}</span>
      </div>

      {/* Cancel button */}
      <div className="flex justify-center">
        <Button variant="outline" onClick={() => setShowCancelDialog(true)}>
          <XCircle className="h-4 w-4" />
          Cancel Execution
        </Button>
      </div>

      {/* Cancel confirmation dialog */}
      <Dialog open={showCancelDialog} onOpenChange={setShowCancelDialog}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-[var(--color-danger)]" />
              Cancel Execution
            </DialogTitle>
            <DialogDescription>
              Are you sure? Execution will be stopped. Any completed work is preserved.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCancelDialog(false)}>
              Keep Running
            </Button>
            <Button variant="destructive" onClick={handleCancel} disabled={cancelArtifact.isPending}>
              {cancelArtifact.isPending ? (
                <>
                  <Loader2 className="animate-spin" />
                  Cancelling...
                </>
              ) : (
                "Cancel Execution"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
