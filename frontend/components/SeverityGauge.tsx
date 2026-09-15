"use client";

import { SEVERITY_COLORS, SEVERITY_LABELS } from "@/lib/utils";

export default function SeverityGauge({
  severity,
  size = 140,
}: {
  severity: number;
  size?: number;
}) {
  const clamped = Math.max(1, Math.min(5, severity));
  const color = SEVERITY_COLORS[clamped] ?? "#94a3b8";
  const stroke = 12;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (clamped - 1) / 4;

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(0,0,0,0.08)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - progress)}
          style={{ transition: "stroke-dashoffset 0.8s ease, stroke 0.4s ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold" style={{ color }}>
          {clamped}
        </span>
        <span className="text-[11px] font-semibold tracking-widest text-zinc-500">
          {SEVERITY_LABELS[clamped]}
        </span>
      </div>
    </div>
  );
}