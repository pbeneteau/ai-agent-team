"use client";

import { ChatPanel } from "@/components/chat/ChatPanel";

export default function ChatPage() {
  return (
    <div className="h-full flex flex-col">
      <div className="px-8 py-4 border-b bg-white shrink-0">
        <h1 className="text-xl font-bold text-slate-900">Chat avec Alex</h1>
        <p className="text-sm text-slate-500">Votre associé IA — déléguez, organisez, avancez.</p>
      </div>
      <div className="flex-1 min-h-0">
        <ChatPanel />
      </div>
    </div>
  );
}
