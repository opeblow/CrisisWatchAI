import { cn } from "@/lib/utils";
import * as React from "react";

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "outline" | "danger";
  size?: "sm" | "md" | "lg";
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-all disabled:opacity-50 disabled:pointer-events-none",
        size === "sm" && "px-3 py-1.5 text-xs",
        size === "md" && "px-4 py-2 text-sm",
        size === "lg" && "px-6 py-3 text-base",
        variant === "primary" &&
          "bg-blue-500 text-white hover:bg-blue-400 shadow-lg shadow-blue-500/25",
        variant === "ghost" && "bg-transparent text-slate-300 hover:bg-white/10",
        variant === "outline" &&
          "border border-white/15 text-slate-200 hover:bg-white/10",
        variant === "danger" && "bg-red-500/90 text-white hover:bg-red-400",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}