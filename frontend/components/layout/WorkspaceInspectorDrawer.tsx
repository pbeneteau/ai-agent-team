"use client";

import Link from "next/link";
import type { ReactNode, TouchEvent, WheelEvent } from "react";

import { ArrowUpRight, Shield, Wrench, X } from "lucide-react";

import { AgentStatusBadge } from "@/components/agents/AgentStatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Agent } from "@/lib/api";

const roleLabel: Record<Agent["role"], string> = {
  associate: "AI associate",
  team_lead: "Team lead",
  specialist: "Specialist",
};

function stopInspectorScrollPropagation(event: WheelEvent | TouchEvent) {
  event.stopPropagation();
}

interface WorkspaceInspectorDrawerProps {
  agent: Agent;
  onClose: () => void;
  onKnowledgeChanged?: () => void;
  showSpecialization?: boolean;
  showOccupancy?: boolean;
  showGoal?: boolean;
  showBackstory?: boolean;
}

export function WorkspaceInspectorDrawer({
  agent,
  onClose,
  showSpecialization = false,
  showOccupancy = false,
  showGoal = true,
  showBackstory = false,
}: WorkspaceInspectorDrawerProps) {
  const enabledGitBindings = agent.git_bindings.filter((binding) => binding.enabled).length;
  const enabledMcpBindings = agent.mcp_tool_bindings.filter((binding) => binding.enabled).length;

  return (
    <div
      className="fixed inset-y-0 right-0 z-50 flex w-[420px] flex-col overflow-hidden border-l border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] shadow-[0_18px_42px_-28px_rgba(15,23,42,0.22)]"
      onWheelCapture={stopInspectorScrollPropagation}
      onTouchMoveCapture={stopInspectorScrollPropagation}
    >
      <div className="border-b px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Agent preview</p>
            <p className="mt-1 text-sm font-semibold text-slate-800">{agent.name}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>
      </div>

      <div
        className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-[var(--ops-surface-muted)] px-4 py-4"
        onWheelCapture={stopInspectorScrollPropagation}
        onTouchMoveCapture={stopInspectorScrollPropagation}
      >
        <div className="rounded-[18px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-base font-semibold text-slate-900">{agent.name}</p>
              <p className="text-sm text-slate-600">{agent.title}</p>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2">
              {agent.role ? <Badge variant="outline">{roleLabel[agent.role]}</Badge> : null}
              <AgentStatusBadge status={agent.status} occupancyStatus={agent.occupancy_status} />
            </div>
          </div>

          {showSpecialization && agent.specialization ? (
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-[var(--ops-surface-muted)] px-2 py-1 text-slate-700">
                {agent.specialization.replace(/_/g, " ")}
              </span>
            </div>
          ) : null}
        </div>

        {showOccupancy && agent.occupancy_status !== "idle" ? (
          <div className="rounded-[16px] border ops-signal-info px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
              {agent.occupancy_status === "busy" ? "Running" : "Assigned"}
            </p>
            <p className="mt-1 text-sm font-semibold text-blue-900">{agent.current_task_title ?? "Current task"}</p>
            {agent.current_node_title ? (
              <p className="mt-1 text-xs text-blue-700">Step: {agent.current_node_title}</p>
            ) : null}
          </div>
        ) : null}

        <div className="grid grid-cols-2 gap-3">
          <SignalTile label="Tools" value={agent.tools.length} icon={<Wrench className="size-3.5" />} />
          <SignalTile label="Git access" value={enabledGitBindings} icon={<Shield className="size-3.5" />} />
          <SignalTile label="MCP tools" value={enabledMcpBindings} icon={<Shield className="size-3.5" />} />
          <SignalTile label="Workspace" value={agent.workspace_path ? "Ready" : "None"} />
        </div>

        {showGoal && agent.goal ? (
          <div className="rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Mission</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-700">{agent.goal}</p>
          </div>
        ) : null}

        {showBackstory && agent.backstory ? (
          <div className="rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Role description</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-700">{agent.backstory}</p>
          </div>
        ) : null}

        <div className="rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Quick capabilities</p>
          {agent.tools.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {agent.tools.slice(0, 8).map((tool) => (
                <span key={tool} className="rounded-full bg-[var(--ops-surface-muted)] px-2 py-1 text-[11px] text-slate-700">
                  {tool.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm text-slate-500">No explicit tool has been exposed yet.</p>
          )}
        </div>
      </div>

      <div className="border-t bg-white px-4 py-4">
        <div className="space-y-2">
          <Link href={`/team/agents/${agent.id}`} onClick={onClose}>
            <Button className="w-full gap-2">
              <ArrowUpRight className="size-4" />
              Open agent page
            </Button>
          </Link>
          <p className="text-xs text-slate-500">
            This drawer stays a lightweight preview. Use the full page for knowledge, files, capabilities, and admin controls.
          </p>
        </div>
      </div>
    </div>
  );
}

function SignalTile({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | number;
  icon?: ReactNode;
}) {
  return (
    <div className="rounded-[14px] border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] px-3 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">{value}</p>
        </div>
        {icon ? <div className="text-slate-400">{icon}</div> : null}
      </div>
    </div>
  );
}
