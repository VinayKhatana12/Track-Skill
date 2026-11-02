"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, RadioTower } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { runTracerNow } from "@/lib/api";
import { ApiError } from "@/lib/api";

export function TracerPanel() {
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: runTracerNow,
    onSuccess: (result) => {
      setError(null);
      const delivered = result.sent
        .map((item) => `${item.milestone} → ${item.trainee_name}`)
        .join(", ");
      setSummary(
        `Delivered ${result.sent_count} tracer(s) now: ${delivered || "none due"}. ` +
          `Created ${result.created}, fast-forwarded ${result.fast_forwarded}, missed ${result.missed_count}.`,
      );
    },
    onError: (mutationError) => {
      setSummary(null);
      setError(
        mutationError instanceof ApiError && mutationError.status === 404
          ? "The tracer demo control is disabled while DEMO_MODE is off."
          : "Could not run the tracer cycle. Please try again.",
      );
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl">Tracer demo control</CardTitle>
        <CardDescription>
          Fast-forwards demo follow-ups to today and delivers them instantly.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <RadioTower className="h-4 w-4" aria-hidden />
          )}
          Run tracer now
        </Button>
        {summary && (
          <p role="status" className="rounded-md bg-secondary px-3 py-2 text-sm text-secondary-foreground">
            {summary}
          </p>
        )}
        {error && (
          <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
