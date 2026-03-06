"use client";

import { WsEventProvider } from "@/lib/ws-context";

export function Providers({ children }: { children: React.ReactNode }) {
  return <WsEventProvider>{children}</WsEventProvider>;
}
