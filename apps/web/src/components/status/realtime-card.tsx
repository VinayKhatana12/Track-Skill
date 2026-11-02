"use client";

import { SendHorizonal } from "lucide-react";
import { useState, type FormEvent } from "react";

import { StatusIndicator, type StatusTone } from "@/components/status/status-indicator";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useRealtime } from "@/hooks/use-realtime";

export function RealtimeCard() {
  const { status, events, send } = useRealtime("global");
  const [draft, setDraft] = useState("");

  const tone: StatusTone =
    status === "online" ? "online" : status === "offline" ? "offline" : "connecting";

  const handleBroadcast = (formEvent: FormEvent<HTMLFormElement>) => {
    formEvent.preventDefault();
    const message = draft.trim();
    if (!message) return;
    send("announcement", { message, source: "landing-demo" });
    setDraft("");
  };

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>Realtime · WebSocket</CardTitle>
          <CardDescription>Channel: global — broadcast from any tab</CardDescription>
        </div>
        <StatusIndicator tone={tone} />
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <form onSubmit={handleBroadcast} className="flex gap-2" aria-label="Broadcast a test event">
          <Input
            value={draft}
            onChange={(inputEvent) => setDraft(inputEvent.target.value)}
            placeholder="Type an update and press Broadcast…"
            aria-label="Message to broadcast"
            maxLength={140}
          />
          <Button type="submit" disabled={status !== "online" || !draft.trim()}>
            <SendHorizonal className="h-4 w-4" aria-hidden />
            Broadcast
          </Button>
        </form>

        <div className="flex-1">
          <h3 className="mb-2 text-sm font-semibold text-muted-foreground">Recent events</h3>
          {events.length === 0 ? (
            <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
              No events yet. Broadcast one here, or open this page in a second tab and broadcast
              from there.
            </p>
          ) : (
            <ul className="space-y-2">
              {events.map(({ id, event }) => (
                <li
                  key={id}
                  className="rounded-md border border-border/70 bg-muted/40 px-3 py-2 text-sm"
                >
                  <span className="font-mono text-xs font-semibold text-primary">
                    {event.event}
                  </span>
                  <span className="ml-2 break-all font-mono text-xs text-muted-foreground">
                    {JSON.stringify(event.payload)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
