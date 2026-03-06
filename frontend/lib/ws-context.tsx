"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useCallback,
  useState,
  ReactNode,
} from "react";
import { WSClient, WSMessage } from "./websocket";
import { CheckCircle, XCircle, Info, X } from "lucide-react";

type WsEventHandler = (msg: WSMessage) => void;

// ─── Toast types ────────────────────────────────────────────────────────────

type ToastKind = "success" | "error" | "info";

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastContextValue {
  push: (kind: ToastKind, message: string) => void;
}

const ToastContext = createContext<ToastContextValue>({ push: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

// ─── WS context ─────────────────────────────────────────────────────────────

interface WsContextValue {
  subscribe: (handler: WsEventHandler) => () => void;
}

const WsContext = createContext<WsContextValue>({ subscribe: () => () => {} });

// Events that are sent via broadcast (not personal) and should be relayed to subscribers.
// Personal messages (stream_start, stream_chunk, stream_end, error, navigate, pong)
// are handled by the ChatPanel itself and intentionally excluded here.
const BROADCAST_EVENTS = new Set([
  "agent_status",
  "task_update",
  "task_created",
  "team_created",
  "briefing_start",
  "briefing_complete",
  "research_complete",
]);

// ─── Toast display ───────────────────────────────────────────────────────────

const KIND_CONFIG: Record<ToastKind, { icon: React.ReactNode; bg: string; text: string }> = {
  success: {
    icon: <CheckCircle className="w-4 h-4 shrink-0" />,
    bg: "bg-green-600",
    text: "text-white",
  },
  error: {
    icon: <XCircle className="w-4 h-4 shrink-0" />,
    bg: "bg-red-600",
    text: "text-white",
  },
  info: {
    icon: <Info className="w-4 h-4 shrink-0" />,
    bg: "bg-slate-800",
    text: "text-white",
  },
};

function ToastContainer({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: number) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => {
        const cfg = KIND_CONFIG[t.kind];
        return (
          <div
            key={t.id}
            className={`flex items-center gap-2 rounded-lg shadow-lg px-4 py-3 text-sm max-w-sm pointer-events-auto ${cfg.bg} ${cfg.text} animate-in slide-in-from-right-4 duration-200`}
          >
            {cfg.icon}
            <span className="flex-1">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="ml-2 opacity-70 hover:opacity-100 transition-opacity"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ─── Combined provider ───────────────────────────────────────────────────────

function wsEventToToast(msg: WSMessage): { kind: ToastKind; message: string } | null {
  const data = (msg.data ?? {}) as Record<string, string>;

  switch (msg.type) {
    case "agent_status":
      if (data.status === "ready") {
        return { kind: "success", message: `${data.name ?? "Agent"} est prêt` };
      }
      if (data.status === "error") {
        return { kind: "error", message: `${data.name ?? "Agent"} : erreur d'apprentissage` };
      }
      return null;

    case "task_update":
      if (data.status === "completed") {
        return { kind: "success", message: `Tâche terminée avec succès` };
      }
      if (data.status === "failed") {
        return { kind: "error", message: `Tâche échouée` };
      }
      return null;

    case "task_created":
      return { kind: "info", message: `Nouvelle tâche créée` };

    case "research_complete":
      return {
        kind: "success",
        message: `Recherche terminée : ${data.topic ?? ""}`,
      };

    case "briefing_complete":
      return {
        kind: "info",
        message: `Briefing projet distribué à ${data.agent_count ?? data.agents_updated ?? "?"} agents`,
      };

    default:
      return null;
  }
}

let _toastSeq = 0;
const TOAST_DURATION_MS = 5000;

export function WsEventProvider({ children }: { children: ReactNode }) {
  const wsRef = useRef<WSClient | null>(null);
  const handlersRef = useRef<Set<WsEventHandler>>(new Set());
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = ++_toastSeq;
    setToasts((prev) => [...prev, { id, kind, message }]);
    setTimeout(() => dismiss(id), TOAST_DURATION_MS);
  }, [dismiss]);

  useEffect(() => {
    const ws = new WSClient("/chat/ws");
    wsRef.current = ws;
    ws.connect();

    const unsub = ws.onMessage((msg) => {
      if (!BROADCAST_EVENTS.has(msg.type)) return;
      handlersRef.current.forEach((h) => h(msg));

      // Push toast for relevant events
      const toast = wsEventToToast(msg);
      if (toast) {
        const id = ++_toastSeq;
        setToasts((prev) => [...prev, { id, ...toast }]);
        setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), TOAST_DURATION_MS);
      }
    });

    return () => {
      unsub();
      ws.disconnect();
    };
  }, []);

  const subscribe = useCallback((handler: WsEventHandler) => {
    handlersRef.current.add(handler);
    return () => {
      handlersRef.current.delete(handler);
    };
  }, []);

  return (
    <ToastContext.Provider value={{ push }}>
      <WsContext.Provider value={{ subscribe }}>
        {children}
        <ToastContainer toasts={toasts} dismiss={dismiss} />
      </WsContext.Provider>
    </ToastContext.Provider>
  );
}

export function useWsEvent(
  handler: WsEventHandler,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  deps: any[] = [],
) {
  const { subscribe } = useContext(WsContext);
  useEffect(() => {
    return subscribe(handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscribe, ...deps]);
}
