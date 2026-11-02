import { useCallback, useEffect, useRef, useState } from "react";

import { getWsUrl } from "@/lib/api";
import type { RealtimeEvent, RealtimeStatus } from "@/types/api";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 15_000;
const PING_INTERVAL_MS = 30_000;
const EVENT_HISTORY_LIMIT = 8;

export interface RealtimeEventWithId {
  id: number;
  event: RealtimeEvent;
}

/**
 * Connects to the /ws gateway on a channel and keeps the connection alive:
 * exponential-backoff reconnects, a heartbeat ping, and a short history of
 * received events (heartbeat pongs excluded).
 */
export function useRealtime(channel = "global") {
  const [status, setStatus] = useState<RealtimeStatus>("connecting");
  const [events, setEvents] = useState<RealtimeEventWithId[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);
  const eventIdRef = useRef(0);

  const send = useCallback((eventName: string, payload: Record<string, unknown> = {}) => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ event: eventName, payload }));
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let pingTimer: ReturnType<typeof setInterval> | null = null;

    const clearTimers = () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (pingTimer) {
        clearInterval(pingTimer);
        pingTimer = null;
      }
    };

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");

      const socket = new WebSocket(getWsUrl(channel));
      socketRef.current = socket;

      socket.onopen = () => {
        attemptsRef.current = 0;
        setStatus("online");
        pingTimer = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ event: "ping", payload: {} }));
          }
        }, PING_INTERVAL_MS);
      };

      socket.onmessage = (message: MessageEvent<string>) => {
        try {
          const parsed = JSON.parse(message.data) as RealtimeEvent;
          if (parsed.event === "pong") return;
          eventIdRef.current += 1;
          const entry: RealtimeEventWithId = { id: eventIdRef.current, event: parsed };
          setEvents((previous) => [entry, ...previous].slice(0, EVENT_HISTORY_LIMIT));
        } catch {
          // The server only sends JSON frames; ignore anything else.
        }
      };

      socket.onclose = () => {
        if (disposed) return;
        setStatus("offline");
        clearTimers();
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attemptsRef.current, RECONNECT_MAX_MS);
        attemptsRef.current += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      disposed = true;
      clearTimers();
      const socket = socketRef.current;
      if (socket) {
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
        socket.close();
        socketRef.current = null;
      }
    };
  }, [channel]);

  return { status, events, send };
}
