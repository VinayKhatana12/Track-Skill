"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { API_URL, ensureFreshToken, getAccessToken } from "@/lib/api";
import { useRealtimeStore } from "@/stores/realtime-store";

/** Opens the authenticated realtime socket, feeds every domain event into
 * the pulse store and invalidates React Query caches so all dashboards
 * refresh without a page reload. */
export function useRealtimeConnection(active: boolean) {
  const queryClient = useQueryClient();
  const setConnected = useRealtimeStore((state) => state.setConnected);
  const record = useRealtimeStore((state) => state.record);
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  useEffect(() => {
    if (!active) {
      return;
    }
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;

    const connect = () => {
      const token = getAccessToken();
      const wsUrl = `${API_URL.replace(/^http/, "ws")}/ws${
        token ? `?token=${encodeURIComponent(token)}` : ""
      }`;
      socket = new WebSocket(wsUrl);

      socket.onopen = () => setConnected(true);

      socket.onmessage = (message) => {
        try {
          const data = JSON.parse(message.data) as {
            event?: string;
            payload?: Record<string, unknown>;
          };
          if (data.event && data.event !== "pong" && data.event !== "connection.established") {
            record(data.event, data.payload);
            void queryClientRef.current.invalidateQueries();
          }
        } catch {
          // non-JSON frame — ignore
        }
      };

      socket.onclose = (closeEvent) => {
        setConnected(false);
        if (disposed) {
          return;
        }
        const wasAuthFailure = closeEvent.code === 4401;
        const delay = wasAuthFailure ? 300 : 3000;
        retryTimer = window.setTimeout(async () => {
          if (wasAuthFailure) {
            await ensureFreshToken();
          }
          connect();
        }, delay);
      };
    };

    void (async () => {
      await ensureFreshToken();
      if (!disposed) {
        connect();
      }
    })();

    return () => {
      disposed = true;
      if (retryTimer) {
        window.clearTimeout(retryTimer);
      }
      socket?.close();
      setConnected(false);
    };
  }, [active, setConnected, record]);
}
