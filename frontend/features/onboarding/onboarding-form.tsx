"use client";

/**
 * Onboarding Step 1 — Company context form.
 *
 * Ref: TDD-05 Section 13.1, TDD-01 Journey J1 Steps 1-3
 */

import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Paperclip, X, FileText } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { WorkspaceDocument } from "@/lib/types/api";

const STAGE_OPTIONS = [
  { value: "idea", label: "Idea / Pre-seed" },
  { value: "startup", label: "Early Startup" },
  { value: "growing", label: "Growing" },
  { value: "established", label: "Established" },
] as const;

const USE_CASE_OPTIONS = [
  { value: "content", label: "Content" },
  { value: "code", label: "Code" },
  { value: "both", label: "Both" },
] as const;

const onboardingSchema = z.object({
  company_name: z.string().min(1, "Company name is required").max(200),
  domain_description: z.string().min(1, "Domain description is required").max(2000),
  product_description: z.string().max(2000).optional(),
  tech_stack: z.string().max(500).optional(),
  company_stage: z.enum(["idea", "startup", "growing", "established"]).optional(),
  target_audience: z.string().max(1000).optional(),
  main_goals: z.string().max(2000).optional(),
  existing_team: z.string().max(500).optional(),
  team_size: z.number().int().min(1).optional(),
  use_case: z.enum(["code", "content", "both"]),
});

export type OnboardingFormValues = z.infer<typeof onboardingSchema>;

interface OnboardingFormProps {
  onSubmit: (values: OnboardingFormValues) => void;
  isPending: boolean;
}

