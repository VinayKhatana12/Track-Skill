"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Loader2, X } from "lucide-react";
import { useState } from "react";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { EmptyState, KpiCard, PulseCard } from "@/components/dashboard/kpi-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePulse } from "@/hooks/use-pulse";
import { DashboardShell } from "@/components/dashboard/app-shell";
import {
  fetchEmployerImpact,
  fetchTalentPool,
  fetchVerifications,
  markConfirmed,
  markDisputed,
} from "@/lib/api";

interface VerificationRow {
  verification_id: string;
  trainee_name: string;
  employment_status: string;
  job_title: string | null;
  monthly_wage: number | null;
  trainee_signal: string;
}

export default function EmployerDashboard() {
  return (
    <DashboardShell
      role="EMPLOYER"
      headline="Verify & Hire"
      subheading="Confirm the claims that name your company — verified outcomes count."
    >
      <OnboardingTour role="EMPLOYER" />
      <EmployerContent />
    </DashboardShell>
  );
}

function EmployerContent() {
  const verifications = useQuery({
    queryKey: ["employer-verifications"],
    queryFn: () => fetchVerifications(),
  });
  const impact = useQuery({ queryKey: ["employer-impact"], queryFn: fetchEmployerImpact });

  const verifyPulse = usePulse("FOLLOWUP_RESPONDED", "EMPLOYMENT_SELF_REPORTED");
  const completePulse = usePulse("VERIFICATION_COMPLETE", "VERIFICATION_DISPUTED");
  const [disputingId, setDisputingId] = useState<string | null>(null);

  const pending = verifications.data ?? [];
  const confirmed = pending.filter((row) => row.trainee_signal === "CONFIRMED");

  return (
    <>
      <section id="verify" aria-label="Verification queue" className="scroll-mt-24">
        <PulseCard pulsing={verifyPulse}>
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl">Pending verifications</CardTitle>
              <CardDescription>
                {verifyPulse
                  ? "New claims received in real time."
                  : "Trainees who reported employment at your company."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {verifications.isPending ? (
                <Skeleton className="h-32 w-full" />
              ) : pending.length === 0 ? (
                <EmptyState
                  icon={CheckCheck}
                  title="No pending claims"
                  hint="New claims appear here the moment a trainee names your company."
                />
              ) : (
                <ul className="space-y-3">
                  {pending.map((row) => (
                    <li key={row.verification_id} className="rounded-md border border-border p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-sm font-medium">{row.trainee_name}</p>
                          <p className="text-xs text-muted-foreground">
                            {row.job_title ?? row.employment_status}
                            {row.monthly_wage
                              ? ` · ${row.monthly_wage.toLocaleString("en-GB")} monthly`
                              : ""}
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <ConfirmButton verificationId={row.verification_id} />
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setDisputingId(row.verification_id)}
                          >
                            Dispute
                          </Button>
                        </div>
                      </div>
                      <p className="mt-2">
                        <SignalBadge signal={row.trainee_signal} />
                      </p>
                      {disputingId === row.verification_id && (
                        <DisputeDialog
                          verificationId={row.verification_id}
                          onClose={() => setDisputingId(null)}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>

      <section id="hires" aria-label="Hires" className="scroll-mt-24">
        <PulseCard pulsing={completePulse}>
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl">Your hires</CardTitle>
              <CardDescription>
                Verified: {impact.data?.verified_hires ?? 0} of {impact.data?.hires ?? 0} ·
                working: {impact.data?.working ?? 0}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {impact.isPending ? (
                <Skeleton className="h-24 w-full" />
              ) : confirmed.length === 0 ? (
                <EmptyState
                  icon={CheckCheck}
                  title="No verified hires yet"
                  hint="Confirm a pending claim to move it here."
                />
              ) : (
                <ul className="space-y-2">
                  {confirmed.map((row) => (
                    <li
                      key={row.verification_id}
                      className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
                    >
                      <span className="font-medium">{row.trainee_name}</span>
                      <span className="text-muted-foreground">{row.job_title ?? "—"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>

      <section id="talent" aria-label="Talent pool" className="scroll-mt-24">
        <TalentPoolCard />
      </section>

      <section id="impact" aria-label="Impact" className="scroll-mt-24">
        <PulseCard pulsing={completePulse}>
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl">Retention of your hires</CardTitle>
              <CardDescription>Share of respondents still in work per milestone.</CardDescription>
            </CardHeader>
            <CardContent>
              {impact.isPending ? (
                <Skeleton className="h-20 w-full" />
              ) : (
                <div className="grid gap-4 sm:grid-cols-3">
                  <KpiCard
                    icon={CheckCheck}
                    label="3-month retention"
                    value={`${Math.round((impact.data?.retention_3m ?? 0) * 100)}%`}
                  />
                  <KpiCard
                    icon={CheckCheck}
                    label="6-month retention"
                    value={`${Math.round((impact.data?.retention_6m ?? 0) * 100)}%`}
                  />
                  <KpiCard
                    icon={CheckCheck}
                    label="12-month retention"
                    value={`${Math.round((impact.data?.retention_12m ?? 0) * 100)}%`}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>
    </>
  );
}

function ConfirmButton({ verificationId }: { verificationId: string }) {
  const queryClient = useQueryClient();
  const confirm = useMutation({
    mutationFn: () => markConfirmed(verificationId),
    onSuccess: () => queryClient.invalidateQueries(),
  });
  return (
    <Button size="sm" onClick={() => confirm.mutate()} disabled={confirm.isPending}>
      {confirm.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      Confirm
    </Button>
  );
}

function SignalBadge({ signal }: { signal: string }) {
  const styles =
    signal === "CONFIRMED"
      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
      : "bg-muted text-muted-foreground";
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles}`}>{signal}</span>
  );
}

function DisputeDialog({
  verificationId,
  onClose,
}: {
  verificationId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const dispute = useMutation({
    mutationFn: async () => {
      const { markDisputed } = await import("@/lib/api");
      return markDisputed(verificationId, reason);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries();
      onClose();
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Dispute claim"
    >
      <Card className="w-full max-w-md">
        <CardHeader className="flex-row items-start justify-between space-y-0">
          <div>
            <CardTitle className="font-display text-lg">Dispute this claim</CardTitle>
            <CardDescription>The trainee and admins will see your reason.</CardDescription>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-muted-foreground hover:bg-accent"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </CardHeader>
        <CardContent>
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            minLength={3}
            required
            aria-label="Dispute reason"
            placeholder="Why are you disputing this claim?"
            className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => dispute.mutate()}
              disabled={dispute.isPending || reason.trim().length < 3}
            >
              {dispute.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              Submit dispute
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TalentPoolCard() {
  const [skill, setSkill] = useState("");
  const [district, setDistrict] = useState("");
  const [submitted, setSubmitted] = useState<{ skill: string; district: string }>({
    skill: "",
    district: "",
  });

  const pool = useQuery({
    queryKey: ["talent-pool", submitted],
    queryFn: () => fetchTalentPool(submitted.skill, submitted.district),
    enabled: false,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl">Talent pool</CardTitle>
        <CardDescription>Certified trainees with active consent, grouped by skill.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          onSubmit={(formEvent) => {
            formEvent.preventDefault();
            setSubmitted({ skill, district });
          }}
          className="flex flex-wrap gap-2"
        >
          <Input
            value={skill}
            onChange={(event) => setSkill(event.target.value)}
            placeholder="Skill (optional)"
            aria-label="Skill filter"
            className="max-w-[12rem]"
          />
          <Input
            value={district}
            onChange={(event) => setDistrict(event.target.value)}
            placeholder="District (optional)"
            aria-label="District filter"
            className="max-w-[12rem]"
          />
          <Button type="submit" variant="outline" size="sm">
            Search
          </Button>
        </form>

        {pool.isFetching ? (
          <Skeleton className="h-32 w-full" />
        ) : (pool.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No consented trainees match — press Search to query the pool.
          </p>
        ) : (
          <ul className="space-y-2">
            {(pool.data ?? []).map((row) => (
              <li
                key={row.skill}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
              >
                <div>
                  <p className="font-medium">{row.skill}</p>
                  <p className="text-xs text-muted-foreground">
                    {row.districts.join(", ")} · {row.trainee_names.join(", ")}
                  </p>
                  {row.contacts?.length > 0 && (
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Contact (masked): {row.contacts.map((c) => c.email).join(" · ")}
                    </p>
                  )}
                </div>
                <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-semibold text-secondary-foreground">
                  {row.trainee_count} · match {row.match_score.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
