"use client";

/**
 * Add agent dialog.
 * Ref: TDD-01 J4 Step 7
 */

import { useForm } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Loader2 } from "lucide-react";
import { useCreateAgent } from "@/lib/hooks/use-roster";

const schema = z.object({
  name: z.string().min(1, "Name is required").max(100),
  specialization: z.string().min(1, "Specialization is required").max(200),
  description: z.string().max(1000),
});
type Values = z.infer<typeof schema>;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddAgentDialog({ open, onOpenChange }: Props) {
  const createAgent = useCreateAgent();
  const { register, handleSubmit, reset, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", specialization: "", description: "" },
  });

  const onSubmit = (values: Values) => {
    createAgent.mutate(values, {
      onSuccess: () => { toast.success("Agent created"); reset(); onOpenChange(false); },
      onError: (e) => toast.error(e.message || "Failed to create agent"),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Agent</DialogTitle>
          <DialogDescription>Create a new AI agent for your roster.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="agent-name" className="text-sm font-medium">Name <span className="text-destructive">*</span></label>
            <Input id="agent-name" placeholder="Technical Writer" aria-invalid={!!errors.name} {...register("name")} />
            {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-2">
            <label htmlFor="agent-spec" className="text-sm font-medium">Specialization <span className="text-destructive">*</span></label>
            <Input id="agent-spec" placeholder="Technical Documentation" aria-invalid={!!errors.specialization} {...register("specialization")} />
            {errors.specialization && <p className="text-xs text-destructive">{errors.specialization.message}</p>}
          </div>
          <div className="space-y-2">
            <label htmlFor="agent-desc" className="text-sm font-medium">Description</label>
            <Textarea id="agent-desc" placeholder="Describe this agent's role..." rows={3} {...register("description")} />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={createAgent.isPending}>
              {createAgent.isPending ? <><Loader2 className="animate-spin" />Creating...</> : "Create Agent"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
