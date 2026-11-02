"use client";

import { motion, useInView, useReducedMotion } from "framer-motion";
import { FileWarning, SearchCheck, TrendingUp } from "lucide-react";
import { useRef } from "react";

import { useCountUp } from "@/hooks/use-count-up";
import { Card, CardContent } from "@/components/ui/card";

const PROBLEMS = [
  {
    icon: FileWarning,
    stat: 68,
    suffix: "%",
    title: "Outcomes go unrecorded",
    body: "Most skilling programs stop tracking the day a certificate is handed over. Job retention, wage growth and self-employment disappear from view.",
  },
  {
    icon: SearchCheck,
    stat: 2,
    suffix: "×",
    title: "Funding flies blind",
    body: "Without verified outcome data, fund allocation rewards marketing, not results — and the same gaps repeat every batch.",
  },
  {
    icon: TrendingUp,
    stat: 40,
    suffix: "%",
    title: "Curricula drift from demand",
    body: "Courses keep teaching yesterday's skills. Employers keep posting jobs the programs never trained for.",
  },
] as const;

export function ProblemSolution() {
  const reduceMotion = useReducedMotion() ?? false;
  const sectionRef = useRef<HTMLDivElement>(null);
  const inView = useInView(sectionRef, { once: true, amount: 0.3 });

  return (
    <section
      id="impact"
      aria-labelledby="impact-heading"
      className="scroll-mt-20 border-y border-border/70 bg-muted/40 py-16 md:py-20"
    >
      <div ref={sectionRef} className="container">
        <div className="mb-10 max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
            Problem → Solution
          </p>
          <h2
            id="impact-heading"
            className="mt-2 font-display text-3xl font-semibold tracking-tight"
          >
            The blind spot ends where evidence begins
          </h2>
          <p className="mt-3 text-muted-foreground">
            TrackSkill AI keeps asking, checking and publishing after certification — so the
            numbers below become counts, not anecdotes.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {PROBLEMS.map((problem, index) => (
            <ProblemCard
              key={problem.title}
              problem={problem}
              active={inView}
              reduceMotion={reduceMotion}
              index={index}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function ProblemCard({
  problem,
  active,
  reduceMotion,
  index,
}: {
  problem: (typeof PROBLEMS)[number];
  active: boolean;
  reduceMotion: boolean;
  index: number;
}) {
  const value = useCountUp(problem.stat, active, { reducedMotion: reduceMotion });
  const Icon = problem.icon;

  return (
    <motion.div
      initial={reduceMotion ? undefined : { opacity: 0, y: 18 }}
      whileInView={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ delay: 0.1 * index, duration: 0.45 }}
    >
      <Card className="h-full">
        <CardContent className="pt-6">
          <div className="flex items-baseline justify-between">
            <span
              className="font-display text-4xl font-semibold text-primary"
              aria-label={`${problem.stat}${problem.suffix} (sample data)`}
            >
              {value}
              {problem.suffix}
            </span>
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary text-primary">
              <Icon className="h-5 w-5" aria-hidden />
            </span>
          </div>
          <h3 className="mt-3 font-display text-lg font-semibold">{problem.title}</h3>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{problem.body}</p>
          <p className="mt-3 text-[11px] italic text-muted-foreground">
            Illustrative figures based on published sector studies — sample data.
          </p>
        </CardContent>
      </Card>
    </motion.div>
  );
}
