"use client";

/**
 * Onboarding page — multi-step wizard.
 *
 * Ref: TDD-05 Section 13, TDD-01 Journey J1
 * Step 1: Company context form
 * Step 2: Generated roster preview with inline editing
 * On confirm: redirect to /projects
 */

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useOnboarding } from "@/lib/hooks/use-onboarding";
import { OnboardingForm, type OnboardingFormValues } from "@/features/onboarding/onboarding-form";
import { RosterPreview } from "@/features/onboarding/roster-preview";
import type { AgentListItem, OnboardingRequest } from "@/lib/types/api";

type Step = "form" | "preview";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("form");
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [isConfirming, setIsConfirming] = useState(false);

  const onboarding = useOnboarding();

  const handleFormSubmit = useCallback(
    (values: OnboardingFormValues) => {
      const payload: OnboardingRequest = {
        company_name: values.company_name,
        domain_description: values.domain_description,
        use_case: "code",
        ...(values.product_description ? { product_description: values.product_description } : {}),
        ...(values.tech_stack ? { tech_stack: values.tech_stack } : {}),
        ...(values.company_stage ? { company_stage: values.company_stage } : {}),
        ...(values.existing_team ? { existing_team: values.existing_team } : {}),
        ...(values.team_size ? { team_size: values.team_size } : {}),
      };

      onboarding.mutate(payload, {
        onSuccess: (data) => {
          setAgents(data.agents);
          setStep("preview");
        },
        onError: (error) => {
          toast.error(error.message || "Failed to generate team");
        },
      });
    },
    [onboarding],
  );

  const handleConfirmRoster = useCallback(
    async (
      edits: Map<string, Partial<{ name: string; specialization: string; description: string }>>,
      removedIds: Set<string>,
      newAgents: { name: string; specialization: string; description: string }[],
    ) => {
      setIsConfirming(true);
      try {
        const promises: Promise<unknown>[] = [];

        for (const [agentId, changes] of edits) {
          promises.push(api.roster.update(agentId, changes));
        }

        for (const id of removedIds) {
          promises.push(api.roster.archive(id));
        }

        for (const agent of newAgents) {
          promises.push(api.roster.create(agent));
        }

        await Promise.all(promises);
        toast.success("Your agency is ready!");
        router.replace("/projects");
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to finalize roster");
      } finally {
        setIsConfirming(false);
      }
    },
    [router],
  );

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-xl space-y-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <Zap className="h-10 w-10 text-[var(--color-accent)]" />
          <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
            {step === "form" ? "Tell us about your company" : "Review Your Agency"}
          </h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            {step === "form"
              ? "We'll build a tailored AI team based on your needs."
              : "Your AI team has been assembled. Customize it before getting started."}
          </p>
          <div className="flex gap-2 pt-2">
            <div
              className={`h-1.5 w-12 rounded-full transition-colors ${
                step === "form" ? "bg-[var(--color-accent)]" : "bg-[var(--color-bg-tertiary)]"
              }`}
            />
            <div
              className={`h-1.5 w-12 rounded-full transition-colors ${
                step === "preview" ? "bg-[var(--color-accent)]" : "bg-[var(--color-bg-tertiary)]"
              }`}
            />
          </div>
        </div>

        {step === "form" ? (
          <OnboardingForm onSubmit={handleFormSubmit} isPending={onboarding.isPending} />
        ) : (
          <RosterPreview agents={agents} onConfirm={handleConfirmRoster} isPending={isConfirming} />
        )}
      </div>
    </div>
  );
}
