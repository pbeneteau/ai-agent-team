"use client";

/**
 * Smart Brief form — the single most important UI.
 *
 * Ref: TDD-05 Section 8, TDD-01 Journeys J2/J3
 *
 * Flow:
 * 1. Fill form with RHF + Zod validation
 * 2. Click Validate → POST /api/artifacts/{id}/validate
 * 3. See inline issues with matched_text highlighting
 * 4. Fix & re-validate
 * 5. Click Delegate → POST /api/artifacts/{id}/delegate (confirm: false) → preview modal
 * 6. Confirm → POST /api/artifacts/{id}/delegate (confirm: true) → redirect
 */

import { useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useForm, Controller } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Loader2, FileText, Code, CheckCircle } from "lucide-react";
import { useCreateArtifact, useValidateArtifact, useDelegateArtifact } from "@/lib/hooks/use-artifacts";
import { useGitConnections, useGitRepos } from "@/lib/hooks/use-git-providers";
import { FieldIssues, SufficiencySummary } from "@/features/artifacts/sufficiency-feedback";
import { DelegatePreview } from "@/features/artifacts/delegate-preview";
import type { SufficiencyIssue, SufficiencyResponse, DelegatePlan, DelegatePreviewResponse } from "@/lib/types/api";

const briefSchema = z.object({
  artifact_type: z.enum(["prose", "code"]),
  title: z.string().min(1, "Title is required").max(200),
  goal: z.string().max(500),
  target_audience: z.string().max(200),
  context: z.string().max(2000),
  description: z.string().min(10, "Description must be at least 10 characters").max(5000),
  max_budget_usd: z.number().min(0.5),
  // Code-only
  git_connection_id: z.string(),
  git_repo_url: z.string(),
  git_base_branch: z.string(),
});

type BriefFormValues = z.infer<typeof briefSchema>;

interface SmartBriefFormProps {
  projectId: string;
}

