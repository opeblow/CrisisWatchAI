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
        color: color || "#52525b",
        backgroundColor: color ? `${color}22` : "rgba(250,204,21,0.2)",
        border: `1px solid ${color ? `${color}55` : "rgba(250,204,21,0.4)"}`,
      }}
    >
      {children}
    </span>
  );
}