"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { UserRole } from "@/types/api";

const TOUR_TIPS: Record<UserRole, string[]> = {
  PROVIDER: [
    "Enrol trainees in bulk or one by one — they get a consent prompt instantly.",
    "Certify a trainee to schedule their 3/6/12-month tracers.",
    "Your PPI card recalculates the moment an employer confirms a placement.",
  ],
  TRAINEE: [
    "Grant consent per channel — WhatsApp, IVR or SMS. Revoke any time.",
    "Tracers arrive at 3, 6 and 12 months; answer in one line.",
    "Your outcome counts fully once your employer confirms it too.",
  ],
  EMPLOYER: [
    "Trainees who name you as their employer appear in your queue.",
    "Confirm or dispute with one tap — disputes are audited.",
    "Browse the consented talent pool by skill when you hire.",
  ],
  ADMIN: [
    "State KPIs update live as verifications complete.",
    "The PPI leaderboard ranks every centre with full components.",
    "Allocate funds or flag centres — providers are notified instantly.",
  ],
};

/** First-run onboarding card for each role dashboard. Shows once per role
 * (tracked in localStorage); part of the Phase 8 auth experience. */
export function OnboardingTour({ role }: { role: UserRole }) {
  const storageKey = `trackskill-onboarding-${role.toLowerCase()}`;
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(window.localStorage.getItem(storageKey) !== "done");
  }, [storageKey]);

  if (!visible) {
    return null;
  }

  const dismiss = () => {
    window.localStorage.setItem(storageKey, "done");
    setVisible(false);
  };

  return (
    <Card className="mb-6 border-primary/30 bg-secondary/40">
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <CardTitle className="font-display text-lg">
          Welcome to your {role.charAt(0) + role.slice(1).toLowerCase()} dashboard
        </CardTitle>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss onboarding"
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {TOUR_TIPS[role].map((tip, index) => (
            <li key={tip} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span
                aria-hidden
                className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground"
              >
                {index + 1}
              </span>
              {tip}
            </li>
          ))}
        </ul>
        <Button size="sm" variant="outline" className="mt-3" onClick={dismiss}>
          Got it
        </Button>
      </CardContent>
    </Card>
  );
}
