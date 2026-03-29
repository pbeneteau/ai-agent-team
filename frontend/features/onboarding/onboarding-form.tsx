"use client";

/**
 * Onboarding — code-factory focused company context form.
 *
 * Phase 7 of CODE_FACTORY_UI_OVERHAUL.md
 * Hardcoded use_case="code". Focused on engineering context.
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

const LANGUAGES = [
  "TypeScript", "Python", "Go", "Rust", "Java", "C#", "Ruby", "PHP", "Swift", "Kotlin", "Other",
] as const;

const onboardingSchema = z.object({
  company_name: z.string().min(1, "Company name is required").max(200),
  domain_description: z.string().min(1, "Product description is required").max(2000),
  product_description: z.string().max(2000).optional(),
  tech_stack: z.string().max(500).optional(),
  company_stage: z.enum(["idea", "startup", "growing", "established"]).optional(),
  existing_team: z.string().max(500).optional(),
  team_size: z.number().int().min(1).optional(),
  use_case: z.literal("code"),
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
    formState: { errors },
  } = useForm<OnboardingFormValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: {
      company_name: "",
      domain_description: "",
      product_description: "",
      tech_stack: "",
      use_case: "code",
    },
  });

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
          Company / Project Name <span className="text-[var(--color-danger)]">*</span>
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

      {/* What does your product do? */}
      <div className="space-y-1.5">
        <label htmlFor="domain_description" className="text-sm font-medium text-[var(--color-text-primary)]">
          What does your product do? <span className="text-[var(--color-danger)]">*</span>
        </label>
        <Textarea
          id="domain_description"
          placeholder="B2B project management tool for small engineering teams. REST API + React SPA."
          rows={2}
          aria-invalid={!!errors.domain_description}
          {...register("domain_description")}
        />
        {errors.domain_description && (
          <p className="text-xs text-[var(--color-danger)]">{errors.domain_description.message}</p>
        )}
      </div>

      {/* Tech Stack */}
      <div className="space-y-1.5">
        <label htmlFor="tech_stack" className="text-sm font-medium text-[var(--color-text-primary)]">
          Tech Stack
        </label>
        <Input
          id="tech_stack"
          placeholder="Next.js, FastAPI, PostgreSQL, Redis, Docker"
          {...register("tech_stack")}
        />
        <p className="text-xs text-[var(--color-text-tertiary)]">
          Languages, frameworks, databases, and tools your team uses.
        </p>
      </div>

      {/* Company Stage */}
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-[var(--color-text-primary)]">
          Company Stage
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

      {/* Engineering Team + Size */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label htmlFor="existing_team" className="text-sm font-medium text-[var(--color-text-primary)]">
            Engineering Team
          </label>
          <Input
            id="existing_team"
            placeholder="1 founder, 2 backend, 1 frontend"
            {...register("existing_team")}
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="team_size" className="text-sm font-medium text-[var(--color-text-primary)]">
            Team Size
          </label>
          <Input
            id="team_size"
            type="number"
            min={1}
            placeholder="4"
            {...register("team_size", { valueAsNumber: true })}
          />
        </div>
      </div>

      {/* Context Documents */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-[var(--color-text-primary)]">
            Reference Documents <span className="text-xs text-[var(--color-text-tertiary)]">(optional)</span>
          </label>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-1.5 text-xs text-[var(--color-accent)] hover:underline disabled:opacity-50"
          >
            {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Paperclip className="h-3 w-3" />}
            {uploading ? "Uploading..." : "Attach file"}
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.txt,.md,.json,.yaml,.yml"
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
            Upload architecture docs, API specs, or style guides to give your agents codebase context.
          </p>
        )}
      </div>

      <Button type="submit" className="w-full" size="lg" disabled={isPending || uploading}>
        {isPending ? (
          <>
            <Loader2 className="animate-spin" />
            Building your engineering team...
          </>
        ) : (
          "Build My Team"
        )}
      </Button>
    </form>
  );
}
