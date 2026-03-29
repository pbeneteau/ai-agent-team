"use client";

/**
 * Smart Brief form — code-factory task creation.
 *
 * Phase 3 of CODE_FACTORY_UI_OVERHAUL.md
 *
 * Flow:
 * 1. Select task type (Feature, Bug Fix, Refactor, etc.)
 * 2. Fill form — fields adapt per type
 * 3. Click Validate → POST /api/artifacts/{id}/validate
 * 4. Click Delegate → preview modal → confirm → execution starts
 */

import { useState, useCallback, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useForm, Controller } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  CheckCircle,
  Sparkles,
  Bug,
  Wrench,
  Shield,
  Zap,
  Server,
  Plug,
  Blocks,
} from "lucide-react";
import { useCreateArtifact, useValidateArtifact, useDelegateArtifact } from "@/lib/hooks/use-artifacts";
import { useGitConnections, useGitRepos } from "@/lib/hooks/use-git-providers";
import { useProjectDetail } from "@/lib/hooks/use-projects";
import { FieldIssues, SufficiencySummary } from "@/features/artifacts/sufficiency-feedback";
import { DelegatePreview } from "@/features/artifacts/delegate-preview";
import type { SufficiencyIssue, SufficiencyResponse, DelegatePlan, DelegatePreviewResponse } from "@/lib/types/api";

// ---------------------------------------------------------------------------
// Task types → DAG template mapping
// ---------------------------------------------------------------------------

const TASK_TYPES = [
  { id: "feature", label: "Feature", icon: Sparkles, template: "full_feature", hint: "PM + Design leads plan, Backend + Frontend workers build, Tech Lead reviews" },
  { id: "bug_fix", label: "Bug Fix", icon: Bug, template: "bug_fix", hint: "Tech Lead diagnoses root cause, Developer fixes, Tech Lead verifies" },
  { id: "refactor", label: "Refactor", icon: Wrench, template: "refactor", hint: "Tech + PM leads plan safe refactor steps, Developer executes, leads verify behavior preserved" },
  { id: "security", label: "Security", icon: Shield, template: "security_fix", hint: "Security + Tech leads analyze threat, Developer patches, both leads verify fix" },
  { id: "performance", label: "Performance", icon: Zap, template: "performance", hint: "Tech Lead profiles bottleneck, Developer optimizes, lead verifies benchmarks" },
  { id: "infra", label: "Infrastructure", icon: Server, template: "infra_devops", hint: "DevOps + Tech leads design, DevOps Engineer implements, both leads review" },
  { id: "api", label: "API Integration", icon: Plug, template: "api_integration", hint: "PM + Tech leads spec the integration, Developer implements client, Tech Lead reviews" },
  { id: "architecture", label: "Architecture", icon: Blocks, template: "architecture", hint: "PM + Tech leads design migration, Developer executes, Tech Lead reviews with highest scrutiny" },
] as const;

type TaskTypeId = (typeof TASK_TYPES)[number]["id"];

// ---------------------------------------------------------------------------
// Form schema
// ---------------------------------------------------------------------------

const briefSchema = z.object({
  artifact_type: z.literal("code"),
  task_type: z.string().min(1, "Select a task type"),
  title: z.string().min(1, "Title is required").max(200),
  goal: z.string().max(1000),
  context: z.string().max(3000),
  description: z.string().min(10, "Description must be at least 10 characters").max(5000),
  // Bug-specific
  severity: z.string(),
  reproduction_steps: z.string().max(2000),
  // Infra-specific
  affected_services: z.string().max(500),
  // Git
  max_budget_usd: z.number().min(0.5),
  git_connection_id: z.string(),
  git_repo_url: z.string(),
  git_base_branch: z.string(),
});

type BriefFormValues = z.infer<typeof briefSchema>;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface SmartBriefFormProps {
  projectId: string;
}

