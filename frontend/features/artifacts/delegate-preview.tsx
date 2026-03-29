"use client";

/**
 * Delegation preview modal — shows plan, team, cost, override controls.
 *
 * Ref: TDD-05 Section 8.4, TDD-01 Journey J2 Step 6
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Loader2, Users, Layers, DollarSign, Zap } from "lucide-react";
import type { DelegatePlan } from "@/lib/types/api";

interface DelegatePreviewProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  plan: DelegatePlan;
  onConfirm: () => void;
  isPending: boolean;
}

export function DelegatePreview({
  open,
  onOpenChange,
  plan,
  onConfirm,
  isPending,
}: DelegatePreviewProps) {
  const team = plan.assembled_team as Record<string, unknown>;
  const dagPlan = plan.dag_plan as Record<string, unknown>;

  // Extract team members from the assembled_team object
  const teamMembers = extractTeamMembers(team);
  const waves = extractWaves(dagPlan, plan.step_labels);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-[var(--color-accent)]" />
            Delegation Preview
          </DialogTitle>
          <DialogDescription>
            Review the execution plan before confirming.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 max-h-[60vh] overflow-y-auto">
          {/* Template */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-primary)]">
              <Layers className="h-4 w-4 text-[var(--color-text-secondary)]" />
              Execution Plan
            </div>
            <Badge variant="secondary">{plan.template_key.replace(/-/g, " ")}</Badge>
          </div>

          <Separator />

          {/* Waves / Steps */}
          <div className="space-y-2">
            <p className="text-sm font-medium text-[var(--color-text-primary)]">Steps</p>
            <div className="space-y-2">
              {waves.map((wave, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] px-3 py-2"
                >
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-accent)] text-[10px] font-bold text-[var(--color-text-inverse)]">
                    {i + 1}
                  </span>
                  <span className="text-sm text-[var(--color-text-primary)]">{wave.label}</span>
                  {wave.agents.length > 0 && (
                    <span className="ml-auto text-xs text-[var(--color-text-tertiary)]">
                      {wave.agents.join(", ")}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          <Separator />

          {/* Team */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-primary)]">
              <Users className="h-4 w-4 text-[var(--color-text-secondary)]" />
              Assembled Team ({teamMembers.length})
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {teamMembers.map((member, i) => (
                <div
                  key={i}
                  className="rounded-[var(--radius-sm)] border border-[var(--color-border-primary)] px-3 py-2"
                >
                  <p className="text-sm font-medium text-[var(--color-text-primary)]">{member.name}</p>
                  <p className="text-xs text-[var(--color-text-secondary)]">{member.role}</p>
                </div>
              ))}
            </div>
          </div>

          <Separator />

          {/* Cost estimate */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-primary)]">
              <DollarSign className="h-4 w-4 text-[var(--color-text-secondary)]" />
              Estimated Cost
            </div>
            <span className="text-lg font-semibold text-[var(--color-text-primary)]">
              ${plan.estimated_cost_usd.toFixed(2)}
            </span>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={isPending}>
            {isPending ? (
              <>
                <Loader2 className="animate-spin" />
                Delegating...
              </>
            ) : (
              "Confirm Delegation"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Helper to extract team member info from the assembled_team object
function extractTeamMembers(team: Record<string, unknown>): { name: string; role: string }[] {
  // The assembled_team can be an object with agent slots or an array
  if (Array.isArray(team)) {
    return team.map((member) => ({
      name: String((member as Record<string, unknown>).agent_name ?? (member as Record<string, unknown>).name ?? "Agent"),
      role: String((member as Record<string, unknown>).specialization ?? (member as Record<string, unknown>).role ?? ""),
    }));
  }

  // Object form: { slot_name: { agent_id, agent_name, ... } }
  return Object.entries(team).map(([slot, value]) => {
    const member = value as Record<string, unknown>;
    return {
      name: String(member.agent_name ?? member.name ?? slot),
      role: String(member.specialization ?? slot.replace(/_/g, " ")),
    };
  });
}

// Helper to extract wave info
function extractWaves(
  dagPlan: Record<string, unknown>,
  stepLabels: string[],
): { label: string; agents: string[] }[] {
  // If step_labels exist, use them directly
  if (stepLabels.length > 0) {
    return stepLabels.map((label) => ({ label, agents: [] }));
  }

  // Fallback: parse the dag_plan if it has a waves array
  const waves = dagPlan.waves as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(waves)) {
    return waves.map((wave, i) => ({
      label: String(wave.step_label ?? wave.label ?? `Wave ${i + 1}`),
      agents: Array.isArray(wave.agents)
        ? wave.agents.map((a) => String((a as Record<string, unknown>).name ?? a))
        : [],
    }));
  }

  return [{ label: "Single execution wave", agents: [] }];
}
