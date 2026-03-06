"use client";

import { Badge } from "@/components/ui/badge";
import type { AgentStatus } from "@/lib/api";

const STATUS_CONFIG: Record<AgentStatus, { label: string; className: string }> = {
  pending: { label: "En attente", className: "bg-gray-100 text-gray-600 border-gray-200" },
  learning: { label: "Apprentissage", className: "bg-yellow-100 text-yellow-700 border-yellow-200 animate-pulse" },
  ready: { label: "Prêt", className: "bg-green-100 text-green-700 border-green-200" },
  working: { label: "En travail", className: "bg-blue-100 text-blue-700 border-blue-200 animate-pulse" },
  error: { label: "Erreur", className: "bg-red-100 text-red-700 border-red-200" },
};

export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return (
    <Badge variant="outline" className={`text-xs font-medium ${config.className}`}>
      {config.label}
    </Badge>
  );
}
