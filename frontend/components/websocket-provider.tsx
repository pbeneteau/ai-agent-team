"use client";

/**
 * WebSocket provider — connects on mount, bridges events to query invalidation.
 *
 * Ref: TDD-05 Section 6.3
 */

import { useWebSocket } from "@/lib/hooks/use-websocket";

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  useWebSocket();
  return <>{children}</>;
}
