"use client";

import { useEffect, useState } from "react";

import { useRealtimeStore } from "@/stores/realtime-store";

/** True for ~2 seconds after any of the given event types arrives over the
 * realtime socket. Wrap a card and apply a visible pulse class. */
export function usePulse(...types: string[]): boolean {
  const lastEvent = useRealtimeStore((state) => state.lastEvent);
  const [pulsing, setPulsing] = useState(false);
  const typesKey = types.join("|");

  useEffect(() => {
    if (!lastEvent || !typesKey.split("|").includes(lastEvent.type)) {
      return;
    }
    setPulsing(true);
    const timer = setTimeout(() => setPulsing(false), 2000);
    return () => clearTimeout(timer);
  }, [lastEvent, typesKey]);

  return pulsing;
}
