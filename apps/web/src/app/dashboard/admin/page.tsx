"use client";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { AccountCard } from "@/components/dashboard/account-card";
import { TracerPanel } from "@/components/admin/tracer-panel";
import { PlaceholderPanel } from "@/components/dashboard/placeholder-panel";
import { useAuthStore } from "@/stores/auth-store";

export default function AdminDashboardPage() {
  const user = useAuthStore((state) => state.user);
  if (!user) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          State Skilling Mission
        </h1>
        <p className="mt-2 text-muted-foreground">
          Welcome back, {user.name}. Governance analytics for the whole mission.
        </p>
      </header>
      <OnboardingTour role="ADMIN" />
      <div className="grid gap-6 lg:grid-cols-2">
        <AccountCard user={user} />
        <TracerPanel />
        <PlaceholderPanel
          title="Governance analytics — Phase 5"
          description="Fund-allocation evidence arrives with the analytics phase."
          bullets={[
            "Provider Performance Index leaderboard and trends",
            "Fund allocation workflow with rationale records",
            "Market demand heat map by sector, skill and district",
            "Outcome verification audit trail",
          ]}
        />
      </div>
    </div>
  );
}
