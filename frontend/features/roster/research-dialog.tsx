"use client";

/**
 * Research dialog — trigger manual research for an agent.
 * Ref: TDD-01 J4 Step 6
 */

import { useState, useCallback } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";
import { useTriggerResearch } from "@/lib/hooks/use-roster";

interface Props {
  agentId: string;
  agentName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ResearchDialog({ agentId, agentName, open, onOpenChange }: Props) {
  const [topic, setTopic] = useState("");
  const triggerResearch = useTriggerResearch(agentId);

  const handleSubmit = useCallback(() => {
    if (!topic.trim()) return;
    triggerResearch.mutate(topic.trim(), {
      onSuccess: () => {
        toast.success(`${agentName} is now researching "${topic}"`);
        setTopic("");
        onOpenChange(false);
      },
      onError: (e) => toast.error(e.message || "Failed to trigger research"),
    });
  }, [topic, agentName, triggerResearch, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Research a Topic</DialogTitle>
          <DialogDescription>{agentName} will research this topic autonomously.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <label htmlFor="research-topic" className="text-sm font-medium">Topic</label>
          <Input
            id="research-topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="WCAG 2.2 accessibility guidelines"
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={!topic.trim() || triggerResearch.isPending}>
            {triggerResearch.isPending ? <><Loader2 className="animate-spin" />Starting...</> : "Start Research"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
