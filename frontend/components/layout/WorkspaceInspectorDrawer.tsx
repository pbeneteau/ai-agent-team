"use client";

import Link from "next/link";
import type { TouchEvent, WheelEvent } from "react";

import { X } from "lucide-react";

import { AgentStatusBadge } from "@/components/agents/AgentStatusBadge";
import { WorkspacePanel } from "@/components/agents/WorkspacePanel";
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
  onKnowledgeChanged,
  showSpecialization = false,
  showOccupancy = false,
  showGoal = true,
  showBackstory = false,
}: WorkspaceInspectorDrawerProps) {
  return (
    <div
      className="fixed inset-y-0 right-0 z-50 flex w-[520px] flex-col overflow-hidden border-l bg-white shadow-2xl"
      onWheelCapture={stopInspectorScrollPropagation}
      onTouchMoveCapture={stopInspectorScrollPropagation}
    >
      <div className="border-b px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Quick preview</p>
            <p className="mt-1 text-sm font-semibold text-slate-800">{agent.name}&apos;s workspace</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link href={`/team/agents/${agent.id}`}>
            <Button variant="outline" size="sm" className="rounded-full">
              Open agent page
            </Button>
          </Link>
        </div>
      </div>

      <div
        className="max-h-[38vh] shrink-0 space-y-3 overflow-y-auto border-b bg-slate-50/70 px-4 py-4"
        onWheelCapture={stopInspectorScrollPropagation}
        onTouchMoveCapture={stopInspectorScrollPropagation}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-base font-semibold text-slate-900">{agent.name}</p>
            <p className="text-sm text-slate-600">{agent.title}</p>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2">
            {agent.role ? <Badge variant="outline">{roleLabel[agent.role]}</Badge> : null}
            <AgentStatusBadge status={agent.status} occupancyStatus={agent.occupancy_status} />
          </div>
        </div>

        {showSpecialization && agent.specialization ? (
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-700">
              {agent.specialization.replace(/_/g, " ")}
            </span>
          </div>
        ) : null}

        {showOccupancy && agent.occupancy_status !== "idle" ? (
          <div className="rounded-lg border border-blue-100 bg-blue-50/80 px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
              {agent.occupancy_status === "busy" ? "Running" : "Assigned"}
            </p>
            <p className="mt-1 text-sm text-blue-900">{agent.current_task_title ?? "Current task"}</p>
            {agent.current_node_title ? (
              <p className="mt-1 text-xs text-blue-700">Step: {agent.current_node_title}</p>
            ) : null}
          </div>
        ) : null}

        {showGoal && agent.goal ? (
          <div className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Mission</p>
            <p className="text-sm leading-relaxed text-slate-700">{agent.goal}</p>
          </div>
        ) : null}

        {showBackstory && agent.backstory ? (
          <div className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Role description</p>
            <p className="text-sm leading-relaxed text-slate-700">{agent.backstory}</p>
          </div>
        ) : null}
      </div>

      <div
        className="min-h-0 flex-1 overflow-hidden"
        onWheelCapture={stopInspectorScrollPropagation}
        onTouchMoveCapture={stopInspectorScrollPropagation}
      >
        <WorkspacePanel agentId={agent.id} agentName={agent.name} onKnowledgeChanged={onKnowledgeChanged} />
      </div>
    </div>
  );
}