export function SmartBriefForm({ projectId }: SmartBriefFormProps) {
  const router = useRouter();
  const createArtifact = useCreateArtifact();
  const { data: project } = useProjectDetail(projectId);

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
    setValue,
    getValues,
    formState: { errors },
  } = useForm<BriefFormValues>({
    resolver: zodResolver(briefSchema),
    defaultValues: {
      artifact_type: "code",
      task_type: "",
      title: "",
      goal: "",
      context: "",
      description: "",
      severity: "",
      reproduction_steps: "",
      affected_services: "",
      max_budget_usd: 5.0,
      git_connection_id: "",
      git_repo_url: "",
      git_base_branch: "",
    },
  });

  const taskType = watch("task_type") as TaskTypeId;
  const gitConnectionId = watch("git_connection_id");

  const selectedType = TASK_TYPES.find((t) => t.id === taskType);
  const isBugFix = taskType === "bug_fix";
  const isInfra = taskType === "infra";

  // Auto-inherit from project
  useEffect(() => {
    if (!project) return;
    if (project.git_repo_url && !getValues("git_repo_url")) {
      setValue("git_repo_url", project.git_repo_url);
    }
    if (!getValues("context")) {
      const parts: string[] = [];
      if (project.primary_language) parts.push(project.primary_language);
      if (project.framework) parts.push(project.framework);
      if (parts.length > 0) {
        setValue("context", `${parts.join(" + ")} codebase.`);
      }
    }
  }, [project, setValue, getValues]);

  // Git provider data
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

  // Build the full description including type-specific fields
  const buildFullDescription = useCallback((values: BriefFormValues): string => {
    const parts = [values.description];

    if (values.severity) {
      parts.unshift(`[Severity: ${values.severity}]`);
    }
    if (values.reproduction_steps) {
      parts.push(`\n\n## Steps to Reproduce\n${values.reproduction_steps}`);
    }
    if (values.affected_services) {
      parts.push(`\n\n## Affected Services\n${values.affected_services}`);
    }

    return parts.join("\n");
  }, []);

  // Step 1: Create artifact + validate
  const handleValidate = useCallback(
    async (values: BriefFormValues) => {
      setIsValidating(true);
      setSufficiency(null);

      try {
        let id = artifactId;

        if (!id) {
          const artifact = await createArtifact.mutateAsync({
            project_id: projectId,
            artifact_type: "code",
            title: values.title,
            goal: values.goal || undefined,
            context: values.context || undefined,
            description: buildFullDescription(values),
            max_budget_usd: values.max_budget_usd || undefined,
            git_repo_url: values.git_repo_url || undefined,
            git_base_branch: values.git_base_branch || undefined,
          });
          id = artifact.id;
          setArtifactId(id);
        }

        const { api } = await import("@/lib/api");
        const result = await api.artifacts.validate(id);
        setSufficiency(result);

        if (result.is_sufficient) {
          toast.success("Specification is sufficient!");
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Validation failed");
      } finally {
        setIsValidating(false);
      }
    },
    [artifactId, projectId, createArtifact, buildFullDescription],
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
        {/* Task Type Selector */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-[var(--color-text-primary)]">
            Task Type <span className="text-[var(--color-danger)]">*</span>
          </label>
          <Controller
            name="task_type"
            control={control}
            render={({ field }) => (
              <div className="grid grid-cols-4 gap-2">
                {TASK_TYPES.map((type) => {
                  const Icon = type.icon;
                  const isSelected = field.value === type.id;
                  return (
                    <button
                      key={type.id}
                      type="button"
                      onClick={() => field.onChange(type.id)}
                      className={`flex flex-col items-center gap-1.5 rounded-[var(--radius-md)] border px-2 py-3 text-xs font-medium transition-colors ${
                        isSelected
                          ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)] text-[var(--color-accent)]"
                          : "border-[var(--color-border-primary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                      {type.label}
                    </button>
                  );
                })}
              </div>
            )}
          />
          {errors.task_type && <p className="text-xs text-[var(--color-danger)]">{errors.task_type.message}</p>}
        </div>

        {/* Template hint */}
        {selectedType && (
          <p className="text-xs text-[var(--color-text-tertiary)] -mt-3">
            Uses <strong>{selectedType.template.replace(/_/g, " ")}</strong> template — {selectedType.hint}
          </p>
        )}

        {/* Title */}
        <div className="space-y-2">
          <label htmlFor="title" className="text-sm font-medium text-[var(--color-text-primary)]">
            Title <span className="text-[var(--color-danger)]">*</span>
          </label>
          <Input
            id="title"
            placeholder={
              isBugFix
                ? "Login returns 500 when email contains +"
                : isInfra
                  ? "Add Redis caching layer for session store"
                  : "Add user authentication flow"
            }
            aria-invalid={!!errors.title}
            {...register("title")}
          />
          {errors.title && <p className="text-xs text-[var(--color-danger)]">{errors.title.message}</p>}
          <FieldIssues issues={issuesByField.get("title") ?? []} fieldValue={getValues("title")} />
        </div>

        {/* Severity — Bug Fix only */}
        {isBugFix && (
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--color-text-primary)]">Severity</label>
            <Controller
              name="severity"
              control={control}
              render={({ field }) => (
                <div className="flex gap-2">
                  {["critical", "high", "medium", "low"].map((level) => (
                    <button
                      key={level}
                      type="button"
                      onClick={() => field.onChange(level)}
                      className={`flex-1 rounded-[var(--radius-md)] border px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                        field.value === level
                          ? level === "critical"
                            ? "border-red-500 bg-red-500/10 text-red-500"
                            : level === "high"
                              ? "border-orange-500 bg-orange-500/10 text-orange-500"
                              : level === "medium"
                                ? "border-yellow-500 bg-yellow-500/10 text-yellow-500"
                                : "border-blue-500 bg-blue-500/10 text-blue-500"
                          : "border-[var(--color-border-primary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
                      }`}
                    >
                      {level}
                    </button>
                  ))}
                </div>
              )}
            />
          </div>
        )}

        {/* Reproduction Steps — Bug Fix only */}
        {isBugFix && (
          <div className="space-y-2">
            <label htmlFor="reproduction_steps" className="text-sm font-medium text-[var(--color-text-primary)]">
              Steps to Reproduce
            </label>
            <Textarea
              id="reproduction_steps"
              placeholder={"1. Create user with email user+test@example.com\n2. POST /api/auth/login with that email\n3. Observe 500 error in response"}
              rows={3}
              {...register("reproduction_steps")}
            />
          </div>
        )}

        {/* Acceptance Criteria */}
        <div className="space-y-2">
          <label htmlFor="goal" className="text-sm font-medium text-[var(--color-text-primary)]">
            Acceptance Criteria <span className="text-xs text-[var(--color-text-tertiary)]">(when is this done?)</span>
          </label>
          <Textarea
            id="goal"
            placeholder={
              isBugFix
                ? "Login succeeds with emails containing +. No 500 errors. Existing auth tests still pass."
                : "Users can sign up, log in, and refresh tokens. Protected routes return 401 without valid JWT."
            }
            rows={2}
            {...register("goal")}
          />
          <FieldIssues issues={issuesByField.get("goal") ?? []} fieldValue={getValues("goal")} />
        </div>

        {/* Technical Context */}
        <div className="space-y-2">
          <label htmlFor="context" className="text-sm font-medium text-[var(--color-text-primary)]">
            Technical Context <span className="text-xs text-[var(--color-text-tertiary)]">(stack, constraints, existing code)</span>
          </label>
          <Textarea
            id="context"
            placeholder="FastAPI backend, PostgreSQL, existing User model in app/models/user.py."
            rows={3}
            {...register("context")}
          />
          <FieldIssues issues={issuesByField.get("context") ?? []} fieldValue={getValues("context")} />
        </div>

        {/* Affected Services — Infra only */}
        {isInfra && (
          <div className="space-y-2">
            <label htmlFor="affected_services" className="text-sm font-medium text-[var(--color-text-primary)]">
              Affected Services
            </label>
            <Input
              id="affected_services"
              placeholder="backend, worker, redis, postgres"
              {...register("affected_services")}
            />
          </div>
        )}

        {/* Description */}
        <div className="space-y-2">
          <label htmlFor="description" className="text-sm font-medium text-[var(--color-text-primary)]">
            Description <span className="text-[var(--color-danger)]">*</span>
            <span className="ml-1 text-xs text-[var(--color-text-tertiary)]">(detailed instructions)</span>
          </label>
          <Textarea
            id="description"
            placeholder={
              isBugFix
                ? "The email parsing in auth/utils.py doesn't handle + characters. Fix the regex in validate_email() and add test coverage for special characters in emails."
                : "Implement JWT-based authentication with signup, login, and token refresh endpoints. Add auth middleware that protects all /api/v1 routes."
            }
            rows={5}
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

        {/* Git Configuration */}
        <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border-primary)] p-4">
          <p className="text-sm font-medium text-[var(--color-text-primary)]">Git Configuration</p>

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
                  className="h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
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
                    className="h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
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

        {/* Sufficiency Summary */}
        {sufficiency && (
          <SufficiencySummary isEligible={isEligible} issues={sufficiency.issues} />
        )}

        {/* Actions */}
        <div className="flex items-center gap-3">
          <Button
            type="submit"
            variant="outline"
            disabled={isValidating || !taskType}
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
