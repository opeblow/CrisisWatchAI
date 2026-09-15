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
          "bg-gold text-black hover:bg-lemon shadow-sm shadow-yellow-500/30",
        variant === "ghost" && "bg-transparent text-zinc-600 hover:bg-zinc-100",
        variant === "outline" &&
          "border border-zinc-300 text-zinc-700 hover:border-yellow-500 hover:text-yellow-700",
        variant === "danger" && "bg-gold text-black hover:bg-lemon",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}