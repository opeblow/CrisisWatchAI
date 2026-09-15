"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Users, Globe, AlertTriangle } from "lucide-react";
import Card from "@/components/ui/Card";
import Skeleton from "@/components/ui/Skeleton";
import { getStats } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

export default function StatsOverview() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["stats"], queryFn: getStats });

  const stats = [
    {
      label: "Active Crises",
      value: data ? formatNumber(data.active_last_30d) : null,
      sub: data ? `${data.total_events} total tracked` : null,
      icon: Activity,
      color: "#3b82f6",
    },
    {
      label: "Critical Alerts",
      value: data ? formatNumber(data.critical_ongoing) : null,
      sub: "Severity ≥ 4 · recent",
      icon: AlertTriangle,
      color: "#ef4444",
    },
    {
      label: "Countries Impacted",
      value: data ? formatNumber(data.countries_impacted) : null,
      sub: "Across all regions",
      icon: Globe,
      color: "#22c55e",
    },
    {
      label: "Events by Type",
      value: data ? Object.keys(data.by_type ?? {}).length : null,
      sub: "8 crisis categories",
      icon: Users,
      color: "#f59e0b",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {stats.map((s) => {
        const Icon = s.icon;
        return (
          <Card key={s.label} className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-xs font-medium uppercase tracking-wider text-slate-500">
                  {s.label}
                </div>
                {isLoading ? (
                  <Skeleton className="mt-2 h-8 w-16" />
                ) : isError ? (
                  <div className="mt-2 text-2xl font-bold text-slate-600">—</div>
                ) : (
                  <div className="mt-2 text-3xl font-bold text-white">{s.value}</div>
                )}
                <div className="mt-1 text-xs text-slate-500">{s.sub}</div>
              </div>
              <div
                className="flex h-10 w-10 items-center justify-center rounded-xl"
                style={{ backgroundColor: `${s.color}1a`, color: s.color }}
              >
                <Icon className="h-5 w-5" />
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}