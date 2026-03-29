"use client";

/**
 * Onboarding Step 2 — Generated roster preview with inline editing.
 *
 * Ref: TDD-05 Section 13.1, TDD-01 Journey J1 Steps 4-6
 */

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Pencil, Trash2, Plus, Check, X, Loader2 } from "lucide-react";
import type { AgentListItem } from "@/lib/types/api";

interface EditableAgent {
  id: string;
  name: string;
  specialization: string;
  description: string;
  isNew?: boolean;
}

interface RosterPreviewProps {
  agents: AgentListItem[];
  onConfirm: (edits: Map<string, Partial<EditableAgent>>, removedIds: Set<string>, newAgents: EditableAgent[]) => void;
  isPending: boolean;
}

export function RosterPreview({ agents, onConfirm, isPending }: RosterPreviewProps) {
  const [editableAgents, setEditableAgents] = useState<EditableAgent[]>(
    agents.map((a) => ({
      id: a.id,
      name: a.name,
      specialization: a.specialization,
      description: a.description,
    })),
  );
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState({ name: "", specialization: "", description: "" });
  const [removedIds, setRemovedIds] = useState<Set<string>>(new Set());
  const [showAddForm, setShowAddForm] = useState(false);
  const [newAgent, setNewAgent] = useState({ name: "", specialization: "", description: "" });

  const startEdit = useCallback((agent: EditableAgent) => {
    setEditingId(agent.id);
    setEditDraft({ name: agent.name, specialization: agent.specialization, description: agent.description });
  }, []);

  const saveEdit = useCallback(() => {
    if (!editingId) return;
    setEditableAgents((prev) =>
      prev.map((a) =>
        a.id === editingId
          ? { ...a, name: editDraft.name, specialization: editDraft.specialization, description: editDraft.description }
          : a,
      ),
    );
    setEditingId(null);
  }, [editingId, editDraft]);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
  }, []);

  const removeAgent = useCallback((id: string) => {
    setEditableAgents((prev) => prev.filter((a) => a.id !== id));
    setRemovedIds((prev) => new Set(prev).add(id));
  }, []);

  const addAgent = useCallback(() => {
    if (!newAgent.name || !newAgent.specialization) return;
    const tempId = `new-${Date.now()}`;
    setEditableAgents((prev) => [
      ...prev,
      { id: tempId, ...newAgent, isNew: true },
    ]);
    setNewAgent({ name: "", specialization: "", description: "" });
    setShowAddForm(false);
  }, [newAgent]);

  const handleConfirm = useCallback(() => {
    const edits = new Map<string, Partial<EditableAgent>>();
    const newAgents: EditableAgent[] = [];

    for (const agent of editableAgents) {
      if (agent.isNew) {
        newAgents.push(agent);
        continue;
      }
      const original = agents.find((a) => a.id === agent.id);
      if (!original) continue;
      const changes: Partial<EditableAgent> = {};
      if (agent.name !== original.name) changes.name = agent.name;
      if (agent.specialization !== original.specialization) changes.specialization = agent.specialization;
      if (agent.description !== original.description) changes.description = agent.description;
      if (Object.keys(changes).length > 0) edits.set(agent.id, changes);
    }

    onConfirm(edits, removedIds, newAgents);
  }, [editableAgents, agents, removedIds, onConfirm]);

  const visibleAgents = editableAgents.filter((a) => !removedIds.has(a.id));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Your Engineering Team</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">
            {visibleAgents.length} agents generated. Rename, adjust, add, or remove as needed.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setShowAddForm(true)} disabled={showAddForm}>
          <Plus className="h-3.5 w-3.5" />
          Add Agent
        </Button>
      </div>

      {showAddForm && (
        <Card className="border-dashed border-[var(--color-accent)]">
          <CardContent className="space-y-3">
            <p className="text-sm font-medium text-[var(--color-text-primary)]">New Agent</p>
            <Input
              placeholder="Agent name"
              value={newAgent.name}
              onChange={(e) => setNewAgent((prev) => ({ ...prev, name: e.target.value }))}
            />
            <Input
              placeholder="Specialization"
              value={newAgent.specialization}
              onChange={(e) => setNewAgent((prev) => ({ ...prev, specialization: e.target.value }))}
            />
            <Input
              placeholder="Description (optional)"
              value={newAgent.description}
              onChange={(e) => setNewAgent((prev) => ({ ...prev, description: e.target.value }))}
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={addAgent} disabled={!newAgent.name || !newAgent.specialization}>
                <Check className="h-3.5 w-3.5" />
                Add
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowAddForm(false)}>
                <X className="h-3.5 w-3.5" />
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {visibleAgents.map((agent) => (
          <Card key={agent.id} size="sm">
            <CardContent>
              {editingId === agent.id ? (
                <div className="space-y-2">
                  <Input
                    value={editDraft.name}
                    onChange={(e) => setEditDraft((prev) => ({ ...prev, name: e.target.value }))}
                    placeholder="Name"
                  />
                  <Input
                    value={editDraft.specialization}
                    onChange={(e) => setEditDraft((prev) => ({ ...prev, specialization: e.target.value }))}
                    placeholder="Specialization"
                  />
                  <Input
                    value={editDraft.description}
                    onChange={(e) => setEditDraft((prev) => ({ ...prev, description: e.target.value }))}
                    placeholder="Description"
                  />
                  <div className="flex gap-2">
                    <Button size="xs" onClick={saveEdit}>
                      <Check className="h-3 w-3" />
                      Save
                    </Button>
                    <Button size="xs" variant="ghost" onClick={cancelEdit}>
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                      {agent.name}
                    </p>
                    <div className="mt-1 flex items-center gap-1.5">
                      {(() => {
                        const original = agents.find((a) => a.id === agent.id);
                        const role = original?.role;
                        return role === "lead" ? (
                          <Badge variant="outline" className="text-[10px] border-[var(--color-accent)] text-[var(--color-accent)]">
                            Lead
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-[10px]">
                            Worker
                          </Badge>
                        );
                      })()}
                      <Badge variant="secondary">
                        {agent.specialization}
                      </Badge>
                    </div>
                    {agent.description && (
                      <p className="mt-1.5 text-xs text-[var(--color-text-secondary)] line-clamp-2">
                        {agent.description}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button size="icon-xs" variant="ghost" onClick={() => startEdit(agent)} aria-label="Edit agent">
                      <Pencil />
                    </Button>
                    <Button size="icon-xs" variant="ghost" onClick={() => removeAgent(agent.id)} aria-label="Remove agent">
                      <Trash2 />
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Button className="w-full" size="lg" onClick={handleConfirm} disabled={isPending || visibleAgents.length === 0}>
        {isPending ? (
          <>
            <Loader2 className="animate-spin" />
            Confirming team...
          </>
        ) : (
          `Confirm Team (${visibleAgents.length} agents)`
        )}
      </Button>
    </div>
  );
}
