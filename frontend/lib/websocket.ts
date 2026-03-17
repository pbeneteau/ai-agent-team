import type { PlanDraft, PlanForm, PlanState } from "@/components/chat/plan-types";
import {
  WS_BASE,
  WS_PING_INTERVAL_MS,
  WS_RECONNECT_BASE_MS,
  WS_RECONNECT_MAX_MS,
} from "@/lib/config/realtime";

export type WSMessage = {
  type: string;
  data?: unknown;
  timestamp?: string;
};

export type ChatWSMessage =
  | { type: "stream_start"; timestamp?: string }
  | { type: "stream_chunk"; data?: string; timestamp?: string }
  | { type: "stream_end"; data?: string; timestamp?: string }
  | { type: "plan_form"; data?: { session_id?: string | null; form?: PlanForm | null }; timestamp?: string }
  | {
      type: "plan_preview";
      data?: {
        session_id?: string | null;
        state?: PlanState | null;
        kind?: "task" | "team" | null;
        draft?: PlanDraft | null;
        last_error?: string | null;
      };
      timestamp?: string;
    }
  | { type: "plan_confirmation_required"; data?: { session_id?: string | null; kind?: string | null }; timestamp?: string }
  | { type: "plan_revising"; data?: { session_id?: string | null; draft_id?: string | null; state?: PlanState | null }; timestamp?: string }
  | {
      type: "plan_executing";
      data?: { session_id?: string | null; draft_id?: string | null; kind?: string | null; draft?: PlanDraft | null };
      timestamp?: string;
    }
  | { type: "plan_completed"; data?: { kind?: string; result?: unknown }; timestamp?: string }
  | { type: "plan_cancelled"; data?: { session_id?: string | null; draft_id?: string | null; state?: PlanState | null }; timestamp?: string }
  | {
      type: "plan_failed";
      data?: { state?: PlanState | null; error?: string; draft?: PlanDraft | null };
      timestamp?: string;
    }
  | { type: "navigate"; data?: { to?: string }; timestamp?: string }
  | { type: "team_created"; data?: unknown; timestamp?: string }
  | { type: "task_created"; data?: unknown; timestamp?: string }
  | { type: "error"; data?: string; timestamp?: string }
  | { type: "pong"; timestamp?: string };

export type WSMessageHandler<TMessage extends WSMessage = WSMessage> = (message: TMessage) => void;

export class WSClient<TMessage extends WSMessage = WSMessage> {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: WSMessageHandler<TMessage>[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private attempt = 0;

  constructor(path: string) {
    this.url = `${WS_BASE}${path}`;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.attempt = 0;
      console.debug(`[WS] Connected: ${this.url}`);
      this.pingInterval = setInterval(() => this.send({ type: "ping" }), WS_PING_INTERVAL_MS);
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as TMessage;
        if (message.type === "pong") return;
        this.handlers.forEach((h) => h(message));
      } catch (e) {
        console.error("[WS] Parse error:", e);
      }
    };

    this.ws.onerror = () => {
      // Browsers intentionally hide WS error details — close event fires right after with a code.
      // We log on close instead where we have the code and reason.
    };

    this.ws.onclose = (e) => {
      if (this.pingInterval) clearInterval(this.pingInterval);
      if (!this.shouldReconnect) return;

      this.attempt += 1;
      const delay = Math.min(
        WS_RECONNECT_BASE_MS * 2 ** (this.attempt - 1),
        WS_RECONNECT_MAX_MS,
      );

      if (this.attempt === 1) {
        // First disconnect — could be a normal startup race, log quietly
        console.debug(`[WS] Disconnected (code ${e.code}), reconnecting in ${delay}ms…`);
      } else {
        console.warn(`[WS] ${this.url} — attempt ${this.attempt}, code ${e.code}${e.reason ? ` "${e.reason}"` : ""}, retry in ${Math.round(delay / 1000)}s`);
      }

      this.reconnectTimer = setTimeout(() => this.connect(), delay);
    };
  }

  send(data: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  onMessage(handler: WSMessageHandler<TMessage>) {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.pingInterval) clearInterval(this.pingInterval);
    this.ws?.close();
  }

  get readyState() {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }
}

export function createChatWS() {
  return new WSClient<ChatWSMessage>("/chat/ws");
}
