"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  Loader2,
  MapPin,
  RadioTower,
  RotateCcw,
  TrendingUp,
} from "lucide-react";
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
  fetchAdminOverview,
  fetchAdminProviders,
  fetchEvents,
  resetDemoData,
  runTracerNow,
  submitAllocation,
} from "@/lib/api";
import { downloadCsv, printSection } from "@/lib/export";

interface AdminOverview {
  trainees: number;
  certified: number;
  placed: number;
  employment_rate: number;
  retention_3m: number;
  retention_6m: number;
  retention_12m: number;
  median_wage_uplift: number;
  self_employment_share: number;
  verification_rate: number;
  demo_mode?: boolean;
  districts: {
    district: string;
    trainees: number;
    certified: number;
    working: number;
    employment_rate: number;
  }[];
}

interface LeaderboardRow {
  centre_id: string;
  centre_name: string;
  district: string;
  rank: number;
  ppi_score: number;
  placement_rate: number;
  verification_rate: number;
}

export default function AdminDashboard() {
  return (
    <DashboardShell
      role="ADMIN"
      headline="Governance"
      subheading="State-wide evidence for allocations, flags and curriculum design."
    >
      <OnboardingTour role="ADMIN" />
      <AdminContent />
    </DashboardShell>
  );
}

function AdminContent() {
  const queryClient = useQueryClient();
  const overview = useQuery({ queryKey: ["admin-overview"], queryFn: fetchAdminOverview });
  const providers = useQuery({ queryKey: ["admin-providers"], queryFn: fetchAdminProviders });
  const events = useQuery({
    queryKey: ["admin-events"],
    queryFn: () => fetchEvents(100),
    refetchInterval: 20_000,
  });

  const kpiPulse = usePulse("VERIFICATION_COMPLETE", "PPI_RECALCULATED");
  const leaderPulse = usePulse("PPI_RECALCULATED");
  const feedPulse = usePulse(
    "TRACER_SENT",
    "TRACER_MISSED",
    "VERIFICATION_COMPLETE",
    "FUND_ALLOCATED",
    "FLAG_RAISED",
    "TRAINEE_ENROLLED",
  );
  const flagPulse = usePulse("FLAG_RAISED");

  const [selectedCentre, setSelectedCentre] = useState<string | null>(null);
  const [tracerResult, setTracerResult] = useState<string | null>(null);
  const [resetResult, setResetResult] = useState<string | null>(null);

  const runTracer = useMutation({
    mutationFn: runTracerNow,
    onSuccess: (result) => {
      setTracerResult(
        `Delivered ${result.sent_count} tracer(s), fast-forwarded ${result.fast_forwarded}.`,
      );
      void queryClient.invalidateQueries();
    },
    onError: () => setTracerResult("Tracer cycle failed. Please try again."),
  });

  const resetData = useMutation({
    mutationFn: resetDemoData,
    onSuccess: (result) => {
      setResetResult(`Sample data regenerated (${result.users} accounts).`);
      void queryClient.invalidateQueries();
    },
    onError: () => setResetResult("Reset failed. Please try again."),
  });

  const flagEvents = (events.data ?? []).filter(
    (event) => event.type === "FLAG_RAISED",
  );

  return (
    <>
      <section id="governance" aria-label="Governance KPIs" className="scroll-mt-24">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {overview.data ? (
            <>
              <KpiCard
                icon={TrendingUp}
                label="Employment rate"
                value={`${Math.round(overview.data.employment_rate * 100)}%`}
                hint={`of ${overview.data.certified} certified`}
              />
              <KpiCard
                icon={TrendingUp}
                label="Verified"
                value={`${Math.round(overview.data.verification_rate * 100)}%`}
                hint="dual-signal confirmed"
              />
              <KpiCard
                icon={TrendingUp}
                label="Self-employed"
                value={`${Math.round(overview.data.self_employment_share * 100)}%`}
              />
              <KpiCard
                icon={TrendingUp}
                label="Wage uplift (median)"
                value={`${Math.round(overview.data.median_wage_uplift * 100)}%`}
                hint="M3 to M12 growth"
              />
            </>
          ) : overview.isError ? (
            <p className="text-sm text-destructive">Could not load the overview.</p>
          ) : (
            Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-24" />
            ))
          )}
        </div>

        <PulseCard pulsing={kpiPulse} className="mt-6">
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="font-display text-lg">District heat map</CardTitle>
                <CardDescription>
                  Colour = employment rate. Retention R3{" "}
                  {Math.round((overview.data?.retention_3m ?? 0) * 100)}% · R6{" "}
                  {Math.round((overview.data?.retention_6m ?? 0) * 100)}% · R12{" "}
                  {Math.round((overview.data?.retention_12m ?? 0) * 100)}%
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => printSection("print-summary")}
                disabled={overview.isPending}
              >
                Export PDF (print)
              </Button>
            </CardHeader>
            <CardContent>
              {overview.data ? (
                <>
                  <div
                    className="grid grid-cols-2 gap-3 sm:grid-cols-4"
                    aria-label="District heat map"
                  >
                    {overview.data.districts.map((district) => {
                      const rate = district.employment_rate;
                      const shade =
                        rate >= 0.7
                          ? "bg-brand-600 text-white"
                          : rate >= 0.5
                            ? "bg-brand-400 text-white"
                            : rate >= 0.3
                              ? "bg-marigold-300 text-marigold-950"
                              : "bg-muted text-muted-foreground";
                      return (
                        <div
                          key={district.district}
                          title={`${district.district}: ${Math.round(rate * 100)}% employment`}
                          className={`rounded-lg p-4 text-center ${shade}`}
                        >
                          <MapPin className="mx-auto h-4 w-4 opacity-70" aria-hidden />
                          <p className="mt-1 text-xs font-medium">{district.district}</p>
                          <p className="font-display text-xl font-semibold">
                            {Math.round(rate * 100)}%
                          </p>
                          <p className="text-[10px] opacity-80">
                            {district.working}/{district.certified} placed
                          </p>
                        </div>
                      );
                    })}
                  </div>
                  <div id="print-summary" className="hidden print:block">
                    <h3>TrackSkill AI — governance summary (sample data)</h3>
                    <p>
                      Employment rate {Math.round(overview.data.employment_rate * 100)}%;
                      verification {Math.round(overview.data.verification_rate * 100)}%; median
                      wage uplift {Math.round(overview.data.median_wage_uplift * 100)}%.
                    </p>
                    <ul>
                      {overview.data.districts.map((district) => (
                        <li key={district.district}>
                          {district.district}: {district.working}/{district.certified} placed (
                          {Math.round(district.employment_rate * 100)}%)
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              ) : (
                <Skeleton className="h-40 w-full" />
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>

      <section id="providers" aria-label="PPI leaderboard" className="scroll-mt-24">
        <PulseCard pulsing={leaderPulse}>
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="font-display text-xl">
                  Provider Performance Index
                </CardTitle>
                <CardDescription>
                  {leaderPulse ? "Recalculated in real time." : "Ranked best-first."}
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  downloadCsv(
                    "ppi-leaderboard.csv",
                    (providers.data ?? []) as unknown as Record<string, unknown>[],
                  )
                }
                disabled={(providers.data?.length ?? 0) === 0}
              >
                Export CSV
              </Button>
            </CardHeader>
            <CardContent>
              {providers.isPending ? (
                <Skeleton className="h-48 w-full" />
              ) : (providers.data?.length ?? 0) === 0 ? (
                <EmptyState icon={BarChart3} title="No centres yet" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th scope="col" className="py-2 pr-3">
                          #
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Centre
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          PPI
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Placement
                        </th>
                        <th scope="col" className="py-2">
                          Verification
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {(providers.data ?? []).map((row) => (
                        <tr
                          key={row.centre_id}
                          className="border-b border-border/50 last:border-0"
                        >
                          <td className="py-2 pr-3 font-semibold">{row.rank}</td>
                          <td className="py-2 pr-3">
                            <button
                              type="button"
                              onClick={() =>
                                setSelectedCentre(
                                  selectedCentre === row.centre_id ? null : row.centre_id,
                                )
                              }
                              className="text-left font-medium underline-offset-4 hover:underline"
                            >
                              {row.centre_name}
                            </button>
                            <span className="block text-xs text-muted-foreground">
                              {row.district}
                            </span>
                          </td>
                          <td className="py-2 pr-3 font-display font-semibold text-primary">
                            {row.ppi_score.toFixed(1)}
                          </td>
                          <td className="py-2 pr-3">
                            {Math.round(row.placement_rate * 100)}%
                          </td>
                          <td className="py-2">
                            {Math.round(row.verification_rate * 100)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <details className="mt-4 rounded-md border border-border p-3 text-sm">
                <summary className="cursor-pointer font-medium">
                  How is this score calculated?
                </summary>
                <p className="mt-2 leading-relaxed text-muted-foreground">
                  PPI = 100 × (0.30·placement + 0.25·retention_weighted + 0.20·wage_growth_norm +
                  0.15·verification + 0.10·response), where retention_weighted = 0.2·R3 + 0.3·R6 +
                  0.5·R12. Verified outcomes count fully; unverified ones at half weight. It
                  recalculates on every completed verification.
                </p>
              </details>
            </CardContent>
          </Card>
        </PulseCard>

        {selectedCentre && (
          <CentreDrillDown centreId={selectedCentre} onClose={() => setSelectedCentre(null)} />
        )}
      </section>

      <section id="funds" aria-label="Fund allocation" className="scroll-mt-24">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl">Fund allocation</CardTitle>
            <CardDescription>
              Pick a centre — the recommended amount is prefilled from its latest PPI.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {(providers.data?.length ?? 0) > 0 ? (
              <AllocationForm
                centres={(providers.data ?? []).map((row) => ({
                  id: row.centre_id,
                  name: row.centre_name,
                  ppi: row.ppi_score,
                }))}
                onDone={() => void queryClient.invalidateQueries()}
              />
            ) : (
              <Skeleton className="h-32 w-full" />
            )}
          </CardContent>
        </Card>
      </section>

      <section id="gaps" aria-label="Curriculum-demand gaps" className="scroll-mt-24">
        <GapMatrixCard />
      </section>

      <section id="activity" aria-label="Activity and anomalies" className="scroll-mt-24">
        <div className="grid gap-6 lg:grid-cols-2">
          <PulseCard pulsing={feedPulse}>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="font-display text-xl">Live activity feed</CardTitle>
                <CardDescription>Audit trail from the events stream.</CardDescription>
              </CardHeader>
              <CardContent>
                {events.isPending ? (
                  <Skeleton className="h-48 w-full" />
                ) : (events.data?.length ?? 0) === 0 ? (
                  <EmptyState icon={RadioTower} title="No activity yet" />
                ) : (
                  <ul className="max-h-72 space-y-2 overflow-y-auto">
                    {(events.data ?? []).map((event) => (
                      <li
                        key={event.id}
                        className="flex items-start justify-between gap-2 rounded-md border border-border/60 px-3 py-2 text-xs"
                      >
                        <span className="font-mono font-semibold">{event.type}</span>
                        <span className="text-muted-foreground">
                          {event.created_at
                            ? event.created_at.slice(0, 19).replace("T", " ")
                            : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </PulseCard>

          <PulseCard pulsing={flagPulse}>
            <Card className="h-full">
              <CardHeader className="flex-row items-start justify-between space-y-0">
                <div>
                  <CardTitle className="font-display text-xl">Anomaly flags</CardTitle>
                  <CardDescription>
                    Wage outliers, date errors, confirmation spikes.
                  </CardDescription>
                </div>
                <AnomalyScanButton />
              </CardHeader>
              <CardContent>
                {flagEvents.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No anomalies flagged yet.</p>
                ) : (
                  <ul className="max-h-64 space-y-2 overflow-y-auto">
                    {flagEvents.map((event) => (
                      <li
                        key={event.id}
                        className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
                      >
                        <AlertTriangle
                          className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
                          aria-hidden
                        />
                        <span>{String(event.payload?.summary ?? event.type)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </PulseCard>
        </div>
      </section>

      <section aria-label="Demo controls" className="scroll-mt-24">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl">Demo controls</CardTitle>
            <CardDescription>
              {overview.data?.demo_mode
                ? "These controls are live while DEMO_MODE is enabled."
                : "Disabled — DEMO_MODE is off."}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <Button
              onClick={() => runTracer.mutate()}
              disabled={runTracer.isPending || !overview.data?.demo_mode}
            >
              {runTracer.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <RadioTower className="h-4 w-4" aria-hidden />
              )}
              Run tracer now
            </Button>
            <Button
              variant="outline"
              onClick={() => resetData.mutate()}
              disabled={resetData.isPending || !overview.data?.demo_mode}
            >
              {resetData.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <RotateCcw className="h-4 w-4" aria-hidden />
              )}
              Reset demo data
            </Button>
            {tracerResult && (
              <p
                role="status"
                className="w-full rounded-md bg-secondary/60 px-3 py-2 text-sm"
              >
                {tracerResult}
              </p>
            )}
            {resetResult && (
              <p
                role="status"
                className="w-full rounded-md bg-secondary/60 px-3 py-2 text-sm"
              >
                {resetResult}
              </p>
            )}
          </CardContent>
        </Card>
      </section>
    </>
  );
}

function AnomalyScanButton() {
  const queryClient = useQueryClient();
  const scan = useMutation({
    mutationFn: async () => {
      const { runAnomalyScan } = await import("@/lib/api");
      return runAnomalyScan();
    },
    onSuccess: () => queryClient.invalidateQueries(),
  });
  return (
    <Button variant="outline" size="sm" onClick={() => scan.mutate()} disabled={scan.isPending}>
      {scan.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      Scan now
    </Button>
  );
}

function AllocationForm({
  centres,
  onDone,
}: {
  centres: { id: string; name: string; ppi: number }[];
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [centreId, setCentreId] = useState(centres[0]?.id ?? "");
  const [amount, setAmount] = useState(
    centres[0] ? String(recommendedAmount(centres[0].ppi)) : "",
  );
  const [rationale, setRationale] = useState("");
  const allocate = useMutation({
    mutationFn: (payload: { centre_id: string; amount: number; rationale: string }) =>
      submitAllocation(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries();
      setRationale("");
    },
  });

  const selected = centres.find((centre) => centre.id === centreId);

  return (
    <form
      onSubmit={(formEvent) => {
        formEvent.preventDefault();
        allocate.mutate({ centre_id: centreId, amount: Number(amount), rationale });
      }}
      className="space-y-3"
    >
      <div className="space-y-2">
        <label htmlFor="alloc-centre" className="text-sm font-medium">
          Centre
        </label>
        <select
          id="alloc-centre"
          value={centreId}
          onChange={(event) => {
            setCentreId(event.target.value);
            const centre = centres.find((item) => item.id === event.target.value);
            if (centre) {
              setAmount(String(recommendedAmount(centre.ppi)));
            }
          }}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
        >
          {centres.map((centre) => (
            <option key={centre.id} value={centre.id}>
              {centre.name} (PPI {centre.ppi.toFixed(1)})
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <label htmlFor="alloc-amount" className="text-sm font-medium">
          Amount
        </label>
        <Input
          id="alloc-amount"
          type="number"
          min={1}
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
        {selected && (
          <p className="text-xs text-muted-foreground">
            Recommended from PPI {selected.ppi.toFixed(1)}:{" "}
            {recommendedAmount(selected.ppi).toLocaleString("en-GB")}
          </p>
        )}
      </div>
      <div className="space-y-2">
        <label htmlFor="alloc-rationale" className="text-sm font-medium">
          Rationale
        </label>
        <Input
          id="alloc-rationale"
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Why this centre receives this allocation…"
          required
          minLength={3}
        />
      </div>
      <Button type="submit" disabled={allocate.isPending}>
        {allocate.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
        Allocate funds
      </Button>
      {allocate.isSuccess && (
        <p role="status" className="text-sm text-emerald-600 dark:text-emerald-400">
          Allocation recorded — the provider has been notified.
        </p>
      )}
      {allocate.isError && (
        <p role="alert" className="text-sm text-destructive">
          Allocation failed. Please try again.
        </p>
      )}
    </form>
  );
}

function recommendedAmount(ppi: number) {
  return Math.round((400_000 + 1_100_000 * (ppi / 100)) / 10_000) * 10_000;
}

function CentreDrillDown({ centreId, onClose }: { centreId: string; onClose: () => void }) {
  const detail = useQuery({
    queryKey: ["admin-provider", centreId],
    queryFn: async () => {
      const { fetchAdminProviderDetail } = await import("@/lib/api");
      return fetchAdminProviderDetail(centreId);
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Centre drill-down"
    >
      <Card className="max-h-[80dvh] w-full max-w-2xl overflow-y-auto">
        <CardHeader className="flex-row items-start justify-between space-y-0">
          <div>
            <CardTitle className="font-display text-xl">
              {detail.data?.centre.name ?? "Centre"}
            </CardTitle>
            <CardDescription>{detail.data?.centre.district}</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {detail.isPending || !detail.data ? (
            <Skeleton className="h-48 w-full" />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <Stat label="PPI" value={detail.data.ppi_score.toFixed(1)} />
                <Stat
                  label="Placement"
                  value={`${Math.round(detail.data.placement_rate * 100)}%`}
                />
                <Stat
                  label="Verification"
                  value={`${Math.round(detail.data.verification_rate * 100)}%`}
                />
                <Stat label="Certified" value={String(detail.data.certified)} />
              </div>
              <div>
                <h4 className="mb-1 text-sm font-semibold">Score history</h4>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {detail.data.score_history.map((score) => (
                    <li key={score.period}>
                      {score.period}: PPI {score.ppi_score.toFixed(1)} · placement{" "}
                      {Math.round(score.placement_rate * 100)}%
                    </li>
                  ))}
                </ul>
              </div>
              {detail.data.allocations.length > 0 && (
                <div>
                  <h4 className="mb-1 text-sm font-semibold">Allocations</h4>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {detail.data.allocations.map((allocation) => (
                      <li key={allocation.id}>
                        {allocation.amount.toLocaleString("en-GB")} — {allocation.rationale}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-display text-lg font-semibold">{value}</p>
    </div>
  );
}

function GapMatrixCard() {
  const gaps = useQuery({
    queryKey: ["admin-gaps"],
    queryFn: async () => {
      const { fetchGapReports } = await import("@/lib/api");
      return fetchGapReports();
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl">Curriculum-demand gap matrix</CardTitle>
        <CardDescription>Worst gaps first — demand skills each course misses.</CardDescription>
      </CardHeader>
      <CardContent>
        {gaps.isPending ? (
          <Skeleton className="h-48 w-full" />
        ) : (gaps.data?.length ?? 0) === 0 ? (
          <EmptyState icon={BarChart3} title="No gap data" />
        ) : (
          <ul className="space-y-2">
            {(gaps.data ?? []).map((row) => (
              <li
                key={row.course_id}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
              >
                <div>
                  <p className="font-medium">{row.title}</p>
                  <p className="text-xs text-muted-foreground">
                    Missing:{" "}
                    {row.missing_in_demand_skills.map((m) => m.skill).join(", ") || "—"}
                  </p>
                </div>
                <span className="rounded-full bg-destructive/10 px-2.5 py-0.5 text-xs font-semibold text-destructive">
                  {row.gap_score.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
