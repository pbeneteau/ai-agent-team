"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AgentStatusBadge } from "./AgentStatusBadge";
import type { Agent, ModelTier } from "@/lib/api";
import { api } from "@/lib/api";
import { ArrowUpRight, Bot, Crown, Sparkles, User, Zap } from "lucide-react";

const ROLE_ICON: Record<string, React.ReactNode> = {
  associate: <Crown className="w-4 h-4 text-amber-500" />,
  team_lead: <Bot className="w-4 h-4 text-blue-500" />,
  specialist: <User className="w-4 h-4 text-slate-500" />,
};

const ROLE_LABEL: Record<Agent["role"], string> = {
  associate: "Associate",
  team_lead: "Lead",
  specialist: "Specialist",
};

const TIER_CONFIG: Record<ModelTier, { label: string; icon: React.ReactNode; className: string }> = {
  sonnet: {
    label: "Sonnet",
    icon: <Zap className="w-3 h-3" />,
    className: "bg-slate-100 text-slate-600 hover:bg-slate-200",
  },
  opus: {
    label: "Opus",
    icon: <Sparkles className="w-3 h-3" />,
    className: "bg-violet-100 text-violet-700 hover:bg-violet-200",
  },
};

interface Props {
  agent: Agent;
  onTierChange?: (agent: Agent) => void;
  onOpen?: (agent: Agent) => void;
}

export function AgentCard({ agent, onTierChange, onOpen }: Props) {
  const [currentTier, setCurrentTier] = useState<ModelTier>(agent.model_tier ?? "sonnet");
  const [switching, setSwitching] = useState(false);
  const tier = TIER_CONFIG[currentTier];

  async function toggleTier(e: React.MouseEvent) {
    e.stopPropagation();
    const nextTier: ModelTier = currentTier === "sonnet" ? "opus" : "sonnet";
    const costNote = nextTier === "opus" ? " (higher-cost model)" : "";
    if (!confirm(`Switch ${agent.name} to Claude ${nextTier.charAt(0).toUpperCase() + nextTier.slice(1)}${costNote}?`)) return;
    setSwitching(true);
    try {
      const updated = await api.setAgentModelTier(agent.id, nextTier);
      setCurrentTier(updated.model_tier);
      if (onTierChange) onTierChange(updated);
    } catch {
      alert("Unable to change the model. Please try again.");
    } finally {
      setSwitching(false);
    }
  }

  return (
    <Card
      className={`transition-colors ${onOpen ? "cursor-pointer hover:border-[var(--ops-border-strong)] hover:bg-[var(--ops-surface-elevated)]" : ""}`}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      onClick={() => onOpen?.(agent)}
      onKeyDown={(event) => {
        if (!onOpen) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(agent);
        }
      }}
    >
      <CardHeader className="flex flex-row items-start gap-2 pb-2">
        <div className="mt-0.5">{ROLE_ICON[agent.role] ?? <User className="w-4 h-4" />}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-semibold">{agent.name}</p>
            <Badge variant="secondary" className="text-[10px]">
              {ROLE_LABEL[agent.role]}
            </Badge>
          </div>
          <p className="truncate text-xs text-muted-foreground">{agent.title}</p>
        </div>
        <AgentStatusBadge status={agent.status} occupancyStatus={agent.occupancy_status} />
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-[10px]">
            {agent.specialization.replace(/_/g, " ")}
          </Badge>
          {agent.tools.slice(0, 2).map((tool) => (
            <Badge key={tool} variant="secondary" className="text-[10px]">
              {tool.replace(/_/g, " ")}
            </Badge>
          ))}
          {agent.tools.length > 2 ? (
            <Badge variant="secondary" className="text-[10px]">
              +{agent.tools.length - 2}
            </Badge>
          ) : null}
        </div>

        {agent.occupancy_status !== "idle" && (
          <div className="rounded-[12px] border ops-signal-info px-2.5 py-2 text-[11px]">
            <p className="font-medium">
              {agent.occupancy_status === "busy" ? "Working on" : "Selected for"}
              {" "}
              {agent.current_task_title ?? "a task"}
            </p>
            {agent.current_node_title && (
              <p className="mt-0.5 text-blue-700">Step: {agent.current_node_title}</p>
            )}
          </div>
        )}

        <div className="flex items-center justify-between gap-3">
          <button
            onClick={toggleTier}
            disabled={switching}
            title={`Current model: Claude ${currentTier.charAt(0).toUpperCase() + currentTier.slice(1)} — click to switch`}
            className={`flex items-center gap-1 text-[10px] font-medium rounded-md px-1.5 py-0.5 transition-colors ${tier.className} ${switching ? "opacity-50 cursor-wait" : "cursor-pointer"}`}
          >
            {tier.icon}
            {tier.label}
          </button>
          {onOpen ? (
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500">
              Agent page
              <ArrowUpRight className="size-3.5" />
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
