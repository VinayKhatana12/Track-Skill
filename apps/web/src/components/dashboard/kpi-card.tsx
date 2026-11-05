"use client";

import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Wraps a card and applies a visible 2-second pulse when a matching
 * realtime event arrives (Phase 9 realtime requirement). */
export function PulseCard({
  pulsing,
  children,
  className,
}: {
  pulsing: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl transition-shadow duration-700",
        pulsing && "realtime-pulse",
        className,
      )}
      data-pulsing={pulsing || undefined}
    >
      {children}
    </div>
  );
}

export function KpiCard({
  icon: Icon,
  label,
  value,
  hint,
  pulsing,
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  hint?: string;
  pulsing?: boolean;
}) {
  return (
    <PulseCard pulsing={Boolean(pulsing)} className="h-full">
      <Card className="h-full">
        <CardContent className="flex items-center justify-between gap-3 pt-6">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {label}
            </p>
            <p className="mt-1 font-display text-3xl font-semibold" aria-label={String(value)}>
              {value}
            </p>
            {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
          </div>
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary">
            <Icon className="h-5 w-5" aria-hidden />
          </span>
        </CardContent>
      </Card>
    </PulseCard>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  hint,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border p-6 text-center">
      <Icon className="h-6 w-6 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
