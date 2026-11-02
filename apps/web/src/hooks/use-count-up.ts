"use client";

import { useEffect, useState } from "react";

/** Animates a number from 0 to `target` once `active` turns true.
 * Respects prefers-reduced-motion by jumping straight to the target. */
export function useCountUp(
  target: number,
  active: boolean,
  {
    durationMs = 1400,
    reducedMotion = false,
    decimals = 0,
  }: { durationMs?: number; reducedMotion?: boolean; decimals?: number } = {},
): number {
  const [value, setValue] = useState(reducedMotion ? target : 0);

  useEffect(() => {
    if (!active) {
      return;
    }
    if (reducedMotion) {
      setValue(target);
      return;
    }
    let frame: number;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = target * eased;
      setValue(decimals > 0 ? Number(current.toFixed(decimals)) : Math.round(current));
      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, target, durationMs, reducedMotion, decimals]);

  return value;
}
