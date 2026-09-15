import { cn } from "@/lib/utils";
import * as React from "react";

export function Badge({
  children,
  color,
  className,
}: {
  children: React.ReactNode;
  color?: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide",
        className
      )}
      style={{
        color: color || "#e2e8f0",
        backgroundColor: color ? `${color}22` : "rgba(255,255,255,0.08)",
        border: `1px solid ${color ? `${color}55` : "rgba(255,255,255,0.12)"}`,
      }}
    >
      {children}
    </span>
  );
}