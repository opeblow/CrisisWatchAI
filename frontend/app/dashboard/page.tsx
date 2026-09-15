"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Card, { CardContent, CardHeader } from "@/components/ui/Card";
import Skeleton from "@/components/ui/Skeleton";
import CrisisMap from "@/components/CrisisMap";
import StatsOverview from "@/components/StatsOverview";
import CrisisCard from "@/components/CrisisCard";
import { TrendChart, SeverityDonut, TopRegionsBar } from "@/components/TrendChart";
import { Select } from "@/components/ui/Select";
import { getCrises, getStats } from "@/lib/api";
import { EVENT_TYPE_LABELS } from "@/lib/utils";

const TYPE_OPTIONS = [
  { value: "all", label: "All Types" },
  ...Object.entries(EVENT_TYPE_LABELS).map(([value, label]) => ({ value, label })),
];

function buildTrend(events: { timestamp: string | null; event_type: string }[], events30: { timestamp: string | null; event_type: string }[]) {
  const buckets: Record<string, Record<string, number>> = {};
  const source = events30.length >= 20 ? events30 : events.slice(0, 250);
  for (const e of source) {
    if (!e.timestamp) continue;
    const d = new Date(e.timestamp);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    buckets[key] ??= {};
    buckets[key][EVENT_TYPE_LABELS[e.event_type] ?? e.event_type] =
      (buckets[key][EVENT_TYPE_LABELS[e.event_type] ?? e.event_type] ?? 0) + 1;
  }
  return Object.entries(buckets)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, types]) => ({ date: date.slice(5), ...types }));
}

export default function DashboardPage() {
  const [type, setType] = useState("all");
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: getStats });
  const { data: crises, isLoading } = useQuery({
    queryKey: ["crises", 500],
    queryFn: () => getCrises({ limit: 500 }),
  });
  const { data: recent } = useQuery({
    queryKey: ["crises-recent"],
    queryFn: () => getCrises({ limit: 40 }),
  });

  const filtered = useMemo(() => {
    const all = crises?.events ?? [];
    return type === "all" ? all : all.filter((e) => e.event_type === type);
  }, [crises, type]);

  const trend = useMemo(
    () => buildTrend(crises?.events ?? [], recent?.events ?? []),
    [crises, recent]
  );

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900">Crisis Dashboard</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Live global situation awareness across all active disasters, outbreaks and conflicts.
          </p>
        </div>
        <Select
          value={type}
          onChange={setType}
          options={TYPE_OPTIONS}
          label="Crisis type"
          className="w-48"
        />
      </div>

      <StatsOverview />

      <Card className="overflow-hidden">
        <CardHeader title="Live Crisis Map" subtitle="Severity-coded events · click markers for details" />
        <CardContent className="p-0">
          {isLoading ? (
            <Skeleton className="m-4 h-[440px]" />
          ) : (
            <CrisisMap events={filtered} height="h-[440px]" />
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Events Over Time" subtitle="Last 30 days by type" />
          <CardContent>
            <TrendChart data={trend} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader title="Severity Distribution" subtitle="Unified 1–5 risk scale" />
          <CardContent>
            <SeverityDonut bySeverity={stats?.by_severity ?? {}} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader title="Most Affected Countries" subtitle="By event count" />
          <CardContent>
            <TopRegionsBar data={(stats?.top_countries ?? []).slice(0, 8)} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader title="Latest Crisis Events" subtitle="Most recent first" />
        <CardContent>
          {isLoading ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-36" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {(recent?.events ?? []).slice(0, 12).map((e) => (
                <CrisisCard key={e.id} event={e} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}