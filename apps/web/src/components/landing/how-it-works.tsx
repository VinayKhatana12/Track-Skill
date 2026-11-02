"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ClipboardCheck, RadioTower, ShieldCheck, Vote } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const STEPS = [
  {
    icon: ClipboardCheck,
    step: "1 · Consent",
    title: "Consent first, always",
    body: "The trainee grants WhatsApp / IVR / SMS consent in one tap and can revoke it at any time. No consent, no tracer — enforced in the database, not just the UI.",
  },
  {
    icon: RadioTower,
    step: "2 · Trace",
    title: "Tracers go out at 3 / 6 / 12 months",
    body: "The scheduler delivers simulated WhatsApp chats and IVR call-cards. Replies are parsed into structured outcomes with a confidence score — ambiguous answers route to manual review.",
  },
  {
    icon: ShieldCheck,
    step: "3 · Verify",
    title: "Two signals, one truth",
    body: "The trainee's claim and the employer's confirmation must both say CONFIRMED. Unverified outcomes count at half weight in every statistic.",
  },
  {
    icon: Vote,
    step: "4 · Act",
    title: "Evidence funds what works",
    body: "The Provider Performance Index recalculates live. Missions allocate funds, flag outliers and close curriculum gaps with the market.",
  },
] as const;

export function HowItWorks() {
  const reduceMotion = useReducedMotion() ?? false;

  return (
    <section id="how-it-works" aria-labelledby="how-heading" className="scroll-mt-20 py-16 md:py-20">
      <div className="container">
        <div className="mb-10 max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
            How it works
          </p>
          <h2 id="how-heading" className="mt-2 font-display text-3xl font-semibold tracking-tight">
            Consent → Trace → Verify → Act
          </h2>
          <p className="mt-3 text-muted-foreground">
            Four steps between certification and a decision a mission can defend.
          </p>
        </div>

        <ol className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            return (
              <motion.li
                key={step.step}
                initial={reduceMotion ? undefined : { opacity: 0, y: 20 }}
                whileInView={reduceMotion ? undefined : { opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ delay: 0.1 * index, duration: 0.45 }}
                className="h-full"
              >
                <Card className="h-full">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary text-primary">
                        <Icon className="h-5 w-5" aria-hidden />
                      </span>
                      <span className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
                        {step.step}
                      </span>
                    </div>
                    <CardTitle className="mt-3 font-display text-lg">{step.title}</CardTitle>
                    <CardDescription className="sr-only">{step.step}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-relaxed text-muted-foreground">{step.body}</p>
                  </CardContent>
                </Card>
              </motion.li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
