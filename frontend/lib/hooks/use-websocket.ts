"use client";

/**
 * WebSocket connection hook with auto-reconnect and query invalidation bridge.
 *
 * Ref: TDD-05 Section 6
 *
 * Connection lifecycle:
 * 1. Connect on mount
 * 2. Reconnect on disconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)
 * 3. Heartbeat ping every 30s to detect stale connections
 * 4. Disconnect on unmount
 *
 * Event → Query Invalidation Bridge:
 * - artifact.status_changed → invalidate artifacts.detail, artifacts.status, artifacts.list
 * - agent.status_changed → invalidate roster.detail, roster.all
 * - execution.wave_completed → invalidate artifacts.status
 * - execution.failed → invalidate artifacts.detail, artifacts.status
 * - budget.warning → show persistent warning toast
 */

import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { queryKeys } from "@/lib/query-keys";
import type { WSEvent } from "@/lib/types/api";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";
const PING_INTERVAL = 30_000;
const MAX_RECONNECT_DELAY = 30_000;

export function useWebSocket() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const handleEvent = useCallback(
    (event: WSEvent) => {
      const { type, payload } = event;

      switch (type) {
        case "artifact.status_changed": {
          const { artifact_id, status, project_id } = payload as {
            artifact_id: string;
            status: string;
            project_id: string;
          };

          queryClient.invalidateQueries({
            queryKey: queryKeys.artifacts.detail(artifact_id),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.artifacts.status(artifact_id),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.artifacts.list(project_id),
          });

          if (status === "in_review") {
            toast.success("Deliverable Ready for Review");
          }
          break;
        }

        case "agent.status_changed": {
          const { agent_id } = payload as { agent_id: string };

          queryClient.invalidateQueries({
            queryKey: queryKeys.roster.detail(agent_id),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.roster.all(),
          });
          break;
        }

        case "execution.wave_completed": {
          const { artifact_id } = payload as { artifact_id: string };

          queryClient.invalidateQueries({
            queryKey: queryKeys.artifacts.status(artifact_id),
          });
          break;
        }

        case "execution.failed": {
          const { artifact_id, error_message } = payload as {
            artifact_id: string;
            error_message: string;
          };

          queryClient.invalidateQueries({
            queryKey: queryKeys.artifacts.detail(artifact_id),
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.artifacts.status(artifact_id),
          });

          toast.error("Execution Failed", { description: error_message });
          break;
        }

        case "budget.warning": {
          const { usage_pct } = payload as { usage_pct: number };

          toast.warning("Budget Warning", {
            description: `${usage_pct}% of monthly budget used`,
            duration: Infinity, // Persistent
          });
          break;
        }
      }
    },
    [queryClient],
  );

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;

        // Start heartbeat ping
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, PING_INTERVAL);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WSEvent;
          handleEvent(data);
        } catch {
          // Ignore non-JSON messages (pong, etc.)
        }
      };

      ws.onclose = () => {
        cleanup();
        scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose will fire after onerror
      };
    } catch {
      scheduleReconnect();
    }
  }, [handleEvent]);

  const cleanup = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;

    const attempt = reconnectAttemptRef.current;
    const delay = Math.min(1000 * Math.pow(2, attempt), MAX_RECONNECT_DELAY);
    reconnectAttemptRef.current = attempt + 1;

    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      cleanup();

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }

      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, cleanup]);
}
