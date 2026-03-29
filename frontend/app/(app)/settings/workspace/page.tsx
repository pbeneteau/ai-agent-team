"use client";

/**
 * Workspace settings page — edit company context and manage context documents.
 */

import { useRef, useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Loader2, Paperclip, X, FileText, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { Workspace, WorkspaceDocument } from "@/lib/types/api";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

const STAGE_OPTIONS = [
  { value: "idea", label: "Idea / Pre-seed" },
  { value: "startup", label: "Early Startup" },
  { value: "growing", label: "Growing" },
  { value: "established", label: "Established" },
] as const;

const schema = z.object({
  name: z.string().min(1, "Company name is required").max(200),
  domain_description: z.string().max(2000).optional(),
  product_description: z.string().max(2000).optional(),
  tech_stack: z.string().max(500).optional(),
  company_stage: z.enum(["idea", "startup", "growing", "established"]).optional(),
  target_audience: z.string().max(1000).optional(),
  main_goals: z.string().max(2000).optional(),
  existing_team: z.string().max(500).optional(),
});
type FormValues = z.infer<typeof schema>;

export default function WorkspaceSettingsPage() {
  const queryClient = useQueryClient();

  const { data: workspace, isLoading: workspaceLoading } = useQuery({
    queryKey: ["workspace"],
    queryFn: () => api.workspace.get(),
  });

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ["workspace", "documents"],
    queryFn: () => api.workspace.listDocuments(),
  });

  const updateMutation = useMutation({
    mutationFn: (data: FormValues) => api.workspace.update(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace"] });
      toast.success("Workspace settings saved");
    },
    onError: () => toast.error("Failed to save settings"),
  });

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => api.workspace.deleteDocument(docId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspace", "documents"] }),
    onError: () => toast.error("Failed to remove document"),
  });

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      domain_description: "",
      product_description: "",
      tech_stack: "",
      target_audience: "",
      main_goals: "",
      existing_team: "",
    },
  });

  useEffect(() => {
    if (workspace) {
      reset({
        name: workspace.name ?? "",
        domain_description: workspace.domain_description ?? "",
        product_description: workspace.product_description ?? "",
        tech_stack: workspace.tech_stack ?? "",
        company_stage: workspace.company_stage ?? undefined,
        target_audience: workspace.target_audience ?? "",
        main_goals: workspace.main_goals ?? "",
        existing_team: workspace.existing_team ?? "",
      });
    }
  }, [workspace, reset]);

  const selectedStage = watch("company_stage");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      await api.workspace.uploadDocument(formData);
      queryClient.invalidateQueries({ queryKey: ["workspace", "documents"] });
      toast.success("Document uploaded");
    } catch {
      toast.error("Failed to upload document");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  if (workspaceLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Company Context */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Company Context</CardTitle>
          <CardDescription>
            This information is used to tailor your AI agents. More detail = better results.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit((v) => updateMutation.mutate(v))} className="space-y-4">

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--color-text-primary)]">
                Company Name <span className="text-[var(--color-danger)]">*</span>
              </label>
              <Input placeholder="Acme SaaS" aria-invalid={!!errors.name} {...register("name")} />
              {errors.name && <p className="text-xs text-[var(--color-danger)]">{errors.name.message}</p>}
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--color-text-primary)]">Domain / Industry</label>
              <Textarea
                placeholder="B2B project management tool for small engineering teams"
                rows={2}
                {...register("domain_description")}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--color-text-primary)]">Product Description</label>
              <Textarea
                placeholder="What does your product do? What problem does it solve?"
                rows={2}
                {...register("product_description")}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--color-text-primary)]">Company Stage</label>
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
                    <input type="radio" value={value} className="sr-only" {...register("company_stage")} />
                    {label}
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--color-text-primary)]">Target Audience</label>
              <Input
                placeholder="Small B2B SaaS companies, 10–200 employees"
                {...register("target_audience")}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--color-text-primary)]">Main Goals</label>
              <Textarea
                placeholder="What do you want to accomplish? e.g. ship faster, improve docs quality"
                rows={2}
                {...register("main_goals")}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--color-text-primary)]">Existing Team Roles</label>
                <Input
                  placeholder="1 founder, 2 engineers"
                  {...register("existing_team")}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-[var(--color-text-primary)]">Tech Stack</label>
                <Input placeholder="Next.js, FastAPI, PostgreSQL" {...register("tech_stack")} />
              </div>
            </div>

            <div className="flex justify-end pt-1">
              <Button type="submit" size="sm" disabled={updateMutation.isPending || !isDirty}>
                {updateMutation.isPending ? (
                  <><Loader2 className="animate-spin" /> Saving…</>
                ) : (
                  <><Save className="h-3.5 w-3.5" /> Save Changes</>
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Context Documents */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Context Documents</CardTitle>
          <CardDescription>
            PDFs, Word docs, or text files your agents can reference across all projects.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.docx,.txt,.md"
            onChange={handleFileChange}
          />

          {docsLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          ) : docsData?.items && docsData.items.length > 0 ? (
            <ul className="space-y-1.5">
              {docsData.items.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--color-border-primary)] bg-[var(--color-bg-secondary)] px-3 py-2"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-tertiary)]" />
                    <span className="truncate text-sm text-[var(--color-text-secondary)]">{doc.filename}</span>
                    <span className="shrink-0 text-xs text-[var(--color-text-tertiary)]">
                      {(doc.size_bytes / 1024).toFixed(0)} KB
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => deleteMutation.mutate(doc.id)}
                    className="ml-2 shrink-0 text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)]"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-[var(--color-text-tertiary)]">No documents uploaded yet.</p>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? (
              <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Uploading…</>
            ) : (
              <><Paperclip className="h-3.5 w-3.5" /> Attach Document</>
            )}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
