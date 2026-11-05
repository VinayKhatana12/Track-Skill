"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCheck,
  GraduationCap,
  Loader2,
  MapPin,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import { useState } from "react";

import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { EmptyState, KpiCard, PulseCard } from "@/components/dashboard/kpi-card";
import { MessagesPanel } from "@/components/trainee/messages-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePulse } from "@/hooks/use-pulse";
import { DashboardShell } from "@/components/dashboard/app-shell";
import { api, assessSkills } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/types/api";

interface MeResponse {
  profile: {
    id: string;
    name: string | null;
    district: string;
    gender: string;
    enrolled_on: string;
    certified_on: string | null;
    status: string;
    course_title: string | null;
  };
  consents: { channel: string; granted: boolean; active: boolean; version: string }[];
  employment: {
    employment_record_id: string;
    status: string;
    job_title: string | null;
    monthly_wage: number | null;
    started_on: string | null;
    trainee_signal: string | null;
    employer_signal: string | null;
    verified: boolean;
  } | null;
  timeline: { date: string; type: string; title: string; detail: string | null }[];
  upcoming: {
    followup_id: string;
    milestone: string;
    due_on: string;
    channel: string;
    state: string;
    message: string;
  }[];
}

interface AssessmentResult {
  profile: { skill: string; sector: string; confidence: number }[];
  role_matches: {
    title: string;
    sector: string;
    score: number;
    explanation: string;
  }[];
}

export default function TraineeDashboard() {
  const me = useQuery({
    queryKey: ["trainee-me"],
    queryFn: async () => {
      const { api } = await import("@/lib/api");
      return api.get<MeResponse>("/trainee/me");
    },
  });

  return (
    <DashboardShell
      role="TRAINEE"
      headline="My Journey"
      subheading="Your consent, tracers and outcomes — all in one place."
    >
      {me.isPending ? (
        <div className="space-y-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : me.isError ? (
        <EmptyState
          icon={GraduationCap}
          title="No trainee profile yet"
          hint="Profiles are created when a centre enrols you in a course."
        />
      ) : (
        <TraineeContent me={me.data} />
      )}
    </DashboardShell>
  );
}

function TraineeContent({ me }: { me: MeResponse }) {
  const verificationPulse = usePulse("VERIFICATION_COMPLETE", "EMPLOYMENT_SELF_REPORTED");
  const consentPulse = usePulse("CONSENT_GRANTED", "CONSENT_REVOKED");

  return (
    <>
      <section id="journey" aria-label="My journey" className="scroll-mt-24">
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <PulseCard pulsing={verificationPulse}>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="font-display text-xl">Journey timeline</CardTitle>
                <CardDescription>
                  {me.profile.status === "CERTIFIED"
                    ? `Certified ${me.profile.certified_on ?? ""} — milestones follow.`
                    : `Enrolled ${me.profile.enrolled_on} — certification to come.`}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="relative space-y-4 border-l border-border pl-5">
                  {me.timeline.map((item, index) => (
                    <li key={`${item.type}-${item.date}-${index}`} className="relative">
                      <span
                        aria-hidden
                        className="absolute -left-[1.55rem] top-1 h-2.5 w-2.5 rounded-full border-2 border-primary bg-background"
                      />
                      <p className="text-xs text-muted-foreground">{item.date}</p>
                      <p className="text-sm font-medium">{item.title}</p>
                      {item.detail && (
                        <p className="text-xs text-muted-foreground">{item.detail}</p>
                      )}
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </PulseCard>

          <div className="space-y-6">
            <PulseCard pulsing={verificationPulse}>
              <Card>
                <CardHeader>
                  <CardTitle className="font-display text-lg">Verification status</CardTitle>
                  <CardDescription>Dual-signal: you + your employer</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <SignalRow
                    label="Your signal"
                    signal={me.employment?.trainee_signal ?? "PENDING"}
                  />
                  <SignalRow
                    label="Employer signal"
                    signal={me.employment?.employer_signal ?? "PENDING"}
                  />
                  <div className="flex items-center justify-between text-sm font-medium">
                    <span>Verified outcome</span>
                    {me.employment?.verified ? (
                      <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                        <CheckCheck className="h-4 w-4" aria-hidden /> Verified
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Awaiting both signals</span>
                    )}
                  </div>
                </CardContent>
              </Card>
            </PulseCard>

            <KpiCard
              icon={MapPin}
              label="District"
              value={me.profile.district}
              hint={me.profile.course_title ?? undefined}
            />
          </div>
        </div>
      </section>

      <section id="consent" aria-label="Consent manager" className="scroll-mt-24">
        <ConsentManager consents={me.consents} />
      </section>

      <section id="messages" aria-label="Messages" className="scroll-mt-24">
        <MessagesPanel />
      </section>

      <section id="employment" aria-label="Employment" className="scroll-mt-24">
        <EmploymentCard me={me} />
      </section>

      <section id="skills" aria-label="AI skills" className="scroll-mt-24">
        <SkillsCard />
      </section>
    </>
  );
}

function SignalRow({ label, signal }: { label: string; signal: string }) {
  const styles =
    signal === "CONFIRMED"
      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
      : signal === "DISPUTED"
        ? "bg-destructive/10 text-destructive"
        : "bg-muted text-muted-foreground";
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles}`}>
        {signal}
      </span>
    </div>
  );
}

function ConsentManager({ consents }: { consents: MeResponse["consents"] }) {
  const consentPulse = usePulse("CONSENT_GRANTED", "CONSENT_REVOKED");
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<string | null>(null);
  const channels = ["WHATSAPP", "IVR", "SMS"];

  const toggle = useMutation({
    mutationFn: async ({ channel, granted }: { channel: string; granted: boolean }) => {
      await api.post("/trainee/consent", { channel, granted });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trainee-me"] }),
  });

  return (
    <PulseCard pulsing={consentPulse}>
      <Card>
        <CardHeader>
          <CardTitle className="font-display text-xl">Consent manager</CardTitle>
          <CardDescription>
            Version-stamped per channel. Revoking cancels undelivered tracers — no consent, no
            tracing.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {channels.map((channel) => {
            const current = consents.find((item) => item.channel === channel);
            const active = current?.active ?? false;
            return (
              <div
                key={channel}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2.5"
              >
                <div>
                  <p className="text-sm font-medium">
                    {channel.charAt(0) + channel.slice(1).toLowerCase()}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {current
                      ? active
                        ? "Active — tracers may use this channel"
                        : current.granted
                          ? "Revoked"
                          : "Declined"
                      : "No decision yet"}
                    {current ? ` · v${current.version}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={active}
                  aria-label={`${active ? "Revoke" : "Grant"} ${channel} consent`}
                  disabled={pending === channel || toggle.isPending}
                  onClick={() => {
                    setPending(channel);
                    toggle.mutate(
                      { channel, granted: !active },
                      { onSettled: () => setPending(null) },
                    );
                  }}
                  className={cn(
                    "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                    active ? "bg-primary" : "bg-muted-foreground/40",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
                      active ? "translate-x-5" : "translate-x-0.5",
                    )}
                  />
                </button>
              </div>
            );
          })}
          {toggle.isPending && (
            <p className="text-xs text-muted-foreground" role="status">
              <Loader2 className="mr-1 inline h-3 w-3 animate-spin" aria-hidden />
              Saving consent…
            </p>
          )}
        </CardContent>
      </Card>
    </PulseCard>
  );
}

