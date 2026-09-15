"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Bell, BellOff, Check, Filter, Loader2, MapPin, Play } from "lucide-react";
import Card, { CardContent, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import Skeleton from "@/components/ui/Skeleton";
import { getAlerts, markAlertRead } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import type { AlertItem } from "@/lib/types";

const FILTERS = [
  { value: "all", label: "All alerts" },
  { value: "unread", label: "Unread only" },
  { value: "severe", label: "Severity 4+" },
];

const TIMERANGE = [
  { value: "100", label: "Latest 100" },
  { value: "50", label: "Latest 50" },
  { value: "20", label: "Latest 20" },
];

export default function AlertsPage() {
  const [filter, setFilter] = useState("all");
  const [limit, setLimit] = useState("100");
  const qc = useQueryClient();

  const params: Record<string, string | number> = { limit: Number(limit) };
  if (filter === "unread") params.unread_only = 1;
  if (filter === "severe") params.severity_min = 4;

  const { data, isLoading } = useQuery({
    queryKey: ["alerts", params],
    queryFn: () => getAlerts(params),
    refetchInterval: 30_000,
  });

  const markAsRead = useMutation({
    mutationFn: markAlertRead,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const alerts = data?.alerts ?? [];

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-zinc-900">
            <Bell className="h-6 w-6 text-yellow-600" /> Crisis Alerts
{data && data.unread_count > 0 && (
              <Badge color="#FACC15">{data.unread_count} unread</Badge>
            )}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Every alert is auto-generated the moment an event crosses the severity threshold —
            ranked by urgency.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={filter} onChange={setFilter} options={FILTERS} className="w-40" label="" />
          <Select value={limit} onChange={setLimit} options={TIMERANGE} className="w-36" label="" />
        </div>
      </div>

      <Card>
        <CardHeader title="Alert Feed" subtitle="Priority-sorted · severity 4+ flagged" />
        <CardContent className="space-y-2">
          {isLoading ? (
            Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20" />)
          ) : alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-14 text-zinc-500">
              <BellOff className="h-10 w-10" />
              <p className="text-sm">No alerts match this filter.</p>
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  await fetch("/api/alerts?threshold=4", { method: "POST" });
                  qc.invalidateQueries({ queryKey: ["alerts"] });
                }}
              >
                <Play className="h-4 w-4" /> Re-scan events for alerts
              </Button>
            </div>
          ) : (
            alerts.map((alert, i) => (
              <motion.div
                key={alert.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className={`rounded-xl border p-4 transition-colors ${
                  !alert.is_read
                    ? "border-gold/30 bg-gold/[0.06]"
                    : "border-zinc-200 bg-zinc-50"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {!alert.is_read && (
                        <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-yellow-600">
                          <span className="relative flex h-1.5 w-1.5">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-yellow-500 opacity-75" />
                            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-yellow-500" />
                          </span>
                          New
                        </span>
                      )}
                      <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                        {alert.event?.event_type}
                      </span>
                      <Badge color={alert.severity_color}>{alert.severity_label}</Badge>
                      <span className="ml-auto text-xs text-zinc-500">
                        {timeAgo(alert.created_at)}
                      </span>
                    </div>
                    <p className="mt-1.5 text-sm font-medium text-zinc-900">{alert.message}</p>
                    {alert.event && (
                      <div className="mt-1.5 flex items-center gap-3 text-xs text-zinc-500">
                        <span className="flex items-center gap-1">
                          <MapPin className="h-3 w-3" />
                          {alert.event.country ?? "—"}
                          {alert.event.region ? ` · ${alert.event.region}` : ""}
                        </span>
                        {alert.event.latitude != null && (
                          <span className="font-mono">
                            {alert.event.latitude.toFixed(2)}, {alert.event.longitude?.toFixed(2)}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  {!alert.is_read && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => markAsRead.mutate(alert.id)}
                      disabled={markAsRead.isPending}
                      className="shrink-0"
                    >
                      {markAsRead.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Check className="h-3.5 w-3.5" />
                      )}
                      Mark read
                    </Button>
                  )}
                </div>
              </motion.div>
            ))
          )}
        </CardContent>
      </Card>

      <div className="flex items-center gap-2 pb-4 text-xs text-zinc-500">
        <Filter className="h-3.5 w-3.5" />
        Alert pipeline: ingestion → severity scoring → threshold trigger → priority queue. Unread
        alerts auto-refresh every 30 seconds.
      </div>
    </div>
  );
}