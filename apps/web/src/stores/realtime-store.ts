"use client";

import { create } from "zustand";

export interface RealtimeEvent {
  type: string;
  payload: Record<string, unknown>;
  at: number;
}

interface RealtimeState {
  connected: boolean;
  lastEvent: RealtimeEvent | null;
  setConnected: (connected: boolean) => void;
  record: (type: string, payload?: Record<string, unknown>) => void;
}

/** Tracks the live WebSocket connection and the most recent domain event so
 * cards can pulse when the data they show changes. */
export const useRealtimeStore = create<RealtimeState>((set) => ({
  connected: false,
  lastEvent: null,
  setConnected: (connected) => set({ connected }),
  record: (type, payload) => set({ lastEvent: { type, payload: payload ?? {}, at: Date.now() } }),
}));
