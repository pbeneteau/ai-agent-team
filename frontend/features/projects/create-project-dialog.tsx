"use client";

/**
 * Add repository dialog — repo-first project creation.
 *
 * Flow: pick git connection → pick repo → backend fetches README as context → create.
 * If no README found, user is asked for a description.
 */

import { useEffect } from "react";
import { useForm, Controller } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, GitBranch, AlertCircle } from "lucide-react";
import { useCreateProject } from "@/lib/hooks/use-projects";
import { useGitConnections, useGitRepos } from "@/lib/hooks/use-git-providers";

const createSchema = z.object({
  git_connection_id: z.string().min(1, "Select a git connection"),
  git_repo_url: z.string().min(1, "Select a repository"),
  name: z.string().min(1, "Name is required").max(200),
  description: z.string().max(2000),
});

type CreateValues = z.infer<typeof createSchema>;

interface CreateProjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateProjectDialog({ open, onOpenChange }: CreateProjectDialogProps) {
  const router = useRouter();
  const createProject = useCreateProject();
  const { data: gitConnections } = useGitConnections();

  const connections = gitConnections?.items ?? [];

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    control,
    formState: { errors },
  } = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      git_connection_id: "",
      git_repo_url: "",
      name: "",
      description: "",
    },
  });

  const gitConnectionId = watch("git_connection_id");
  const selectedRepo = watch("git_repo_url");

  const { data: gitRepos } = useGitRepos(gitConnectionId);
  const repos = gitRepos?.items ?? [];

  // Auto-fill name from repo selection
  useEffect(() => {
    if (selectedRepo) {
      const repoName = selectedRepo.split("/").pop() ?? selectedRepo;
      setValue("name", repoName);
    }
  }, [selectedRepo, setValue]);

  const onSubmit = (values: CreateValues) => {
    createProject.mutate(
      {
        name: values.name,
        description: values.description || undefined,
        git_repo_url: values.git_repo_url,
        git_connection_id: values.git_connection_id,
      },
      {
        onSuccess: (project) => {
          toast.success(`Repository ${values.git_repo_url} added`);
          reset();
          onOpenChange(false);
          router.push(`/projects/${project.id}`);
        },
        onError: (error) => {
          toast.error(error.message || "Failed to add repository");
        },
      },
    );
  };

  const hasConnections = connections.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitBranch className="h-5 w-5" />
            Add Repository
          </DialogTitle>
          <DialogDescription>
            Select a repository. The README will be analyzed as engineering context for your AI team.
          </DialogDescription>
        </DialogHeader>

        {!hasConnections ? (
          <div className="flex flex-col items-center gap-3 py-8">
            <AlertCircle className="h-8 w-8 text-[var(--color-text-tertiary)]" />
            <p className="text-sm text-[var(--color-text-secondary)] text-center">
              No git connections configured yet.
            </p>
            <Button
              variant="outline"
              onClick={() => {
                onOpenChange(false);
                router.push("/settings/git");
              }}
            >
              Connect Git Provider
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {/* Git Connection */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Git Connection</label>
              <Controller
                name="git_connection_id"
                control={control}
                render={({ field }) => (
                  <select
                    {...field}
                    className="h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <option value="">Select connection...</option>
                    {connections.map((conn) => (
                      <option key={conn.id} value={conn.id}>
                        {conn.display_name} ({conn.provider})
                      </option>
                    ))}
                  </select>
                )}
              />
            </div>

            {/* Repository */}
            {gitConnectionId && repos.length > 0 && (
              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Repository <span className="text-destructive">*</span>
                </label>
                <Controller
                  name="git_repo_url"
                  control={control}
                  render={({ field }) => (
                    <select
                      {...field}
                      className="h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      <option value="">Select repository...</option>
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
                {errors.git_repo_url && (
                  <p className="text-xs text-destructive">{errors.git_repo_url.message}</p>
                )}
              </div>
            )}

            {gitConnectionId && repos.length === 0 && (
              <p className="text-xs text-[var(--color-text-tertiary)]">
                No repositories found. Check your PAT permissions (needs Contents read access).
              </p>
            )}

            {/* Display name (auto-filled, editable) */}
            {selectedRepo && (
              <>
                <div className="space-y-2">
                  <label htmlFor="project-name" className="text-sm font-medium">
                    Display Name
                  </label>
                  <Input
                    id="project-name"
                    aria-invalid={!!errors.name}
                    {...register("name")}
                  />
                  {errors.name && (
                    <p className="text-xs text-destructive">{errors.name.message}</p>
                  )}
                </div>

                {/* Description — fallback if repo has no README */}
                <div className="space-y-2">
                  <label htmlFor="project-desc" className="text-sm font-medium">
                    Description <span className="text-xs text-muted-foreground">(used if no README found in repo)</span>
                  </label>
                  <Textarea
                    id="project-desc"
                    placeholder="Brief description of this repository's purpose and tech stack."
                    rows={2}
                    {...register("description")}
                  />
                </div>

                <p className="text-xs text-[var(--color-text-tertiary)]">
                  The repo's README will be fetched and used as engineering context for your AI team.
                  If no README is found, the description above will be used instead.
                </p>
              </>
            )}

            <DialogFooter>
              <Button type="submit" disabled={createProject.isPending || !selectedRepo}>
                {createProject.isPending ? (
                  <>
                    <Loader2 className="animate-spin" />
                    Adding...
                  </>
                ) : (
                  "Add Repository"
                )}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
