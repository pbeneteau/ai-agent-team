"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { AgentStatusBadge } from "./AgentStatusBadge";
import type { Agent, ModelTier } from "@/lib/api";
import { api } from "@/lib/api";
import { Bot, Crown, User, Zap, Sparkles } from "lucide-react";

const ROLE_ICON: Record<string, React.ReactNode> = {
  associate: <Crown className="w-4 h-4 text-amber-500" />,
  team_lead: <Bot className="w-4 h-4 text-blue-500" />,
  specialist: <User className="w-4 h-4 text-slate-500" />,
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
      className={`transition-all ${onOpen ? "cursor-pointer hover:-translate-y-0.5 hover:ring-foreground/20" : ""}`}
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
      <CardHeader className="pb-2 flex flex-row items-center gap-2">
        {ROLE_ICON[agent.role] ?? <User className="w-4 h-4" />}
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{agent.name}</p>
          <p className="text-xs text-muted-foreground truncate">{agent.title}</p>
        </div>
        <AgentStatusBadge status={agent.status} occupancyStatus={agent.occupancy_status} />
      </CardHeader>
      <CardContent className="pt-0 space-y-2">
        <p className="text-xs text-muted-foreground">{agent.specialization.replace(/_/g, " ")}</p>
        {agent.occupancy_status !== "idle" && (
          <div className="rounded-md border border-blue-100 bg-blue-50/70 px-2 py-1.5 text-[11px] text-blue-900">
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

        <div className="flex items-center justify-between">
          {/* Model tier toggle */}
          <button
            onClick={toggleTier}
            disabled={switching}
            title={`Current model: Claude ${currentTier.charAt(0).toUpperCase() + currentTier.slice(1)} — click to switch`}
            className={`flex items-center gap-1 text-[10px] font-medium rounded-md px-1.5 py-0.5 transition-colors ${tier.className} ${switching ? "opacity-50 cursor-wait" : "cursor-pointer"}`}
          >
            {tier.icon}
            {tier.label}
          </button>

          {/* Tools */}
          <div className="flex flex-wrap gap-1 justify-end">
            {agent.tools.slice(0, 2).map((tool) => (
              <span key={tool} className="text-[10px] bg-slate-100 text-slate-600 rounded-md px-1.5 py-0.5">
                {tool.replace(/_/g, " ")}
              </span>
            ))}
            {agent.tools.length > 2 && (
              <span className="text-[10px] bg-slate-100 text-slate-600 rounded-md px-1.5 py-0.5">
                +{agent.tools.length - 2}
              </span>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
