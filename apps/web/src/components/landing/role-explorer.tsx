"use client";

import { motion, useReducedMotion } from "framer-motion";
import { BarChart3, BotMessageSquare, CheckCheck, Radar } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface RolePreview {
  role: string;
  headline: string;
  benefit: string;
  bullets: string[];
  demoEmail: string;
  dashboard: string;
}

const ROLES: RolePreview[] = [
  {
    role: "Provider",
    headline: "Run your centre on evidence",
    benefit: "Enrol batches in bulk, certify in one click, and see your PPI move the moment an employer confirms a placement.",
    bullets: ["Bulk CSV enrolment", "Due & overdue tracers", "Live PPI + district rank"],
    demoEmail: "provider.demo@trackskill.in",
    dashboard: "/dashboard/provider",
  },
  {
    role: "Trainee",
    headline: "Your journey, your consent",
    benefit: "Grant consent once, get tracer messages at 3/6/12 months, and answer in one line — your outcome is counted only when you and your employer agree.",
    bullets: ["WhatsApp-style tracers", "One-line replies", "Skill profile & role matches"],
    demoEmail: "trainee.demo@trackskill.in",
    dashboard: "/dashboard/trainee",
  },
  {
    role: "Employer",
    headline: "Verify claims in seconds",
    benefit: "A pending queue of claims that name you as the employer. Confirm or dispute with one tap — verified outcomes build your talent pipeline.",
    bullets: ["Pending verification queue", "One-tap confirm/dispute", "Consented talent pool by skill"],
    demoEmail: "employer.demo@trackskill.in",
    dashboard: "/dashboard/employer",
  },
  {
    role: "Admin",
    headline: "Govern with the full picture",
    benefit: "State KPIs, the PPI leaderboard, curriculum gaps and a live audit feed — allocate funds with a rationale the data supports.",
    bullets: ["District heat map", "PPI leaderboard", "Fund allocation & flags"],
    demoEmail: "admin.demo@trackskill.in",
    dashboard: "/dashboard/admin",
  },
];

const ROLE_ICONS = [Radar, BotMessageSquare, CheckCheck, BarChart3] as const;

export function RoleExplorer() {
  const reduceMotion = useReducedMotion() ?? false;
  const [activeRole, setActiveRole] = useState(0);
  const role = ROLES[activeRole];
  const RoleIcon = ROLE_ICONS[activeRole];

  return (
    <section id="roles" aria-labelledby="roles-heading" className="scroll-mt-20 py-16 md:py-20">
      <div className="container">
        <div className="mb-10 max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
            Role explorer
          </p>
          <h2 id="roles-heading" className="mt-2 font-display text-3xl font-semibold tracking-tight">
            One platform, four seats at the table
          </h2>
          <p className="mt-3 text-muted-foreground">
            Pick a seat to preview its dashboard — then try it instantly with the demo account.
          </p>
        </div>

        <div role="tablist" aria-label="Preview a role" className="flex flex-wrap gap-2">
          {ROLES.map((preview, index) => (
            <button
              key={preview.role}
              role="tab"
              id={`role-tab-${preview.role}`}
              aria-selected={activeRole === index}
              aria-controls={`role-panel-${preview.role}`}
              onClick={() => setActiveRole(index)}
              className={cn(
                "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                activeRole === index
                  ? "bg-primary text-primary-foreground"
                  : "border border-input text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {preview.role}
            </button>
          ))}
        </div>

        <motion.div
          key={role.role}
          role="tabpanel"
          id={`role-panel-${role.role}`}
          aria-labelledby={`role-tab-${role.role}`}
          initial={reduceMotion ? undefined : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduceMotion ? 0 : 0.3 }}
          className="mt-6"
        >
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-secondary text-primary">
                  <RoleIcon className="h-5 w-5" aria-hidden />
                </span>
                <div>
                  <CardTitle className="font-display text-xl">{role.headline}</CardTitle>
                  <CardDescription>{role.role} dashboard preview</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="grid gap-6 md:grid-cols-[1fr_auto] md:items-center">
              <div>
                <p className="text-sm leading-relaxed text-muted-foreground">{role.benefit}</p>
                <ul className="mt-4 space-y-2">
                  {role.bullets.map((bullet) => (
                    <li key={bullet} className="flex items-center gap-2 text-sm">
                      <span
                        aria-hidden
                        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-secondary text-primary"
                      >
                        <CheckCheck className="h-3 w-3" />
                      </span>
                      {bullet}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex flex-col items-start gap-2 md:items-end">
                <Button asChild>
                  {/* Pre-fills the demo credentials for this role on the sign-in page. */}
                  <Link href={`/login?role=${role.role}`}>Try as {role.role}</Link>
                </Button>
                <p className="font-mono text-xs text-muted-foreground" aria-hidden>
                  {role.demoEmail}
                </p>
                <p className="max-w-[16rem] text-right text-[11px] text-muted-foreground md:text-right">
                  Opens the sign-in page with the demo credentials pre-filled (sample data).
                </p>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </section>
  );
}

function CheckDot() {
  return (
    <span
      aria-hidden
      className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-secondary text-primary"
    >
      <CheckCheck className="h-3 w-3" />
    </span>
  );
}
