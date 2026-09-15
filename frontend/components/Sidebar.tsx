"use client";

import { Activity, FileText, LayoutDashboard, Radar, Bell } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/predictions", label: "Predictions", icon: Radar },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/reports", label: "Reports", icon: FileText },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-zinc-200 bg-white">
      <div className="flex h-16 items-center gap-3 border-b border-zinc-200 px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gold/75 text-black">
          <Activity className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-bold tracking-tight text-zinc-900">CrisisWatch AI</div>
          <div className="text-[10px] uppercase tracking-widest text-zinc-500">
            Global Intelligence
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-gold/75 text-black"
                  : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-zinc-200 p-4">
        <div className="flex items-center gap-2 rounded-lg bg-zinc-50 px-3 py-3">
          <div className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-yellow-500 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-yellow-500" />
          </div>
          <div className="text-xs">
            <div className="font-semibold text-zinc-800">Systems Live</div>
            <div className="text-zinc-500">Real-time feeds active</div>
          </div>
        </div>
      </div>
    </aside>
  );
}