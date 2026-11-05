"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { useState } from "react";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { EmptyState, KpiCard, PulseCard } from "@/components/dashboard/kpi-card";
import { OutcomesBar } from "@/components/charts/outcomes-bar";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePulse } from "@/hooks/use-pulse";
import { DashboardShell } from "@/components/dashboard/app-shell";
import { api } from "@/lib/api";
import { downloadCsv } from "@/lib/export";
import {
  fetchProviderCourses,
  fetchProviderFollowups,
  fetchProviderGapAlerts,
  fetchProviderOverview,
  fetchProviderTrainees,
} from "@/lib/api";

interface TraineeRow {
  id: string;
  name: string;
  email: string;
  course_title: string | null;
  status: string;
  consent_active: boolean;
}

interface FollowupItem {
  followup_id: string;
  trainee_name: string;
  milestone: string;
  due_on: string;
  channel: string;
  raw_text?: string;
}

export default function ProviderDashboard() {
  const queryClient = useQueryClient();
  const overview = useQuery({
    queryKey: ["provider-overview"],
    queryFn: fetchProviderOverview,
  });
  const trainees = useQuery({
    queryKey: ["provider-trainees"],
    queryFn: fetchProviderTrainees,
  });
  const followups = useQuery({
    queryKey: ["provider-followups"],
    queryFn: fetchProviderFollowups,
  });
  const courses = useQuery({
    queryKey: ["provider-courses"],
    queryFn: fetchProviderCourses,
  });
  const gaps = useQuery({
    queryKey: ["provider-gaps"],
    queryFn: fetchProviderGapAlerts,
  });

  const ppiPulse = usePulse("PPI_RECALCULATED", "VERIFICATION_COMPLETE");
  const tracerPulse = usePulse("TRACER_SENT", "TRACER_MISSED", "FOLLOWUP_RESPONDED");
  const traineePulse = usePulse("TRAINEE_ENROLLED", "TRAINEES_IMPORTED");

  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [enrolOpen, setEnrolOpen] = useState(false);
  const [enrolResult, setEnrolResult] = useState<string | null>(null);
  const [certifyingId, setCertifyingId] = useState<string | null>(null);

  const certify = async (traineeId: string) => {
    setCertifyingId(traineeId);
    try {
      await api.patch(`/provider/trainees/${traineeId}/certify`, {});
      await queryClient.invalidateQueries();
    } finally {
      setCertifyingId(null);
    }
  };

  const rows = (trainees.data ?? []).filter((row) => {
    if (statusFilter !== "ALL" && row.status !== statusFilter) {
      return false;
    }
    if (search) {
      const needle = search.toLowerCase();
      if (!`${row.name} ${row.email}`.toLowerCase().includes(needle)) {
        return false;
      }
    }
    return true;
  });

  return (
    <DashboardShell
      role="PROVIDER"
      headline="Centre Command"
      subheading="Enrol, certify and trace — with your PPI always in view."
    >
      <OnboardingTour role="PROVIDER" />

      <section id="overview" aria-label="Key indicators" className="scroll-mt-24">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {overview.data ? (
            <>
              <KpiCard icon={Radar} label="Enrolled" value={overview.data.enrolled} />
              <KpiCard icon={Radar} label="Certified" value={overview.data.certified} />
              <KpiCard
                icon={Radar}
                label="Consent rate"
                value={`${Math.round(overview.data.consent_rate * 100)}%`}
              />
              <KpiCard
                icon={Radar}
                label="Response rate"
                value={`${Math.round(overview.data.response_rate * 100)}%`}
              />
              <KpiCard
                icon={Radar}
                label="Placement rate"
                value={`${Math.round(overview.data.placement_rate * 100)}%`}
              />
              <PulseCard pulsing={ppiPulse}>
                <Card className="h-full border-primary/40">
                  <CardContent className="pt-6">
                    <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      PPI · rank {overview.data.ppi_rank}/{overview.data.total_centres}
                    </p>
                    <p className="mt-1 font-display text-3xl font-semibold text-primary">
                      {overview.data.ppi_score.toFixed(1)}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      live — recalculates on verification
                    </p>
                  </CardContent>
                </Card>
              </PulseCard>
            </>
          ) : overview.isError ? (
            <p className="text-sm text-destructive">Could not load the overview.</p>
          ) : (
            Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-28" />)
          )}
        </div>
      </section>

      <section id="trainees" aria-label="Trainees" className="scroll-mt-24">
        <PulseCard pulsing={traineePulse}>
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="font-display text-xl">Trainees</CardTitle>
                <CardDescription>
                  {traineePulse
                    ? "Just updated — new activity received."
                    : "Your centre roster."}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" onClick={() => setEnrolOpen(true)}>
                  Enrol trainee
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => downloadCsv("trainees.csv", (trainees.data ?? []) as unknown as Record<string, unknown>[])}
                  disabled={(trainees.data?.length ?? 0) === 0}
                >
                  Export CSV
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-4 flex flex-wrap gap-2">
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search name or email…"
                  aria-label="Filter trainees"
                  className="max-w-xs"
                />
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  aria-label="Filter by status"
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                >
                  {["ALL", "ENROLLED", "CERTIFIED", "DROPPED"].map((option) => (
                    <option key={option} value={option}>
                      {option === "ALL" ? "All statuses" : option}
                    </option>
                  ))}
                </select>
              </div>

              {trainees.isPending ? (
                <Skeleton className="h-48 w-full" />
              ) : rows.length === 0 ? (
                <EmptyState icon={Radar} title="No trainees match" hint="Adjust the filters." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th scope="col" className="py-2 pr-3">
                          Name
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Course
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Status
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Consent
                        </th>
                        <th scope="col" className="py-2">
                          Action
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.id} className="border-b border-border/50 last:border-0">
                          <td className="py-2 pr-3 font-medium">{row.name}</td>
                          <td className="py-2 pr-3 text-muted-foreground">{row.course_title}</td>
                          <td className="py-2 pr-3">{row.status}</td>
                          <td className="py-2 pr-3">{row.consent_active ? "Granted" : "—"}</td>
                          <td className="py-2">
                            {row.status === "ENROLLED" && (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={certifyingId === row.id}
                                onClick={() => certify(row.id)}
                              >
                                {certifyingId === row.id ? "Certifying…" : "Certify"}
                              </Button>
                            )}
                            {row.status === "CERTIFIED" && (
                              <span title="certified">✓</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </PulseCard>

        {enrolOpen && (
          <EnrolDialog
            courses={courses.data ?? []}
            onClose={() => setEnrolOpen(false)}
            onDone={(message) => {
              setEnrolResult(message);
              void queryClient.invalidateQueries();
            }}
          />
        )}
        {enrolResult && (
          <p role="status" className="rounded-md bg-secondary/60 px-3 py-2 text-sm">
            {enrolResult}
          </p>
        )}
      </section>

      <section id="followups" aria-label="Follow-up queue" className="scroll-mt-24">
        <PulseCard pulsing={tracerPulse}>
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl">Follow-up queue</CardTitle>
              <CardDescription>
                {tracerPulse
                  ? "Updated in real time."
                  : "Tracers due soon and overdue ones — consent-gated."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {followups.isPending || !followups.data ? (
                <Skeleton className="h-32 w-full" />
              ) : (
                <div className="space-y-4">
                  <QueueList title="Overdue" items={followups.data.overdue} highlight />
                  <QueueList title="Due this week" items={followups.data.due_soon} />
                  <QueueList
                    title="Manual review (low-confidence replies)"
                    items={followups.data.manual_review}
                    manual
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>

      <section id="insights" aria-label="Insights" className="scroll-mt-24">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl">Outcomes by milestone</CardTitle>
            <CardDescription>
              Employment retention reported at each checkpoint.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {overview.data ? (
              <OutcomesBar
                data={[
                  { milestone: "3 months", rate: overview.data.retention_3m },
                  { milestone: "6 months", rate: overview.data.retention_6m },
                  { milestone: "12 months", rate: overview.data.retention_12m },
                ]}
              />
            ) : (
              <Skeleton className="h-64 w-full" />
            )}
          </CardContent>
        </Card>
      </section>

      <section aria-label="Curriculum gap alerts" className="scroll-mt-24">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl">Curriculum gap alerts</CardTitle>
            <CardDescription>
              Courses whose skills fall behind district demand — from the AI matcher.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {gaps.isPending || !gaps.data ? (
              <Skeleton className="h-24 w-full" />
            ) : gaps.data.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No curriculum gaps detected for your centre&apos;s courses.
              </p>
            ) : (
              <ul className="space-y-3">
                {gaps.data.slice(0, 4).map((row) => (
                  <li key={row.course_id} className="rounded-md border border-border p-3">
                    <p className="flex items-center justify-between text-sm font-medium">
                      {row.title}
                      <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
                        gap {row.gap_score.toFixed(2)}
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Missing:{" "}
                      {row.missing_in_demand_skills.map((m) => m.skill).join(", ") || "—"}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>
    </DashboardShell>
  );
}

function QueueList({
  title,
  items,
  highlight,
  manual,
}: {
  title: string;
  items: FollowupItem[];
  highlight?: boolean;
  manual?: boolean;
}) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">
        {title}
        <span className="ml-1 rounded-full bg-muted px-2 py-0.5 text-xs font-normal text-muted-foreground">
          {items.length}
        </span>
      </h3>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nothing here right now.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.followup_id}
              className={
                highlight
                  ? "rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
                  : "rounded-md border border-border px-3 py-2 text-sm"
              }
            >
              <span className="font-medium">{item.trainee_name}</span>
              <span className="text-muted-foreground">
                {" · "}
                {item.milestone} · due {item.due_on} · {item.channel}
              </span>
              {manual && item.raw_text && (
                <p className="mt-1 text-xs text-muted-foreground">raw: {item.raw_text}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EnrolDialog({
  courses,
  onClose,
  onDone,
}: {
  courses: { id: string; title: string }[];
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: "", email: "", phone: "", course_id: "" });
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (formEvent: React.FormEvent<HTMLFormElement>) => {
    formEvent.preventDefault();
    if (!form.course_id) {
      setError("Select a course.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.post<{ temporary_password: string }>(
        "/provider/trainees",
        form,
      );
      setTempPassword(result.temporary_password);
      onDone("Trainee enrolled.");
      void queryClient.invalidateQueries();
    } catch (enrolError) {
      setError(
        enrolError instanceof Error && enrolError.message.includes("exists")
          ? "An account with this email already exists."
          : "Could not enrol this trainee. Check the details and try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Enrol trainee"
    >
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="font-display text-xl">Enrol trainee</CardTitle>
          <CardDescription>
            Creates the account and profile. A one-time temporary password is shown after.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tempPassword ? (
            <div className="space-y-3">
              <p className="rounded-md border border-primary/30 bg-secondary/50 p-3 text-sm">
                Temporary password (shown once, hand it to the trainee):
                <span className="ml-1 font-mono font-semibold">{tempPassword}</span>
              </p>
              <Button onClick={onClose}>Done</Button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-3">
              <Input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Full name"
                aria-label="Full name"
                required
              />
              <Input
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                placeholder="Email"
                type="email"
                aria-label="Email"
                required
              />
              <Input
                value={form.phone}
                onChange={(event) => setForm({ ...form, phone: event.target.value })}
                placeholder="Phone"
                aria-label="Phone"
                required
              />
              <select
                value={form.course_id}
                onChange={(event) => setForm({ ...form, course_id: event.target.value })}
                aria-label="Course"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                required
              >
                <option value="">Select a course…</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.title}
                  </option>
                ))}
              </select>
              {error && (
                <p
                  role="alert"
                  className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {error}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={onClose}>
                  Cancel
                </Button>
                <Button type="submit" disabled={submitting}>
                  Enrol
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
