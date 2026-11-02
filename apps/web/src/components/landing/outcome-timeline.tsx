"use client";

import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import { useRef, useState } from "react";

import { useCountUp } from "@/hooks/use-count-up";
import { cn } from "@/lib/utils";

const STAGES = [
  {
    key: "m3",
    label: "3 months",
    title: "Placed & confirmed",
    detail: "Tracer goes out on WhatsApp/IVR. The job claim is verified by the employer.",
    counter: { target: 78, suffix: "%", label: "respond within the first week" },
  },
  {
    key: "m6",
    label: "6 months",
    title: "Retention checked",
    detail: "Wage growth and retention are re-confirmed and weighted into the centre's PPI.",
    counter: { target: 71, suffix: "%", label: "still employed at six months" },
  },
  {
    key: "m12",
    label: "12 months",
    title: "Outcome certified",
    detail: "Dual-signal confirmation locks the outcome in; fund allocation follows the evidence.",
    counter: { target: 64, suffix: "%", label: "sustained outcomes after a year" },
  },
] as const;

/** Animated 3/6/12-month outcome timeline for the hero. Hover or focus a
 * stage to expand it; counters animate in view. Honours reduced motion. */
export function OutcomeTimeline() {
  const reduceMotion = useReducedMotion() ?? false;
  const sectionRef = useRef<HTMLDivElement>(null);
  const inView = useInView(sectionRef, { once: true, amount: 0.4 });
  const [activeKey, setActiveKey] = useState<string>("m3");

  return (
    <div
      ref={sectionRef}
      className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm sm:p-8"
      aria-label="Animated 3, 6 and 12 month outcome timeline"
    >
      <div className="relative flex items-start justify-between gap-2 sm:gap-4">
        <span aria-hidden className="absolute left-2 right-2 top-5 hidden h-0.5 bg-border sm:block" />
        {STAGES.map((stage, index) => {
          const active = activeKey === stage.key;
          return (
            <motion.button
              key={stage.key}
              type="button"
              initial={reduceMotion ? undefined : { opacity: 0, y: 14 }}
              animate={inView || reduceMotion ? { opacity: 1, y: 0 } : undefined}
              transition={{ delay: reduceMotion ? 0 : 0.15 * index, duration: 0.5 }}
              onMouseEnter={() => setActiveKey(stage.key)}
              onFocus={() => setActiveKey(stage.key)}
              onClick={() => setActiveKey(stage.key)}
              aria-pressed={active}
              className={cn(
                "relative z-10 flex flex-1 cursor-pointer flex-col items-center gap-2 rounded-lg px-1 pb-2 pt-1 text-center outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active && "bg-secondary/60",
              )}
            >
              <span
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-full border-2 font-display text-xs font-semibold transition-colors",
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-muted-foreground",
                )}
              >
                {stage.label === "3 months" ? "M3" : stage.label === "6 months" ? "M6" : "M12"}
              </span>
              <span className="text-xs font-medium sm:text-sm">{stage.label}</span>
            </motion.button>
          );
        })}
      </div>

      <AnimatePresence mode="wait" initial={false}>
        {STAGES.filter((stage) => stage.key === activeKey).map((stage) => (
          <motion.div
            key={stage.key}
            initial={reduceMotion ? undefined : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: reduceMotion ? 0 : 0.25 }}
            className="mt-6 grid gap-4 sm:grid-cols-[1fr_auto] sm:items-center"
          >
            <div>
              <p className="font-display text-lg font-semibold">{stage.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{stage.detail}</p>
            </div>
            <StageCounter
              target={stage.counter.target}
              suffix={stage.counter.suffix}
              label={stage.counter.label}
              active={inView}
              reduceMotion={reduceMotion}
            />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function StageCounter({
  target,
  suffix,
  label,
  active,
  reduceMotion,
}: {
  target: number;
  suffix: string;
  label: string;
  active: boolean;
  reduceMotion: boolean;
}) {
  const value = useCountUp(target, active, { reducedMotion: reduceMotion });
  return (
    <div className="rounded-xl border border-border/70 bg-background px-5 py-4 text-center">
      <p className="font-display text-3xl font-semibold text-primary" aria-label={`${value}${suffix}`}>
        {value}
        {suffix}
      </p>
      <p className="mt-1 max-w-[12rem] text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
