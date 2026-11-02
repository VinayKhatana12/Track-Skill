"use client";

import { RefreshCw } from "lucide-react";

import { StatusIndicator, type StatusTone } from "@/components/status/status-indicator";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useHealth } from "@/hooks/use-health";
import { cn } from "@/lib/utils";

export function HealthCard() {
  const { data, isPending, isError, isFetching, refetch } = useHealth();

  const tone: StatusTone = isPending ? "connecting" : isError ? "offline" : "online";
  const headline = isPending ? "Checking" : isError ? "API unreachable" : "API online";

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>REST · FastAPI</CardTitle>
          <CardDescription>GET /health · polled every 15 seconds</CardDescription>
        </div>
        <StatusIndicator tone={tone} label={headline} />
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        {!isPending && !isError && data ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <div>
              <dt className="text-muted-foreground">Service</dt>
              <dd className="font-medium">{data.service}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Version</dt>
              <dd className="font-medium">{data.version}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Environment</dt>
              <dd className="font-medium capitalize">{data.environment}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Status</dt>
              <dd className="font-medium uppercase">{data.status}</dd>
            </div>
          </dl>
        ) : (
          <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
            {isPending
              ? "Waiting for the first response from the API…"
              : "The API did not answer. Start the stack with docker compose up, then retry."}
          </p>
        )}
        <div className="mt-auto">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} aria-hidden />
            Refresh now
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
