"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";

import { LandingNav } from "@/components/landing/landing-nav";
import { OutcomeTimeline } from "@/components/landing/outcome-timeline";
import { ProblemSolution } from "@/components/landing/problem-solution";
import { HowItWorks } from "@/components/landing/how-it-works";
import { RoleExplorer } from "@/components/landing/role-explorer";
import { SocialProof } from "@/components/landing/social-proof";
import { FeaturesGrid } from "@/components/landing/features-grid";
import { FaqSection } from "@/components/landing/faq";
import { ContactSection } from "@/components/landing/contact-section";
import { LandingFooter } from "@/components/landing/landing-footer";
import { Button } from "@/components/ui/button";

export function LandingPage() {
  const reduceMotion = useReducedMotion() ?? false;
  const fade = (delay: number) =>
    reduceMotion
      ? {}
      : {
          initial: { opacity: 0, y: 16 },
          animate: { opacity: 1, y: 0 },
          transition: { delay, duration: 0.5 },
        };

  return (
    <div className="flex min-h-dvh flex-col">
      <LandingNav />

      <main id="main">
        <h1 className="sr-only">
          TrackSkill AI — consent-based outcome tracking for skilling programs
        </h1>

        {/* ── HERO ──────────────────────────────────────────────────────── */}
        <section
          aria-label="Introduction"
          className="relative overflow-hidden border-b border-border/70"
        >
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(60rem_30rem_at_85%_-10%,rgba(30,93,95,0.14),transparent)]"
          />
          <div className="container grid items-center gap-10 py-16 lg:grid-cols-[1.1fr_1fr] lg:py-24">
            <div className="flex flex-col items-start gap-6">
              <motion.p
                {...fade(0)}
                className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-800 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-200"
              >
                Skilling governance · SDG 8 · SDG 4 · SDG 9
              </motion.p>
              <motion.h2
                {...fade(0.05)}
                className="max-w-2xl font-display text-4xl font-semibold leading-tight tracking-tight text-balance sm:text-5xl"
              >
                Close the <span className="text-primary">post-certification</span> blind spot
                in skilling programs.
              </motion.h2>
              <motion.p
                {...fade(0.1)}
                className="max-w-xl text-lg leading-relaxed text-muted-foreground"
              >
                TrackSkill AI keeps following trainees after the certificate — employment,
                wages and retention at 3, 6 and 12 months — with consent-based tracers,
                employer verification and a Provider Performance Index that turns outcomes
                into funding decisions.
              </motion.p>
              <motion.div {...fade(0.15)} className="flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <a href="/register">
                    Get started
                    <ArrowRight className="h-4 w-4" aria-hidden />
                  </a>
                </Button>
                <Button asChild size="lg" variant="outline">
                  <a href="#roles">Try a live demo</a>
                </Button>
              </motion.div>
              <motion.p {...fade(0.2)} className="text-xs text-muted-foreground">
                Demo build — all accounts and figures on this page are sample data. No
                consent, no tracing.
              </motion.p>
            </div>

            <motion.div {...fade(0.2)}>
              <OutcomeTimeline />
            </motion.div>
          </div>
        </section>

        <ProblemSolution />
        <HowItWorks />
        <RoleExplorer />
        <SocialProof />
        <FeaturesGrid />
        <FaqSection />
        <ContactSection />
      </main>

      <LandingFooter />
    </div>
  );
}
