import { Badge } from "@/components/ui/Badge";
import { SEVERITY_COLORS, EVENT_TYPE_LABELS, timeAgo, formatNumber } from "@/lib/utils";
import type { CrisisEvent } from "@/lib/types";

export default function CrisisCard({ event }: { event: CrisisEvent }) {
  const color = SEVERITY_COLORS[event.severity] ?? "#94a3b8";
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 transition-colors hover:border-white/20">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: color }}
          />
          <span className="text-slate-400">{EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}</span>
          <Badge color={color}>{event.severity_label}</Badge>
        </div>
        <span className="text-xs text-slate-500">{timeAgo(event.timestamp)}</span>
      </div>
      <h4 className="mt-2 text-sm font-semibold text-white">{event.title}</h4>
      <p className="mt-1 line-clamp-2 text-xs text-slate-400">{event.description}</p>
      <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
        <span>
          {event.region}, {event.country}
        </span>
        <span className="font-mono">
          {formatNumber(event.affected)} affected
        </span>
      </div>
    </div>
  );
}