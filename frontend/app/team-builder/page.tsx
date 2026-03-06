"use client";

import { useRouter } from "next/navigation";
import { TeamBuilderChat } from "@/components/chat/TeamBuilderChat";

export default function TeamBuilderPage() {
  const router = useRouter();

  return (
    <div className="h-screen flex flex-col">
      <div className="px-8 py-4 border-b bg-white">
        <h1 className="text-xl font-bold text-slate-900">Construire une équipe</h1>
        <p className="text-sm text-slate-500">
          Discutez avec Alex pour définir votre équipe d&apos;agents idéale.
        </p>
      </div>
      <div className="flex-1 overflow-hidden">
        <TeamBuilderChat
          onTeamCreated={() => {
            setTimeout(() => router.push("/team"), 2000);
          }}
        />
      </div>
    </div>
  );
}
