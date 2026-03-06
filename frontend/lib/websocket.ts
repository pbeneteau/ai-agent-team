const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/api";

const RECONNECT_BASE_MS = 1500;
const RECONNECT_MAX_MS = 30000;

export type WSMessage = {
  type: string;
  data?: unknown;
  timestamp?: string;
};

export type WSMessageHandler = (message: WSMessage) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: WSMessageHandler[] = [];
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
      this.pingInterval = setInterval(() => this.send({ type: "ping" }), 30000);
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WSMessage;
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
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** (this.attempt - 1), RECONNECT_MAX_MS);

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

  onMessage(handler: WSMessageHandler) {
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
  return new WSClient("/chat/ws");
}

export function createTeamBuilderWS() {
  return new WSClient("/chat/team-builder/ws");
}
