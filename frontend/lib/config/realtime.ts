export const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/api";
export const WS_RECONNECT_BASE_MS = 1500;
export const WS_RECONNECT_MAX_MS = 30000;
export const WS_PING_INTERVAL_MS = 30000;

export const WS_BROADCAST_EVENTS = new Set([
  "agent_status",
  "task_update",
  "task_created",
  "task_deleted",
  "team_created",
  "briefing_start",
  "briefing_complete",
  "research_complete",
]);

export const TOAST_DURATION_MS = 5000;
