"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Send, Bot, User, Loader2, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { WSClient, createTeamBuilderWS } from "@/lib/websocket";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

interface TeamBuilderChatProps {
  onTeamCreated?: (data: unknown) => void;
}

export function TeamBuilderChat({ onTeamCreated }: TeamBuilderChatProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Bonjour ! Je suis Alex. Je vais vous aider à construire votre équipe d'agents IA. Commençons par votre projet — décrivez-le moi en quelques mots.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [awaitingConfirmation, setAwaitingConfirmation] = useState(false);
  const [teamCreated, setTeamCreated] = useState(false);
  const wsRef = useRef<WSClient | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = createTeamBuilderWS();
    wsRef.current = ws;
    ws.connect();

    const unsub = ws.onMessage((msg) => {
      if (msg.type === "stream_start") {
        setIsStreaming(true);
        setMessages((prev) => [...prev, { role: "assistant", content: "", streaming: true }]);
      } else if (msg.type === "stream_chunk") {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.streaming) {
            return [...prev.slice(0, -1), { ...last, content: last.content + (msg.data as string) }];
          }
          return prev;
        });
      } else if (msg.type === "stream_end") {
        setIsStreaming(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.streaming) return [...prev.slice(0, -1), { ...last, streaming: false }];
          return prev;
        });
      } else if (msg.type === "team_confirmed") {
        setAwaitingConfirmation(true);
      } else if (msg.type === "team_created") {
        setTeamCreated(true);
        setAwaitingConfirmation(false);
        if (onTeamCreated) onTeamCreated(msg.data);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "✅ Équipe créée avec succès ! Vos agents sont en phase d'apprentissage. Rendez-vous sur le Dashboard pour suivre leur progression.",
          },
        ]);
      }
    });

    const checkConnection = setInterval(() => {
      setIsConnected(ws.readyState === WebSocket.OPEN);
    }, 1000);

    return () => {
      unsub();
      clearInterval(checkConnection);
      ws.disconnect();
    };
  }, [onTeamCreated]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(() => {
    const content = input.trim();
    if (!content || isStreaming) return;
    setMessages((prev) => [...prev, { role: "user", content }]);
    wsRef.current?.send({ type: "chat", content });
    setInput("");
  }, [input, isStreaming]);

  const confirmTeam = useCallback(() => {
    wsRef.current?.send({ type: "confirm_team" });
    setAwaitingConfirmation(false);
    setMessages((prev) => [...prev, { role: "user", content: "Oui, créez l'équipe !" }]);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-2 border-b bg-slate-50">
        <div className={cn("w-2 h-2 rounded-full", isConnected ? "bg-green-500" : "bg-red-400")} />
        <span className="text-xs text-muted-foreground">
          {isConnected ? "Connecté — Construction d'équipe" : "Reconnexion…"}
        </span>
      </div>

      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4 max-w-3xl mx-auto">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}
            >
              {msg.role === "assistant" && (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center flex-shrink-0 mt-1">
                  <Bot className="w-4 h-4 text-white" />
                </div>
              )}
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                  msg.role === "user"
                    ? "bg-indigo-600 text-white rounded-tr-sm"
                    : "bg-white border border-slate-200 text-slate-800 rounded-tl-sm shadow-sm"
                )}
              >
                <span className="whitespace-pre-wrap">
                  {msg.content.replace(/```json[\s\S]*?```/g, "").trim() || msg.content}
                </span>
                {msg.streaming && (
                  <span className="inline-block w-1 h-4 ml-1 bg-current animate-pulse rounded" />
                )}
              </div>
              {msg.role === "user" && (
                <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center flex-shrink-0 mt-1">
                  <User className="w-4 h-4 text-slate-600" />
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {awaitingConfirmation && !teamCreated && (
        <div className="border-t bg-green-50 p-4">
          <div className="max-w-3xl mx-auto flex items-center justify-between">
            <p className="text-sm text-green-700 font-medium">
              Alex a proposé une structure d&apos;équipe. Souhaitez-vous la créer ?
            </p>
            <Button onClick={confirmTeam} className="bg-green-600 hover:bg-green-700 gap-2">
              <CheckCircle className="w-4 h-4" />
              Créer l&apos;équipe
            </Button>
          </div>
        </div>
      )}

      {!teamCreated && (
        <div className="border-t p-4 bg-white">
          <div className="max-w-3xl mx-auto flex gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Décrivez votre projet, vos besoins…"
              className="resize-none min-h-[60px] max-h-[160px]"
              disabled={isStreaming}
            />
            <Button
              onClick={sendMessage}
              disabled={!input.trim() || isStreaming || !isConnected}
              className="self-end bg-indigo-600 hover:bg-indigo-700"
            >
              {isStreaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
