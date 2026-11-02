"use client";

import { motion, useInView, useReducedMotion } from "framer-motion";
import { BadgeCheck, Quote } from "lucide-react";
import { useRef } from "react";

import { useCountUp } from "@/hooks/use-count-up";
import { Card, CardContent } from "@/components/ui/card";

const PARTNER_MARKS = [
  "District Skilling Mission (placeholder)",
  "Skills University (placeholder)",
  "Industry Guild (placeholder)",
  "NGO Consortium (placeholder)",
  "Chamber of Commerce (placeholder)",
  "ITI Federation (placeholder)",
] as const;

const TESTIMONIALS = [
  {
    quote:
      "For the first time we can show a funder exactly what happened to batch 14 — with the employer's own confirmation attached.",
    name: "Sample Name: Centre Director",
    role: "Training provider staff — illustrative quote",
  },
  {
    quote:
      "The WhatsApp tracer takes me ten seconds to answer. Nobody from a program ever asked me how I was doing after the certificate before.",
    name: "Sample Name: Certified Trainee",
    role: "M6 tracer respondent — illustrative quote",
  },
  {
    quote:
      "The PPI leaderboard ended an argument. The data settles which centres need support and which deserve scale-up.",
    name: "Sample Name: Mission Officer",
    role: "State skilling mission — illustrative quote",
  },
] as const;

const IMPACT = [
  { target: 12480, label: "trainees tracked" },
  { target: 86, label: "centres benchmarked" },
  { target: 74, label: "districts covered" },
] as const;

const SDGS = [
  { goal: "SDG 8", title: "Decent Work & Economic Growth", primary: true },
  { goal: "SDG 4", title: "Quality Education", primary: false },
  { goal: "SDG 9", title: "Industry, Innovation & Infrastructure", primary: false },
] as const;

export function SocialProof() {
  const reduceMotion = useReducedMotion() ?? false;
  const countersRef = useRef<HTMLDivElement>(null);
  const countersInView = useInView(countersRef, { once: true, amount: 0.4 });

  return (
    <section
      id="social-proof"
      aria-labelledby="proof-heading"
      className="scroll-mt-20 py-16 md:py-20"
    >
      <div className="container space-y-14">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
            Social proof
          </p>
          <h2 id="proof-heading" className="mt-2 font-display text-3xl font-semibold tracking-tight">
            Built for missions, centres, trainees and employers
          </h2>
          <p className="mt-3 text-muted-foreground">
            Everything on this page is sample content for a capstone demo — no real
            organisations or people are represented.
          </p>
        </div>

        {/* Placeholder partner strip */}
        <div
          aria-label="Placeholder partner marks"
          className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
        >
          {PARTNER_MARKS.map((mark) => (
            <div
              key={mark}
              title="Placeholder mark — no real organisation"
              className="flex h-16 items-center justify-center rounded-lg border border-dashed border-border px-2 text-center text-[11px] leading-tight text-muted-foreground"
            >
              {mark}
            </div>
          ))}
        </div>

        {/* Testimonials */}
        <div className="grid gap-6 md:grid-cols-3">
          {TESTIMONIALS.map((testimonial) => (
            <Card key={testimonial.name} className="h-full">
              <CardContent className="flex h-full flex-col gap-3 pt-6">
                <Quote className="h-5 w-5 text-primary" aria-hidden />
                <blockquote className="flex-1 text-sm leading-relaxed">
                  {testimonial.quote}
                </blockquote>
                <footer className="text-xs text-muted-foreground">
                  <p className="flex items-center gap-1 font-medium text-foreground">
                    <BadgeCheck className="h-3.5 w-3.5 text-primary" aria-hidden />
                    {testimonial.name}
                  </p>
                  <p className="italic">{testimonial.role}</p>
                </footer>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Impact counters */}
        <div
          ref={countersRef}
          aria-label="Sample impact counters"
          className="grid gap-6 sm:grid-cols-3"
        >
          {IMPACT.map((counter) => (
            <ImpactCounter
              key={counter.label}
              target={counter.target}
              label={counter.label}
              active={countersInView}
              reduceMotion={reduceMotion}
            />
          ))}
        </div>

        {/* SDG badges */}
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-muted-foreground">Aligned with:</span>
          {SDGS.map((sdg) => (
            <span
              key={sdg.goal}
              title={sdg.title}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${
                sdg.primary
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card text-foreground"
              }`}
            >
              {sdg.goal}
              <span className={sdg.primary ? "opacity-90" : "text-muted-foreground"}>
                {sdg.title}
              </span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function ImpactCounter({
  target,
  label,
  active,
  reduceMotion,
}: {
  target: number;
  label: string;
  active: boolean;
  reduceMotion: boolean;
}) {
  const value = useCountUp(target, active, { reducedMotion: reduceMotion });
  return (
    <div className="rounded-xl border border-border/70 bg-card p-6 text-center shadow-sm">
      <p
        className="font-display text-4xl font-semibold text-primary"
        aria-label={`${target.toLocaleString("en-GB")} (sample data)`}
      >
        {value.toLocaleString("en-GB")}
      </p>
      <p className="mt-1 text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-[11px] italic text-muted-foreground">Sample data</p>
    </div>
  );
}
