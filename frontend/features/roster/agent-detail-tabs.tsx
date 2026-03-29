"use client";

/**
 * Agent detail page tabs: Profile, Skills, Knowledge.
 * Ref: TDD-05 Section 14.2
 */

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Loader2, Save, Search, Trash2, AlertTriangle, Brain, BookOpen, CheckCircle, X } from "lucide-react";
import {
  useAgentSkills, useLearningProfile, useUpdateAgent, useArchiveAgent,
  useDeleteAgent, useTriggerReflection, useAgentRecommendations,
} from "@/lib/hooks/use-roster";
import { api } from "@/lib/api";
import { ResearchDialog } from "./research-dialog";
import type { AgentDetail, SkillItem, ReadinessComponent } from "@/lib/types/api";

// ── Profile Tab ──────────────────────────────────────────────────────
function ProfileTab({ agent }: { agent: AgentDetail }) {
  const router = useRouter();
  const updateAgent = useUpdateAgent(agent.id);
  const archiveAgent = useArchiveAgent();
  const deleteAgent = useDeleteAgent();
  const triggerReflection = useTriggerReflection(agent.id);

  const [name, setName] = useState(agent.name ?? "");
  const [specialization, setSpecialization] = useState(agent.specialization ?? "");
  const [description, setDescription] = useState(agent.description ?? "");
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deleteConfirmName, setDeleteConfirmName] = useState("");

  const handleSave = useCallback(() => {
    updateAgent.mutate(
      { name, specialization, description },
      {
        onSuccess: () => toast.success("Agent updated"),
        onError: (e) => toast.error(e.message || "Failed to update"),
      },
    );
  }, [name, specialization, description, updateAgent]);

  const handleArchive = useCallback(() => {
    archiveAgent.mutate(agent.id, {
      onSuccess: () => { toast.success("Agent archived"); router.push("/roster"); },
      onError: (e) => toast.error(e.message || "Failed to archive"),
    });
  }, [agent.id, archiveAgent, router]);

  const handleDelete = useCallback(() => {
    if (deleteConfirmName !== agent.name) return;
    deleteAgent.mutate(agent.id, {
      onSuccess: () => { toast.success("Agent permanently deleted"); setShowDeleteDialog(false); router.push("/roster"); },
      onError: (e) => toast.error(e.message || "Failed to delete"),
    });
  }, [agent.id, agent.name, deleteConfirmName, deleteAgent, router]);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <label htmlFor="agent-name" className="text-sm font-medium text-[var(--color-text-primary)]">Name</label>
          <Input id="agent-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-2">
          <label htmlFor="agent-spec" className="text-sm font-medium text-[var(--color-text-primary)]">Specialization</label>
          <Input id="agent-spec" value={specialization} onChange={(e) => setSpecialization(e.target.value)} />
        </div>
      </div>
      <div className="space-y-2">
        <label htmlFor="agent-desc" className="text-sm font-medium text-[var(--color-text-primary)]">Description</label>
        <Textarea id="agent-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--color-text-secondary)]">
        <span>Model: <strong className="text-[var(--color-text-primary)]">{agent.model_tier}</strong></span>
        <span>&middot;</span>
        <span>Status: <strong className="text-[var(--color-text-primary)]">{agent.status}</strong></span>
        <span>&middot;</span>
        <span>Level: <strong className="text-[var(--color-text-primary)]">{agent.progression_level}</strong></span>
        <span>&middot;</span>
        <span>
          Role:{" "}
          <strong
            className={agent.role === "lead" ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}
          >
            {agent.role === "lead" ? "Lead" : "Worker"}
          </strong>
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button onClick={handleSave} disabled={updateAgent.isPending}>
          {updateAgent.isPending ? <Loader2 className="animate-spin" /> : <Save className="h-4 w-4" />}
          Save Changes
        </Button>
        <Button variant="outline" onClick={() => triggerReflection.mutate(undefined, {
          onSuccess: () => toast.success("Reflection started"),
          onError: (e) => toast.error(e.message || "Failed"),
        })} disabled={triggerReflection.isPending}>
          <Brain className="h-4 w-4" /> Reflect
        </Button>
      </div>

      <Separator />

      {/* Danger zone */}
      <div className="space-y-3 rounded-[var(--radius-lg)] border border-[var(--color-danger)] p-4">
        <h3 className="text-sm font-medium text-[var(--color-danger)]">Danger Zone</h3>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={handleArchive} disabled={archiveAgent.isPending}>
            Archive Agent
          </Button>
          <Button variant="destructive" onClick={() => setShowDeleteDialog(true)}>
            <Trash2 className="h-4 w-4" /> Delete Permanently
          </Button>
        </div>
      </div>

      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-[var(--color-danger)]" />
              Delete Agent Permanently
            </DialogTitle>
            <DialogDescription>
              This will permanently remove <strong>{agent.name}</strong> and all associated data. Type the agent name to confirm.
            </DialogDescription>
          </DialogHeader>
          <Input
            value={deleteConfirmName}
            onChange={(e) => setDeleteConfirmName(e.target.value)}
            placeholder={agent.name}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteConfirmName !== agent.name || deleteAgent.isPending}
            >
              {deleteAgent.isPending ? <Loader2 className="animate-spin" /> : "Delete Forever"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Skills Tab ───────────────────────────────────────────────────────
function SkillsTab({ agentId }: { agentId: string }) {
  const [category, setCategory] = useState<string | undefined>();
  const { data, isLoading } = useAgentSkills(agentId, category);

  const categories = [
    { value: undefined, label: "All" },
    { value: "skill", label: "Skills" },
    { value: "work_learning", label: "Learnings" },
    { value: "briefing", label: "Briefings" },
  ] as const;

  if (isLoading) return <div className="space-y-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>;

  const items = data?.items ?? [];
  const totalTokens = data?.total_tokens ?? 0;
  const budgetLimit = data?.budget_limit ?? 8000;
  const usagePct = Math.round((totalTokens / budgetLimit) * 100);

  return (
    <div className="space-y-4">
      {/* Token budget */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-[var(--color-text-secondary)]">Token Budget</span>
          <span className="tabular-nums text-[var(--color-text-primary)]">{totalTokens.toLocaleString()} / {budgetLimit.toLocaleString()}</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-bg-tertiary)]">
          <div
            className={`h-full rounded-full transition-all ${usagePct > 90 ? "bg-[var(--color-danger)]" : usagePct > 70 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]"}`}
            style={{ width: `${Math.min(usagePct, 100)}%` }}
          />
        </div>
      </div>

      {/* Category filter */}
      <div className="flex gap-1">
        {categories.map((c) => (
          <Button
            key={c.label}
            variant={category === c.value ? "default" : "ghost"}
            size="xs"
            onClick={() => setCategory(c.value)}
          >
            {c.label}
          </Button>
        ))}
      </div>

      {/* Skills list */}
      {items.length === 0 ? (
        <p className="py-8 text-center text-sm text-[var(--color-text-tertiary)]">No skills in this category.</p>
      ) : (
        <div className="divide-y divide-[var(--color-border-primary)] rounded-[var(--radius-lg)] border border-[var(--color-border-primary)]">
          {items.map((skill) => (
            <div key={skill.id} className="px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[var(--color-text-primary)]">{skill.title}</p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-[var(--color-text-secondary)]">{skill.content}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge variant="outline" className="text-[10px]">{skill.category.replace("_", " ")}</Badge>
                  <span className="text-[10px] tabular-nums text-[var(--color-text-tertiary)]">{skill.token_count}t</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Knowledge Tab ────────────────────────────────────────────────────
function KnowledgeTab({ agent }: { agent: AgentDetail }) {
  const { data: profile, isLoading: profileLoading } = useLearningProfile(agent.id);
  const { data: recsData } = useAgentRecommendations(agent.id);
  const [showResearch, setShowResearch] = useState(false);

  const recommendations = (recsData?.items ?? []) as Array<{ id: string; topic: string; reason: string }>;

  return (
    <div className="space-y-6">
      {/* Readiness breakdown */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Readiness Breakdown</h3>
        {profileLoading ? (
          <div className="space-y-2">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
        ) : (
          <div className="space-y-2">
            {(profile?.breakdown ?? []).map((component) => (
              <div key={component.name} className="flex items-center gap-3">
                {component.met ? (
                  <CheckCircle className="h-4 w-4 shrink-0 text-[var(--color-success)]" />
                ) : (
                  <X className="h-4 w-4 shrink-0 text-[var(--color-text-tertiary)]" />
                )}
                <span className="flex-1 text-sm text-[var(--color-text-primary)]">{component.name}</span>
                <span className="text-xs tabular-nums text-[var(--color-text-secondary)]">
                  {component.score}/{component.max_score}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <Separator />

      {/* Recommendations */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">
          Knowledge Recommendations ({recommendations.length})
        </h3>
        {recommendations.length === 0 ? (
          <p className="text-sm text-[var(--color-text-tertiary)]">No recommendations at this time.</p>
        ) : (
          <div className="space-y-2">
            {recommendations.map((rec) => (
              <div key={rec.id} className="flex items-start gap-3 rounded-[var(--radius-md)] border border-[var(--color-border-primary)] p-3">
                <BookOpen className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-accent)]" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[var(--color-text-primary)]">{rec.topic}</p>
                  <p className="text-xs text-[var(--color-text-secondary)]">{rec.reason}</p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    size="xs"
                    onClick={() => api.roster.applyRecommendation(agent.id, rec.id).then(() => toast.success("Research started"))}
                  >
                    Apply
                  </Button>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => api.roster.dismissRecommendation(agent.id, rec.id).then(() => toast.success("Dismissed"))}
                  >
                    Dismiss
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Separator />

      <Button variant="outline" onClick={() => setShowResearch(true)}>
        <Search className="h-4 w-4" /> Research a Topic
      </Button>
      <ResearchDialog agentId={agent.id} agentName={agent.name} open={showResearch} onOpenChange={setShowResearch} />
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────
interface AgentDetailTabsProps {
  agent: AgentDetail;
}

export function AgentDetailTabs({ agent }: AgentDetailTabsProps) {
  return (
    <Tabs defaultValue="profile">
      <TabsList variant="line">
        <TabsTrigger value="profile">Profile</TabsTrigger>
        <TabsTrigger value="skills">Skills</TabsTrigger>
        <TabsTrigger value="knowledge">Knowledge</TabsTrigger>
      </TabsList>
      <TabsContent value="profile" className="pt-4">
        <ProfileTab agent={agent} />
      </TabsContent>
      <TabsContent value="skills" className="pt-4">
        <SkillsTab agentId={agent.id} />
      </TabsContent>
      <TabsContent value="knowledge" className="pt-4">
        <KnowledgeTab agent={agent} />
      </TabsContent>
    </Tabs>
  );
}
