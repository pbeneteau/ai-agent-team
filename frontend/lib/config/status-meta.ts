import {
  CheckCircle,
  Clock,
  Loader2,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import type {
  AgentOccupancyStatus,
  AgentStatus,
  TaskExecutionMode,
  TaskNodeStatus,
  TaskNodeType,
  TaskPlanStatus,
  TaskPriority,
  TaskStatus,
} from "@/lib/api";

export interface StatusMeta {
  Icon: LucideIcon;
  className: string;
  label: string;
}

export const TASK_STATUS_META: Record<TaskStatus, StatusMeta> = {
  pending: {
    Icon: Clock,
    className: "bg-slate-100 text-slate-600 border-slate-200",
    label: "Pending",
  },
  running: {
    Icon: Loader2,
    className: "bg-blue-100 text-blue-700 border-blue-200",
    label: "Running",
  },
  completed: {
    Icon: CheckCircle,
    className: "bg-green-100 text-green-700 border-green-200",
    label: "Completed",
  },
  failed: {
    Icon: XCircle,
    className: "bg-red-100 text-red-700 border-red-200",
    label: "Failed",
  },
};

export const TASK_PRIORITY_META: Record<TaskPriority, { className: string; label: string }> = {
  low: { className: "bg-gray-100 text-gray-600", label: "Low" },
  medium: { className: "bg-yellow-100 text-yellow-700", label: "Medium" },
  high: { className: "bg-red-100 text-red-700", label: "High" },
};

export const TASK_EXECUTION_MODE_LABELS: Record<TaskExecutionMode, string> = {
  auto: "Auto",
  standalone: "Standalone",
  dependency_graph: "Dependencies",
};

export const TASK_PLAN_STATUS_LABELS: Record<TaskPlanStatus, string> = {
  not_planned: "Not planned",
  planning: "Planning",
  ready: "Ready",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

export const TASK_NODE_TYPE_LABELS: Record<TaskNodeType, string> = {
  single_agent: "Single agent",
  specialist: "Specialist",
  lead_compile: "Lead compile",
};

export const TASK_NODE_STATUS_META: Record<TaskNodeStatus, { className: string; label: string }> = {
  pending: { className: "bg-slate-100 text-slate-600", label: "Pending" },
  blocked: { className: "bg-zinc-100 text-zinc-700", label: "Blocked" },
  ready: { className: "bg-violet-100 text-violet-700", label: "Ready" },
  running: { className: "bg-blue-100 text-blue-700", label: "Running" },
  completed: { className: "bg-green-100 text-green-700", label: "Completed" },
  failed: { className: "bg-red-100 text-red-700", label: "Failed" },
  skipped: { className: "bg-amber-100 text-amber-700", label: "Skipped" },
};

export const AGENT_STATUS_META: Record<AgentStatus, { label: string; className: string }> = {
  pending: { label: "Pending", className: "bg-gray-100 text-gray-600 border-gray-200" },
  learning: { label: "Learning", className: "bg-yellow-100 text-yellow-700 border-yellow-200 animate-pulse" },
  ready: { label: "Ready", className: "bg-green-100 text-green-700 border-green-200" },
  working: { label: "Working", className: "bg-blue-100 text-blue-700 border-blue-200 animate-pulse" },
  error: { label: "Error", className: "bg-red-100 text-red-700 border-red-200" },
};

export const AGENT_OCCUPANCY_META: Record<
  Exclude<AgentOccupancyStatus, "idle">,
  { label: string; className: string }
> = {
  assigned: {
    label: "Assigned",
    className: "bg-violet-100 text-violet-700 border-violet-200",
  },
  busy: {
    label: "Busy",
    className: "bg-blue-100 text-blue-700 border-blue-200 animate-pulse",
  },
};
