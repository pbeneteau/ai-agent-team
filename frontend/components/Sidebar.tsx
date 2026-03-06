"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  MessageSquare,
  Users,
  ListTodo,
  Sparkles,
  Zap,
  BarChart2,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface UsageSummary {
  today: { input_tokens: number; output_tokens: number; cost_usd: number };
  total: { input_tokens: number; output_tokens: number; cost_usd: number; calls: number };
}

const NAV_ITEMS = [
  { href: "/", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/chat", icon: MessageSquare, label: "Chat avec Alex" },
  { href: "/team", icon: Users, label: "Mon Équipe" },
  { href: "/tasks", icon: ListTodo, label: "Tâches" },
  { href: "/usage", icon: BarChart2, label: "Usage & Coûts" },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export function Sidebar() {
  const pathname = usePathname();
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  useEffect(() => {
    const load = () =>
      fetch(`${API_BASE}/usage/`)
        .then((r) => r.json())
        .then(setUsage)
        .catch(() => {});
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <aside className="w-64 bg-slate-900 text-white flex flex-col h-screen sticky top-0">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <p className="font-bold text-sm">AgentTeam</p>
            <p className="text-[10px] text-slate-400">Votre équipe IA</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                isActive
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-white hover:bg-slate-800"
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Usage monitor */}
      <div className="px-4 py-3 border-t border-slate-800 space-y-2">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
          <Zap className="w-3 h-3" />
          Coût estimé
        </div>
        {usage ? (
          <div className="space-y-1.5">
            <div className="flex justify-between text-[11px]">
              <span className="text-slate-400">Aujourd&apos;hui</span>
              <span className={cn(
                "font-mono font-medium",
                usage.today.cost_usd > 1 ? "text-amber-400" : "text-green-400"
              )}>
                ${usage.today.cost_usd.toFixed(4)}
              </span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-slate-400">Total</span>
              <span className="font-mono font-medium text-slate-300">
                ${usage.total.cost_usd.toFixed(4)}
              </span>
            </div>
            <div className="text-[10px] text-slate-600">
              {usage.total.calls} appel{usage.total.calls !== 1 ? "s" : ""} · {((usage.total.input_tokens + usage.total.output_tokens) / 1000).toFixed(1)}K tokens
            </div>
          </div>
        ) : (
          <p className="text-[11px] text-slate-600">—</p>
        )}
        <p className="text-[9px] text-slate-700 leading-tight">
          Estimation basée sur les tarifs Anthropic officiels. Sans crédits de cache.
        </p>
      </div>
    </aside>
  );
}