export function SmartBriefForm({ projectId }: SmartBriefFormProps) {
  const router = useRouter();
  const createArtifact = useCreateArtifact();

  const [artifactId, setArtifactId] = useState<string | null>(null);
  const [sufficiency, setSufficiency] = useState<SufficiencyResponse | null>(null);
  const [delegatePlan, setDelegatePlan] = useState<DelegatePlan | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isDelegating, setIsDelegating] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  const {
    register,
    handleSubmit,
    control,
    watch,
    getValues,
    formState: { errors },
  } = useForm<BriefFormValues>({
    resolver: zodResolver(briefSchema),
    defaultValues: {
      artifact_type: "prose",
      title: "",
      goal: "",
      target_audience: "",
      context: "",
      description: "",
      max_budget_usd: 5.0,
      git_connection_id: "",
      git_repo_url: "",
      git_base_branch: "",
    },
  });

  const artifactType = watch("artifact_type");
  const gitConnectionId = watch("git_connection_id");

  // Git provider data (for code artifacts)
  const { data: gitConnections } = useGitConnections();
  const { data: gitRepos } = useGitRepos(gitConnectionId);

  const connections = gitConnections?.items ?? [];
  const repos = gitRepos?.items ?? [];

  // Group issues by field for inline display
  const issuesByField = useMemo(() => {
    if (!sufficiency) return new Map<string, SufficiencyIssue[]>();
    const map = new Map<string, SufficiencyIssue[]>();
    for (const issue of sufficiency.issues) {
      const existing = map.get(issue.field) ?? [];
      existing.push(issue);
      map.set(issue.field, existing);
    }
    return map;
  }, [sufficiency]);

  const hasCriticalIssues = sufficiency?.issues.some((i) => i.severity === "critical") ?? false;
  const isEligible = sufficiency?.is_sufficient === true;

  // Step 1: Create artifact + validate
  const handleValidate = useCallback(
    async (values: BriefFormValues) => {
      setIsValidating(true);
      setSufficiency(null);

      try {
        let id = artifactId;

        if (!id) {
          // Create the artifact first
          const artifact = await createArtifact.mutateAsync({
            project_id: projectId,
            artifact_type: values.artifact_type,
            title: values.title,
            goal: values.goal || undefined,
            target_audience: values.target_audience || undefined,
            context: values.context || undefined,
            description: values.description,
            max_budget_usd: values.max_budget_usd || undefined,
            git_repo_url: values.git_repo_url || undefined,
            git_base_branch: values.git_base_branch || undefined,
          });
          id = artifact.id;
          setArtifactId(id);
        }

        // Validate
        const { api } = await import("@/lib/api");
        const result = await api.artifacts.validate(id);
        setSufficiency(result);

        if (result.is_sufficient) {
          toast.success("Brief is sufficient!");
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Validation failed");
      } finally {
        setIsValidating(false);
      }
    },
    [artifactId, projectId, createArtifact],
  );

  // Step 2: Request delegation preview
  const handleDelegate = useCallback(async () => {
    if (!artifactId) return;
    setIsDelegating(true);

    try {
      const { api } = await import("@/lib/api");
      const result = (await api.artifacts.delegate(artifactId, { confirm: false })) as DelegatePreviewResponse;
      setDelegatePlan(result.plan);
      setShowPreview(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to generate plan");
    } finally {
      setIsDelegating(false);
    }
  }, [artifactId]);

  // Step 3: Confirm delegation
  const handleConfirmDelegation = useCallback(async () => {
    if (!artifactId) return;
    setIsConfirming(true);

    try {
      const { api } = await import("@/lib/api");
      await api.artifacts.delegate(artifactId, { confirm: true });
      toast.success("Delegation confirmed! Execution started.");
      setShowPreview(false);
      router.push(`/projects/${projectId}/artifacts/${artifactId}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Delegation failed");
    } finally {
      setIsConfirming(false);
    }
  }, [artifactId, projectId, router]);

  return (
    <div className="space-y-6">
      <form onSubmit={handleSubmit(handleValidate)} className="space-y-6">
        {/* Artifact Type Toggle */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-[var(--color-text-primary)]">
            Artifact Type <span className="text-[var(--color-danger)]">*</span>
          </label>
          <Controller
            name="artifact_type"
            control={control}
            render={({ field }) => (
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => field.onChange("prose")}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-[var(--radius-md)] border px-4 py-2.5 text-sm font-medium transition-colors ${
                    field.value === "prose"
                      ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)] text-[var(--color-accent)]"
                      : "border-[var(--color-border-primary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
                  }`}
                >
                  <FileText className="h-4 w-4" />
                  Document
                </button>
                <button
                  type="button"
                  onClick={() => field.onChange("code")}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-[var(--radius-md)] border px-4 py-2.5 text-sm font-medium transition-colors ${
                    field.value === "code"
                      ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)] text-[var(--color-accent)]"
                      : "border-[var(--color-border-primary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
                  }`}
                >
                  <Code className="h-4 w-4" />
                  Code
                </button>
              </div>
            )}
          />
        </div>

        {/* Title */}
        <div className="space-y-2">
          <label htmlFor="title" className="text-sm font-medium text-[var(--color-text-primary)]">
            Title <span className="text-[var(--color-danger)]">*</span>
          </label>
          <Input
            id="title"
            placeholder="Q3 Competitive Analysis"
            aria-invalid={!!errors.title}
            {...register("title")}
          />
          {errors.title && <p className="text-xs text-[var(--color-danger)]">{errors.title.message}</p>}
          <FieldIssues issues={issuesByField.get("title") ?? []} fieldValue={getValues("title")} />
        </div>

        {/* Goal */}
        <div className="space-y-2">
          <label htmlFor="goal" className="text-sm font-medium text-[var(--color-text-primary)]">
            Goal <span className="text-xs text-[var(--color-text-tertiary)]">(what success looks like)</span>
          </label>
          <Textarea
            id="goal"
            placeholder="Identify top 3 competitor weaknesses we can exploit in messaging."
            rows={2}
            {...register("goal")}
          />
          <FieldIssues issues={issuesByField.get("goal") ?? []} fieldValue={getValues("goal")} />
        </div>

        {/* Target Audience */}
        <div className="space-y-2">
          <label htmlFor="target_audience" className="text-sm font-medium text-[var(--color-text-primary)]">
            Target Audience
          </label>
          <Input
            id="target_audience"
            placeholder="Exec team, Series A investors"
            {...register("target_audience")}
          />
          <FieldIssues issues={issuesByField.get("target_audience") ?? []} fieldValue={getValues("target_audience")} />
        </div>

        {/* Context */}
        <div className="space-y-2">
          <label htmlFor="context" className="text-sm font-medium text-[var(--color-text-primary)]">
            Context <span className="text-xs text-[var(--color-text-tertiary)]">(background, constraints)</span>
          </label>
          <Textarea
            id="context"
            placeholder="Focus on US market, B2B SaaS only."
            rows={3}
            {...register("context")}
          />
          <FieldIssues issues={issuesByField.get("context") ?? []} fieldValue={getValues("context")} />
        </div>

        {/* Description */}
        <div className="space-y-2">
          <label htmlFor="description" className="text-sm font-medium text-[var(--color-text-primary)]">
            Description <span className="text-[var(--color-danger)]">*</span>
            <span className="ml-1 text-xs text-[var(--color-text-tertiary)]">(detailed instructions)</span>
          </label>
          <Textarea
            id="description"
            placeholder="Compare Notion, Coda, Confluence on pricing, collaboration, AI features. Include recommendation matrix."
            rows={6}
            aria-invalid={!!errors.description}
            {...register("description")}
          />
          {errors.description && <p className="text-xs text-[var(--color-danger)]">{errors.description.message}</p>}
          <FieldIssues issues={issuesByField.get("description") ?? []} fieldValue={getValues("description")} />
        </div>

        {/* Budget */}
        <div className="space-y-2">
          <label htmlFor="max_budget_usd" className="text-sm font-medium text-[var(--color-text-primary)]">
            Max Budget (USD)
          </label>
          <Input
            id="max_budget_usd"
            type="number"
            step="0.50"
            min="0.50"
            {...register("max_budget_usd", { valueAsNumber: true })}
          />
        </div>

        {/* Code-only fields */}
        {artifactType === "code" && (
          <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border-primary)] p-4">
            <p className="text-sm font-medium text-[var(--color-text-primary)]">Code Configuration</p>

            {/* Git Connection */}
            <div className="space-y-2">
              <label htmlFor="git_connection_id" className="text-sm font-medium text-[var(--color-text-primary)]">
                Git Connection
              </label>
              <Controller
                name="git_connection_id"
                control={control}
                render={({ field }) => (
                  <select
                    {...field}
                    id="git_connection_id"
                    className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <option value="">Select a connection...</option>
                    {connections.map((conn) => (
                      <option key={conn.id} value={conn.id}>
                        {conn.display_name} ({conn.provider})
                      </option>
                    ))}
                  </select>
                )}
              />
              {connections.length === 0 && (
                <p className="text-xs text-[var(--color-text-tertiary)]">
                  No git connections configured. Add one in Settings.
                </p>
              )}
            </div>

            {/* Repository */}
            {gitConnectionId && repos.length > 0 && (
              <div className="space-y-2">
                <label htmlFor="git_repo_url" className="text-sm font-medium text-[var(--color-text-primary)]">
                  Repository
                </label>
                <Controller
                  name="git_repo_url"
                  control={control}
                  render={({ field }) => (
                    <select
                      {...field}
                      id="git_repo_url"
                      className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      <option value="">Select a repository...</option>
                      {repos.map((repo) => {
                        const fullName = repo.full_name ?? `${repo.owner}/${repo.name}`;
                        return (
                          <option key={fullName} value={fullName}>
                            {fullName}
                          </option>
                        );
                      })}
                    </select>
                  )}
                />
              </div>
            )}

            {/* Base Branch */}
            <div className="space-y-2">
              <label htmlFor="git_base_branch" className="text-sm font-medium text-[var(--color-text-primary)]">
                Base Branch
              </label>
              <Input
                id="git_base_branch"
                placeholder="main"
                {...register("git_base_branch")}
              />
            </div>
          </div>
        )}

        {/* Sufficiency Summary */}
        {sufficiency && (
          <SufficiencySummary isEligible={isEligible} issues={sufficiency.issues} />
        )}

        {/* Actions */}
        <div className="flex items-center gap-3">
          <Button
            type="submit"
            variant="outline"
            disabled={isValidating}
            className="flex-1"
          >
            {isValidating ? (
              <>
                <Loader2 className="animate-spin" />
                Validating...
              </>
            ) : sufficiency ? (
              <>
                <CheckCircle className="h-4 w-4" />
                Re-validate
              </>
            ) : (
              "Validate"
            )}
          </Button>

          <Button
            type="button"
            onClick={handleDelegate}
            disabled={!isEligible || hasCriticalIssues || isDelegating || !artifactId}
            className="flex-1"
          >
            {isDelegating ? (
              <>
                <Loader2 className="animate-spin" />
                Preparing plan...
              </>
            ) : (
              "Delegate to Team"
            )}
          </Button>
        </div>
      </form>

      {/* Delegation Preview Modal */}
      {delegatePlan && (
        <DelegatePreview
          open={showPreview}
          onOpenChange={setShowPreview}
          plan={delegatePlan}
          onConfirm={handleConfirmDelegation}
          isPending={isConfirming}
        />
      )}
    </div>
  );
}
