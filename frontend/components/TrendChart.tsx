"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SEVERITY_COLORS, SEVERITY_LABELS, EVENT_TYPE_LABELS } from "@/lib/utils";

const AXIS = { fontSize: 11, fill: "#71717a" };
const GRID = "rgba(0,0,0,0.07)";
const TOOLTIP_STYLE = {
  backgroundColor: "#ffffff",
  border: "1px solid rgba(0,0,0,0.12)",
  borderRadius: 12,
  fontSize: 12,
  color: "#18181b",
};

export function TrendChart({
  data,
}: {
  data: { date: string; [k: string]: string | number }[];
}) {
  if (!data.length) return <EmptyChart />;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data}>
        <defs>
          {Object.keys(data[0] ?? {}).filter((k) => k !== "date").map((k) => (
            <linearGradient key={k} id={`grad-${k}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#FACC15" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#FACC15" stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tick={AXIS} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={28} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        {Object.keys(data[0] ?? {}).filter((k) => k !== "date").map((k) => (
          <Area
            key={k}
            type="monotone"
            dataKey={k}
            stroke="#EAB308"
            fill={`url(#grad-${k})`}
            strokeWidth={2}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SeverityDonut({ bySeverity }: { bySeverity: Record<number, number> }) {
  const data = useMemo(
    () =>
      Object.entries(bySeverity)
        .map(([sev, count]) => ({
          name: SEVERITY_LABELS[Number(sev)] ?? `L${sev}`,
          value: count as number,
          color: SEVERITY_COLORS[Number(sev)] ?? "#94a3b8",
        }))
        .sort((a, b) => Number(a.value) - Number(b.value)),
    [bySeverity]
  );
  if (!data.length) return <EmptyChart />;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>
          {data.map((d) => (
            <Cell key={d.name} fill={d.color} />
          ))}
        </Pie>
        <Tooltip contentStyle={TOOLTIP_STYLE} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function TopRegionsBar({ data }: { data: { country: string; count: number }[] }) {
  if (!data.length) return <EmptyChart />;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} layout="vertical">
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis dataKey="country" type="category" width={90} tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={14}>
          {data.map((_, i) => (
            <Cell key={i} fill={i < 2 ? "#FACC15" : i < 5 ? "#EAB308" : "#C2410C"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ForecastChart({
  points,
}: {
  points: { ds: string; yhat: number; yhat_lower: number; yhat_upper: number }[];
}) {
  if (!points.length) return <EmptyChart />;
  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={points}>
        <defs>
          <linearGradient id="grad-fc" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FACC15" stopOpacity={0.4} />
            <stop offset="100%" stopColor="#FACC15" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="ds" tick={AXIS} tickLine={false} axisLine={false} minTickGap={32} tickFormatter={(v) => {
          const d = new Date(v);
          return `${d.getMonth() + 1}/${d.getDate()}`;
        }} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={30} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Area type="monotone" dataKey="yhat_upper" stroke="none" fill="rgba(234,179,8,0.12)" />
        <Area type="monotone" dataKey="yhat_lower" stroke="none" fill="rgba(234,179,8,0.12)" />
        <Area type="monotone" dataKey="yhat" stroke="#EAB308" strokeWidth={2.5} fill="url(#grad-fc)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function EmptyChart() {
  return (
    <div className="flex h-[260px] items-center justify-center text-sm text-zinc-400">
      No data yet
    </div>
  );
}

export { EVENT_TYPE_LABELS };