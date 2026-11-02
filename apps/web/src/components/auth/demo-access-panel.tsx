"use client";

import { motion } from "framer-motion";
import { BarChart3, BotMessageSquare, CheckCheck, Radar, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { UserRole } from "@/types/api";

export interface DemoRoleCard {
  role: UserRole;
  icon: typeof Radar;
  email: string;
  headline: string;
  bullets: string[];
}

export const DEMO_ROLE_CARDS: DemoRoleCard[] = [
  {
    role: "PROVIDER",
    icon: Radar,
    email: "provider.demo@trackskill.in",
    headline: "Run a training centre",
    bullets: ["Enrol & certify trainees", "See due/overdue tracers", "Track your PPI rank"],
  },
  {
    role: "TRAINEE",
    icon: BotMessageSquare,
    email: "trainee.demo@trackskill.in",
    headline: "Answer tracers, own your journey",
    bullets: ["WhatsApp-style follow-ups", "Consent per channel", "Skill profile & role matches"],
  },
  {
    role: "EMPLOYER",
    icon: CheckCheck,
    email: "employer.demo@trackskill.in",
    headline: "Verify claims in seconds",
    bullets: ["Pending verification queue", "One-tap confirm/dispute", "Consented talent pool"],
  },
  {
    role: "ADMIN",
    icon: ShieldCheck,
    email: "admin.demo@trackskill.in",
    headline: "Govern with the full picture",
    bullets: ["State KPIs & district heat", "PPI leaderboard", "Allocations & flags"],
  },
];

export function DemoAccessPanel({
  onPick,
  onInstantSignIn,
  pending,
}: {
  onPick: (card: DemoRoleCard) => void;
  onInstantSignIn: (card: DemoRoleCard) => void;
  pending: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-base">Demo access</CardTitle>
        <CardDescription>
          One click fills the form and shows what the role can do — password included.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        {DEMO_ROLE_CARDS.map((card) => {
          const Icon = card.icon;
          return (
            <motion.div
              key={card.role}
              whileHover={{ y: -2 }}
              className={cn(
                "flex flex-col rounded-lg border border-border p-3 text-left transition-colors",
                "hover:border-primary/40",
              )}
            >
              <button
                type="button"
                onClick={() => onPick(card)}
                className="flex items-center gap-2 text-left"
                aria-label={`Fill demo credentials for ${card.role}`}
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-secondary text-primary">
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                <span className="text-sm font-semibold">{card.role}</span>
              </button>
              <p className="mt-2 text-xs font-medium">{card.headline}</p>
              <ul className="mt-1.5 flex-1 space-y-1">
                {card.bullets.map((bullet) => (
                  <li key={bullet} className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
                    <CheckCheck className="mt-0.5 h-3 w-3 shrink-0 text-primary" aria-hidden />
                    {bullet}
                  </li>
                ))}
              </ul>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="mt-3 w-full"
                disabled={pending}
                onClick={() => onInstantSignIn(card)}
              >
                Sign in instantly
              </Button>
            </motion.div>
          );
        })}
      </CardContent>
    </Card>
  );
}