export function OnboardingForm({ onSubmit, isPending }: OnboardingFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<OnboardingFormValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: {
      company_name: "",
      domain_description: "",
      product_description: "",
      tech_stack: "",
      use_case: "both",
    },
  });

  const selectedUseCase = watch("use_case");
  const selectedStage = watch("company_stage");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<WorkspaceDocument[]>([]);
  const [uploading, setUploading] = useState(false);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const doc = await api.workspace.uploadDocument(formData);
      setDocuments((prev) => [...prev, doc]);
    } catch {
      toast.error("Failed to upload document");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleRemoveDoc = async (docId: string) => {
    try {
      await api.workspace.deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch {
      toast.error("Failed to remove document");
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">

      {/* Company Name */}
      <div className="space-y-1.5">
        <label htmlFor="company_name" className="text-sm font-medium text-[var(--color-text-primary)]">
          Company Name <span className="text-[var(--color-danger)]">*</span>
        </label>
        <Input
          id="company_name"
          placeholder="Acme SaaS"
          aria-invalid={!!errors.company_name}
          {...register("company_name")}
        />
        {errors.company_name && (
          <p className="text-xs text-[var(--color-danger)]">{errors.company_name.message}</p>
        )}
      </div>

      {/* Domain / Industry */}
      <div className="space-y-1.5">
        <label htmlFor="domain_description" className="text-sm font-medium text-[var(--color-text-primary)]">
          Domain / Industry <span className="text-[var(--color-danger)]">*</span>
        </label>
        <Textarea
          id="domain_description"
          placeholder="B2B project management tool for small engineering teams"
          rows={2}
          aria-invalid={!!errors.domain_description}
          {...register("domain_description")}
        />
        {errors.domain_description && (
          <p className="text-xs text-[var(--color-danger)]">{errors.domain_description.message}</p>
        )}
      </div>

      {/* Product Description */}
      <div className="space-y-1.5">
        <label htmlFor="product_description" className="text-sm font-medium text-[var(--color-text-primary)]">
          Product Description <span className="text-xs text-[var(--color-text-tertiary)]">(optional)</span>
        </label>
        <Textarea
          id="product_description"
          placeholder="What does your product do? What problem does it solve?"
          rows={2}
          {...register("product_description")}
        />
      </div>

      {/* Company Stage */}
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-[var(--color-text-primary)]">
          Company Stage <span className="text-xs text-[var(--color-text-tertiary)]">(optional)</span>
        </label>
        <div className="grid grid-cols-4 gap-2">
          {STAGE_OPTIONS.map(({ value, label }) => (
            <label
              key={value}
              className={`cursor-pointer rounded-[var(--radius-md)] border px-3 py-2 text-center text-xs font-medium transition-colors ${
                selectedStage === value
                  ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)] text-[var(--color-accent)]"
                  : "border-[var(--color-border-primary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
              }`}
            >
              <input
                type="radio"
                value={value}
                className="sr-only"
                {...register("company_stage")}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      {/* Target Audience */}
      <div className="space-y-1.5">
        <label htmlFor="target_audience" className="text-sm font-medium text-[var(--color-text-primary)]">
          Target Audience <span className="text-xs text-[var(--color-text-tertiary)]">(optional)</span>
        </label>
        <Input
          id="target_audience"
          placeholder="Small B2B SaaS companies, 10–200 employees"
          {...register("target_audience")}
        />
      </div>

      {/* Main Goals */}
      <div className="space-y-1.5">
        <label htmlFor="main_goals" className="text-sm font-medium text-[var(--color-text-primary)]">
          Main Goals <span className="text-xs text-[var(--color-text-tertiary)]">(optional)</span>
        </label>
        <Textarea
          id="main_goals"
          placeholder="What do you want to accomplish? e.g. ship faster, improve docs quality, reduce technical debt"
          rows={2}
          {...register("main_goals")}
        />
      </div>

      {/* Existing Team */}
      <div className="space-y-1.5">
        <label htmlFor="existing_team" className="text-sm font-medium text-[var(--color-text-primary)]">
          Existing Team Roles <span className="text-xs text-[var(--color-text-tertiary)]">(optional)</span>
        </label>
        <Input
          id="existing_team"
          placeholder="1 founder, 2 engineers — no designers or marketers yet"
          {...register("existing_team")}
        />
      </div>

      {/* Tech Stack + Team Size */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label htmlFor="tech_stack" className="text-sm font-medium text-[var(--color-text-primary)]">
            Tech Stack <span className="text-xs text-[var(--color-text-tertiary)]">(optional)</span>
          </label>
          <Input
            id="tech_stack"
            placeholder="Next.js, FastAPI, PostgreSQL"
            {...register("tech_stack")}
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="team_size" className="text-sm font-medium text-[var(--color-text-primary)]">
            Team Size <span className="text-xs text-[var(--color-text-tertiary)]">(optional)</span>
          </label>
          <Input
            id="team_size"
            type="number"
            min={1}
            placeholder="3"
            {...register("team_size", { valueAsNumber: true })}
          />
        </div>
      </div>

      {/* Primary Use Case */}
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-[var(--color-text-primary)]">
          Primary Use Case <span className="text-[var(--color-danger)]">*</span>
        </label>
        <div className="flex gap-2">
          {USE_CASE_OPTIONS.map(({ value, label }) => (
            <label
              key={value}
              className={`flex-1 cursor-pointer rounded-[var(--radius-md)] border px-4 py-2.5 text-center text-sm font-medium transition-colors ${
                selectedUseCase === value
                  ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)] text-[var(--color-accent)]"
                  : "border-[var(--color-border-primary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
              }`}
            >
              <input
                type="radio"
                value={value}
                className="sr-only"
                {...register("use_case")}
              />
              {label}
            </label>
          ))}
        </div>
        {errors.use_case && (
          <p className="text-xs text-[var(--color-danger)]">{errors.use_case.message}</p>
        )}
      </div>

      {/* Context Documents */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-[var(--color-text-primary)]">
            Context Documents <span className="text-xs text-[var(--color-text-tertiary)]">(optional)</span>
          </label>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-1.5 text-xs text-[var(--color-accent)] hover:underline disabled:opacity-50"
          >
            {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Paperclip className="h-3 w-3" />}
            {uploading ? "Uploading…" : "Attach file"}
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.txt,.md"
          onChange={handleFileChange}
        />
        {documents.length > 0 ? (
          <ul className="space-y-1.5">
            {documents.map((doc) => (
              <li
                key={doc.id}
                className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--color-border-primary)] bg-[var(--color-bg-secondary)] px-3 py-2"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-tertiary)]" />
                  <span className="truncate text-xs text-[var(--color-text-secondary)]">{doc.filename}</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleRemoveDoc(doc.id)}
                  className="ml-2 shrink-0 text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)]"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-[var(--color-text-tertiary)]">
            Upload PDFs, Word docs, or text files to give your agents extra context about your business.
          </p>
        )}
      </div>

      <Button type="submit" className="w-full" size="lg" disabled={isPending || uploading}>
        {isPending ? (
          <>
            <Loader2 className="animate-spin" />
            Generating your agency…
          </>
        ) : (
          "Generate My Agency"
        )}
      </Button>
    </form>
  );
}
