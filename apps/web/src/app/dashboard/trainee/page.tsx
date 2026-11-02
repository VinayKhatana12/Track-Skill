"use client";

import { useQuery } from "@tanstack/react-query";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { AccountCard } from "@/components/dashboard/account-card";
import { MessagesPanel } from "@/components/trainee/messages-panel";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fetchMyTraineeProfile } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import type { TraineeStatus } from "@/types/api";

const statusBadgeClass: Record<TraineeStatus, string> = {
  CERTIFIED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  ENROLLED: "bg-marigold-100 text-marigold-800 dark:bg-marigold-950 dark:text-marigold-300",
  DROPPED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export default function TraineeDashboardPage() {
  const user = useAuthStore((state) => state.user);
  const profileQuery = useQuery({
    queryKey: ["trainees", "me"],
    queryFn: fetchMyTraineeProfile,
    retry: false,
  });

  if (!user) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-3xl font-semibold tracking-tight">My journey</h1>
        <p className="mt-2 text-muted-foreground">
          Welcome back, {user.name}. Your enrolment, certification and follow-ups live here.
        </p>
      </header>
      <OnboardingTour role="TRAINEE" />
      <div className="grid gap-6 lg:grid-cols-2">
        <AccountCard user={user} />
        <MessagesPanel />
        <Card className="h-full">
          <CardHeader>
            <CardTitle className="font-display text-xl">Trainee profile</CardTitle>
            <CardDescription>Your consent-based digital profile</CardDescription>
          </CardHeader>
          <CardContent>
            {profileQuery.isPending ? (
              <p className="text-sm text-muted-foreground" role="status">
                Loading your profile…
              </p>
            ) : profileQuery.isError ? (
              <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                No trainee profile is linked to this account yet. Profiles are
                created when a centre enrols you in a course.
              </p>
            ) : (
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <div>
                  <dt className="text-muted-foreground">Status</dt>
                  <dd>
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusBadgeClass[profileQuery.data.status]}`}
                    >
                      {profileQuery.data.status}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">District</dt>
                  <dd className="font-medium">{profileQuery.data.district}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Enrolled on</dt>
                  <dd className="font-medium">{formatDate(profileQuery.data.enrolled_on)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Certified on</dt>
                  <dd className="font-medium">{formatDate(profileQuery.data.certified_on)}</dd>
                </div>
              </dl>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
