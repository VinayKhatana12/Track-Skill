"use client";

import { cn } from "@/lib/utils";

export function ConnectionPill({ connected }: { connected: boolean }) {
  return (
    <span
      role="status"
      aria-label={connected ? "Realtime connection live" : "Realtime connection offline"}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
        connected
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "h-2 w-2 rounded-full",
          connected ? "animate-pulse bg-emerald-500" : "bg-red-500",
        )}
      />
      {connected ? "Live" : "Offline"}
    </span>
  );
}
