"use client";

/**
 * Roster overview — agent grid with status and role filters.
 * Ref: TDD-05 Section 14.1, TDD-01 J4 Step 1
 */

import { useState, useMemo } from "react";
import { Users, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRosterList } from "@/lib/hooks/use-roster";
import { AgentCard } from "@/features/roster/agent-card";
import { AddAgentDialog } from "@/features/roster/add-agent-dialog";
import type { AgentListItem, AgentRole, AgentStatus } from "@/lib/types/api";

const statusFilters: Array<{ value: AgentStatus | undefined; label: string }> = [
  { value: undefined, label: "All" },
  { value: "ready", label: "Ready" },
  { value: "learning", label: "Learning" },
  { value: "working", label: "Working" },
  { value: "reflecting", label: "Reflecting" },
];

const roleFilters: Array<{ value: AgentRole | undefined; label: string }> = [
  { value: undefined, label: "All roles" },
  { value: "lead", label: "Leads" },
  { value: "worker", label: "Workers" },
];

function AgentGrid({ agents }: { agents: AgentListItem[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}

export default function RosterPage() {
  const [statusFilter, setStatusFilter] = useState<AgentStatus | undefined>();
  const [roleFilter, setRoleFilter] = useState<AgentRole | undefined>();
  const [addOpen, setAddOpen] = useState(false);
  const { data, isLoading } = useRosterList(statusFilter ? { status: statusFilter } : undefined);

  const allAgents = data?.items ?? [];

  // Client-side role filtering
  const agents = useMemo(
    () => roleFilter ? allAgents.filter((a) => a.role === roleFilter) : allAgents,
    [allAgents, roleFilter],
  );

  // Group by role only when showing everything (no filters active)
  const grouped = !statusFilter && !roleFilter;
  const leads = useMemo(() => agents.filter((a) => a.role === "lead"), [agents]);
  const workers = useMemo(() => agents.filter((a) => a.role === "worker"), [agents]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Users className="h-6 w-6 text-[var(--color-accent)]" />
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">Agency Roster</h1>
        </div>
        <Button onClick={() => setAddOpen(true)}>
          <Plus className="h-4 w-4" /> Add Agent
        </Button>
      </div>

      {/* Filters */}
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter by status">
          {statusFilters.map((f) => (
            <Button
              key={f.label}
              variant={statusFilter === f.value ? "default" : "ghost"}
              size="sm"
              role="tab"
              aria-selected={statusFilter === f.value}
              onClick={() => setStatusFilter(f.value)}
            >
              {f.label}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter by role">
          {roleFilters.map((f) => (
            <Button
              key={f.label}
              variant={roleFilter === f.value ? "secondary" : "ghost"}
              size="sm"
              role="tab"
              aria-selected={roleFilter === f.value}
              onClick={() => setRoleFilter(f.value)}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Agent grid */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-44 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      ) : agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-20">
          <Users className="h-10 w-10 text-[var(--color-text-tertiary)]" />
          <p className="text-sm text-[var(--color-text-secondary)]">
            {statusFilter || roleFilter ? "No agents match this filter." : "No agents yet. Add one to get started."}
          </p>
        </div>
      ) : grouped ? (
        <div className="space-y-8" aria-live="polite">
          {leads.length > 0 && (
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--color-accent)]">
                Leads · {leads.length}
              </h2>
              <AgentGrid agents={leads} />
            </section>
          )}
          {workers.length > 0 && (
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                Workers · {workers.length}
              </h2>
              <AgentGrid agents={workers} />
            </section>
          )}
        </div>
      ) : (
        <div aria-live="polite">
          <AgentGrid agents={agents} />
        </div>
      )}

      <AddAgentDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  );
}
