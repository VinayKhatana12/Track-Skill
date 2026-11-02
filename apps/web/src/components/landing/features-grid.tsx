"use client";

import { motion, useReducedMotion } from "framer-motion";
import { BrainCircuit, Radar, ShieldCheck } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const FEATURES = [
  {
    icon: Radar,
    objective: "Objective 1 — Outcome tracking",
    title: "3/6/12-month outcome tracing",
    bullets: [
      "Consent-based digital profiles per trainee",
      "Simulated WhatsApp / IVR / SMS tracers with retries and expiry",
      "Free-text replies parsed into structured outcomes with confidence",
    ],
  },
  {
    icon: ShieldCheck,
    objective: "Objective 1 — Verification",
    title: "Dual-signal verification",
    bullets: [
      "Trainee self-report + employer confirmation must both say CONFIRMED",
      "Unverified outcomes count at half weight in analytics",
      "Manual review queue for low-confidence replies",
    ],
  },
  {
    icon: BrainCircuit,
    objective: "Objective 2 — AI matching",
    title: "Skills & curriculum intelligence",
    bullets: [
      "Skill profile with per-skill confidence against a 60-skill taxonomy",
      "Top-5 job-role matches with traceable explanations",
      "Per-course curriculum-demand gaps with suggested modules",
    ],
  },
] as const;

export function FeaturesGrid() {
  const reduceMotion = useReducedMotion() ?? false;

  return (
    <section id="features" aria-labelledby="features-heading" className="scroll-mt-20 py-16 md:py-20">
      <div className="container">
        <div className="mb-10 max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
            Features
          </p>
          <h2 id="features-heading" className="mt-2 font-display text-3xl font-semibold tracking-tight">
            Mapped to the three objectives
          </h2>
          <p className="mt-3 text-muted-foreground">
            Every feature exists to turn a certificate into a verified, funded outcome.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {FEATURES.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <motion.div
                key={feature.title}
                initial={reduceMotion ? undefined : { opacity: 0, y: 18 }}
                whileInView={reduceMotion ? undefined : { opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ delay: 0.1 * index, duration: 0.45 }}
              >
                <Card className="h-full">
                  <CardHeader>
                    <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-lg bg-secondary text-primary">
                      <Icon className="h-5 w-5" aria-hidden />
                    </span>
                    <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
                      {feature.objective}
                    </p>
                    <CardTitle className="font-display text-lg">{feature.title}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-2">
                      {feature.bullets.map((bullet) => (
                        <li key={bullet} className="flex items-start gap-2 text-sm text-muted-foreground">
                          <span
                            aria-hidden
                            className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-marigold-500"
                          />
                          {bullet}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
