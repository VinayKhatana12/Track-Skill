"use client";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { AccountCard } from "@/components/dashboard/account-card";
import { PlaceholderPanel } from "@/components/dashboard/placeholder-panel";
import { useAuthStore } from "@/stores/auth-store";

export default function ProviderDashboardPage() {
  const user = useAuthStore((state) => state.user);
  if (!user) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Provider workspace</h1>
        <p className="mt-2 text-muted-foreground">
          Welcome back, {user.name}. Manage your centre, courses and trainees.
        </p>
      </header>
      <OnboardingTour role="PROVIDER" />
      <div className="grid gap-6 lg:grid-cols-2">
        <AccountCard user={user} />
        <PlaceholderPanel
          title="Centre management — Phase 3"
          description="Day-to-day tools arrive with the profiles and tracing phase."
          bullets={[
            "Course catalogue and trainee enrolment",
            "Milestone tracer console (simulated WhatsApp / IVR)",
            "Employment recording and verification review",
            "PPI preview for your centre (Phase 5)",
          ]}
        />
      </div>
    </div>
  );
}
