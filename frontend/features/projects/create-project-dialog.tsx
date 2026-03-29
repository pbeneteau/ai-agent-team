"use client";

/**
 * Create project dialog.
 *
 * Ref: TDD-05 Section 15.1
 */

import { useForm } from "react-hook-form";
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
import { Loader2 } from "lucide-react";
import { useCreateProject } from "@/lib/hooks/use-projects";

const createProjectSchema = z.object({
  name: z.string().min(1, "Project name is required").max(200),
  description: z.string().max(2000),
});

type CreateProjectValues = z.infer<typeof createProjectSchema>;

interface CreateProjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateProjectDialog({ open, onOpenChange }: CreateProjectDialogProps) {
  const router = useRouter();
  const createProject = useCreateProject();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateProjectValues>({
    resolver: zodResolver(createProjectSchema),
    defaultValues: { name: "", description: "" },
  });

  const onSubmit = (values: CreateProjectValues) => {
    createProject.mutate(
      { name: values.name, description: values.description || undefined },
      {
        onSuccess: (project) => {
          toast.success("Project created");
          reset();
          onOpenChange(false);
          router.push(`/projects/${project.id}`);
        },
        onError: (error) => {
          toast.error(error.message || "Failed to create project");
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New Project</DialogTitle>
          <DialogDescription>Create a new project to organize your deliverables.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="project-name" className="text-sm font-medium">
              Name <span className="text-destructive">*</span>
            </label>
            <Input
              id="project-name"
              placeholder="Q3 Product Launch"
              aria-invalid={!!errors.name}
              {...register("name")}
            />
            {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-2">
            <label htmlFor="project-description" className="text-sm font-medium">
              Description
            </label>
            <Textarea
              id="project-description"
              placeholder="Launch the new enterprise pricing tier."
              rows={3}
              {...register("description")}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={createProject.isPending}>
              {createProject.isPending ? (
                <>
                  <Loader2 className="animate-spin" />
                  Creating...
                </>
              ) : (
                "Create Project"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
