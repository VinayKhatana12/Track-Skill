"use client";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { AccountCard } from "@/components/dashboard/account-card";
import { PlaceholderPanel } from "@/components/dashboard/placeholder-panel";
import { useAuthStore } from "@/stores/auth-store";

export default function EmployerDashboardPage() {
  const user = useAuthStore((state) => state.user);
  if (!user) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Employer workspace</h1>
        <p className="mt-2 text-muted-foreground">
          Welcome back, {user.name}. Confirm the employment of the trainees you hired.
        </p>
      </header>
      <OnboardingTour role="EMPLOYER" />
      <div className="grid gap-6 lg:grid-cols-2">
        <AccountCard user={user} />
        <PlaceholderPanel
          title="Verification queue — Phase 3"
          description="Dual-signal confirmation tools arrive with the tracing phase."
          bullets={[
            "Confirm or dispute employment signals for your hires",
            "See who still needs confirmation",
            "Company profile management",
          ]}
        />
      </div>
    </div>
  );
}
