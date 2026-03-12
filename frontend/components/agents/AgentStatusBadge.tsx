"use client";

import { Badge } from "@/components/ui/badge";
import {
  AGENT_OCCUPANCY_META,
  AGENT_STATUS_META,
} from "@/lib/config/status-meta";
import type { AgentOccupancyStatus, AgentStatus } from "@/lib/api";

interface AgentStatusBadgeProps {
  status: AgentStatus;
  occupancyStatus?: AgentOccupancyStatus;
}

export function AgentStatusBadge({ status, occupancyStatus = "idle" }: AgentStatusBadgeProps) {
  const statusConfig = AGENT_STATUS_META[status] ?? AGENT_STATUS_META.pending;
  const occupancyConfig = occupancyStatus !== "idle" ? AGENT_OCCUPANCY_META[occupancyStatus] : null;
  return (
    <div className="flex flex-wrap items-center justify-end gap-1">
      <Badge variant="outline" className={`text-xs font-medium ${statusConfig.className}`}>
        {statusConfig.label}
      </Badge>
      {occupancyConfig && (
        <Badge variant="outline" className={`text-xs font-medium ${occupancyConfig.className}`}>
          {occupancyConfig.label}
        </Badge>
      )}
    </div>
  );
}
