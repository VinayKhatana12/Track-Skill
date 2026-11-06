"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

const TRIGGER_PX = 64;
const MAX_PULL_PX = 96;

/** Mobile pull-to-refresh for touch devices: pulling down at the top of the
 * page refreshes every dashboard query, with a haptic tick where supported.
 * Renders its children plus the fixed drag indicator. */
export function PullToRefresh({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef<number | null>(null);
  const startX = useRef<number>(0);
  const pulling = useRef(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await queryClient.invalidateQueries();
      // Give refetches a beat to land so the user sees new content.
      await new Promise((resolve) => setTimeout(resolve, 600));
    } finally {
      setRefreshing(false);
    }
  }, [queryClient]);

  useEffect(() => {
    const onTouchStart = (event: TouchEvent) => {
      if (event.touches.length !== 1) {
        return;
      }
      startY.current = event.touches[0].clientY;
      startX.current = event.touches[0].clientX;
      pulling.current = window.scrollY <= 0;
    };

    const onTouchMove = (event: TouchEvent) => {
      if (!pulling.current || startY.current === null || refreshing) {
        return;
      }
      const deltaY = event.touches[0].clientY - startY.current;
      const deltaX = event.touches[0].clientX - startX.current;
      // Only react to deliberate vertical drags.
      if (deltaY <= 0 || Math.abs(deltaX) > Math.abs(deltaY)) {
        setPull(0);
        return;
      }
      if (window.scrollY > 4) {
        pulling.current = false;
        setPull(0);
        return;
      }
      // Rubber-band resistance past the trigger point.
      const distance = deltaY > TRIGGER_PX ? TRIGGER_PX + (deltaY - TRIGGER_PX) * 0.25 : deltaY;
      setPull(Math.min(distance, MAX_PULL_PX));
    };

    const onTouchEnd = async () => {
      if (!pulling.current) {
        return;
      }
      startY.current = null;
      pulling.current = false;
      setPull((current) => {
        if (current >= TRIGGER_PX * 0.8) {
          navigator.vibrate?.(10);
          void refresh();
          return 0;
        }
        return 0;
      });
    };

    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchmove", onTouchMove, { passive: true });
    document.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      document.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
    };
  }, [refresh, refreshing]);

  const progress = refreshing || pull > 0;

  return (
    <>
      <div
        aria-hidden={!progress}
        className="pointer-events-none fixed inset-x-0 top-0 z-50 flex justify-center transition-opacity"
        style={{
          opacity: progress ? 1 : 0,
          transform: refreshing ? "translateY(12px)" : `translateY(${pull * 0.4}px)`,
        }}
      >
        <span className="mt-2 flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground shadow">
          <Loader2 className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} aria-hidden />
          {refreshing ? "Refreshing…" : pull >= TRIGGER_PX * 0.8 ? "Release to refresh" : "Pull to refresh"}
        </span>
      </div>
      {children}
    </>
  );
}