function EmploymentCard({ me }: { me: MeResponse }) {
  const wagePulse = usePulse("EMPLOYMENT_SELF_REPORTED");
  const queryClient = useQueryClient();
  const employment = me.employment;
  const [jobTitle, setJobTitle] = useState(employment?.job_title ?? "");
  const [wage, setWage] = useState(
    employment?.monthly_wage ? String(employment.monthly_wage) : "",
  );
  const [saved, setSaved] = useState(false);

  const report = useMutation({
    mutationFn: async () => {
      const { reportEmployment } = await import("@/lib/api");
      return reportEmployment({
        employment_status: "EMPLOYED",
        job_title: jobTitle.trim(),
        monthly_wage: Number(wage),
      });
    },
    onSuccess: () => {
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["trainee-me"] });
    },
  });

  if (me.profile.status !== "CERTIFIED") {
    return null;
  }

  return (
    <PulseCard pulsing={wagePulse}>
      <Card>
        <CardHeader>
          <CardTitle className="font-display text-xl">Employment &amp; wage</CardTitle>
          <CardDescription>
            {employment
              ? `Started ${employment.started_on ?? "—"} · ${employment.status}`
              : "Add your current role and wage to start the verification chain."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <form
            onSubmit={(formEvent) => {
              formEvent.preventDefault();
              report.mutate();
            }}
            className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end"
          >
            <div className="space-y-2">
              <Input
                value={jobTitle}
                onChange={(event) => setJobTitle(event.target.value)}
                placeholder="Job title"
                aria-label="Job title"
                required
                minLength={2}
              />
              <Input
                value={wage}
                onChange={(event) => setWage(event.target.value)}
                placeholder="Monthly wage"
                aria-label="Monthly wage"
                type="number"
                min={0}
                required
              />
            </div>
            <Button type="submit" disabled={report.isPending}>
              {report.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Wallet className="h-4 w-4" aria-hidden />
              )}
              {employment ? "Update" : "Add"}
            </Button>
          </form>
          {report.isSuccess && (
            <p role="status" className="text-xs text-muted-foreground">
              Saved — your employer signal is pending confirmation.
            </p>
          )}
          {report.isError && (
            <p role="alert" className="text-xs text-destructive">
              Could not save. Please try again.
            </p>
          )}
        </CardContent>
      </Card>
    </PulseCard>
  );
}

function SkillsCard() {
  const assessment = useQuery({
    queryKey: ["trainee-assessment"],
    queryFn: () => assessSkills({}),
    staleTime: 5 * 60 * 1000,
  });

  const radarData = (assessment.data?.profile ?? []).slice(0, 8);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl">AI skill profile</CardTitle>
        <CardDescription>
          Confidence per skill (0–1) and the closest job-role matches.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {assessment.isPending ? (
          <Skeleton className="h-64 w-full" />
        ) : radarData.length === 0 ? (
          <EmptyState
            icon={GraduationCap}
            title="No skills detected yet"
            hint="Skills come from your assigned course."
          />
        ) : (
          <>
            <div
              className="h-72 w-full"
              role="img"
              aria-label="Radar chart of skill confidence"
            >
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData} outerRadius="80%">
                  <PolarGrid stroke="hsl(var(--border))" />
                  <PolarAngleAxis
                    dataKey="skill"
                    tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                  />
                  <Radar dataKey="confidence" stroke="#2f8f8c" fill="#2f8f8c" fillOpacity={0.35} />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: 8,
                      color: "hsl(var(--card-foreground))",
                    }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold">Closest job roles</h3>
              <ul className="space-y-2">
                {(assessment.data?.role_matches ?? []).slice(0, 5).map((match) => (
                  <li key={match.title} className="rounded-md border border-border p-3 text-sm">
                    <p className="flex items-center justify-between font-medium">
                      {match.title}
                      <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
                        {match.score.toFixed(2)}
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">{match.explanation}</p>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
