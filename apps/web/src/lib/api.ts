/**
 * Typed fetch client for the TrackSkill AI API.
 *
 * - The short-lived access token lives in memory only and is attached as a
 *   Bearer header.
 * - The long-lived refresh token is an httpOnly cookie managed by the API;
 *   on a 401 the client runs a single-flight refresh and retries once.
 * - Base URLs come from the environment:
 *     NEXT_PUBLIC_API_URL  e.g. http://localhost:8000
 *     NEXT_PUBLIC_WS_URL   e.g. ws://localhost:8000/ws
 */

import type {
  AuthTokens,
  DemoAccount,
  TraineeMessage,
  TraineeProfile,
  TracerRunSummary,
  UserPublic,
  UserRole,
} from "@/types/api";

const RAW_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const RAW_WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "";

export const API_URL = RAW_API_URL.replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(status: number, message: string, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export interface RequestOptions {
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Ensures the in-memory access token is fresh (single-flight refresh). */
export async function ensureFreshToken(): Promise<boolean> {
  return refreshAccessToken();
}

const authExpiredListeners = new Set<() => void>();

/** Register a callback fired when the session cannot be restored. */
export function onAuthExpired(listener: () => void): () => void {
  authExpiredListeners.add(listener);
  return () => {
    authExpiredListeners.delete(listener);
  };
}

// Endpoints whose own 401 responses must never trigger a refresh round-trip.
const AUTH_PATHS = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"];

let refreshInFlight: Promise<boolean> | null = null;

async function requestRefresh(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      cache: "no-store",
    });
    if (!response.ok) {
      return false;
    }
    const data = (await response.json()) as { access_token: string };
    accessToken = data.access_token;
    return true;
  } catch {
    return false;
  }
}

function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = requestRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

interface InternalOptions extends RequestOptions {
  method?: string;
  body?: unknown;
  isRetry?: boolean;
}

async function request<T>(path: string, options: InternalOptions = {}): Promise<T> {
  const { method = "GET", body, headers, signal, isRetry = false } = options;

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "include",
    cache: "no-store",
    signal,
  });

  if (
    response.status === 401 &&
    !isRetry &&
    !AUTH_PATHS.some((authPath) => path.startsWith(authPath))
  ) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return request<T>(path, { ...options, isRetry: true });
    }
    accessToken = null;
    authExpiredListeners.forEach((listener) => listener());
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    let details: unknown = null;
    try {
      const problem = await response.json();
      details = problem;
      if (typeof problem?.detail === "string") {
        message = problem.detail;
      }
    } catch {
      // The response had no JSON body; keep the generic message.
    }
    throw new ApiError(response.status, message, details);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: "DELETE" }),
};

export function getApiUrl(): string {
  return API_URL;
}

/**
 * Build the WebSocket URL for a channel.
 *
 * NEXT_PUBLIC_WS_URL may be the full endpoint (ws://host/ws) or just the
 * origin (ws://host) — in the latter case /ws is appended. When unset, the
 * URL is derived from the API base URL.
 */
export function getWsUrl(channel = "global"): string {
  let base = RAW_WS_URL.trim();
  if (!base) {
    base = `${API_URL.replace(/^http/, "ws")}/ws`;
  }
  base = base.replace(/\/+$/, "");
  if (!/\/ws$/.test(base)) {
    base = `${base}/ws`;
  }
  return `${base}?channel=${encodeURIComponent(channel)}`;
}

// ── Auth endpoints ───────────────────────────────────────────────────────────

export interface SignUpInput {
  name: string;
  email: string;
  password: string;
  role: UserRole;
  phone?: string;
  district?: string;
  centre_code?: string;
  company_name?: string;
  company_district?: string;
  consent_channels?: string[];
}

export async function login(email: string, password: string): Promise<AuthTokens> {
  return api.post<AuthTokens>("/auth/login", { email, password });
}

export async function requestPasswordReset(
  email: string,
): Promise<{ status: string; message: string; reset_link?: string }> {
  return api.post("/auth/forgot-password", { email });
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<{ status: string; message: string }> {
  return api.post("/auth/reset-password", { token, new_password: newPassword });
}

export async function register(input: SignUpInput): Promise<AuthTokens> {
  return api.post<AuthTokens>("/auth/register", input);
}

export async function fetchMe(): Promise<UserPublic> {
  return api.get<UserPublic>("/auth/me");
}

export async function logout(): Promise<void> {
  await api.post<{ detail: string }>("/auth/logout");
}

export async function fetchDemoAccounts(): Promise<DemoAccount[] | null> {
  try {
    return await api.get<DemoAccount[]>("/auth/demo-accounts");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function fetchMyTraineeProfile(): Promise<TraineeProfile> {
  return api.get<TraineeProfile>("/trainees/me");
}

// ── Contact endpoint ─────────────────────────────────────────────────────────

export interface ContactPayload {
  name: string;
  email: string;
  organisation?: string;
  role: "PROVIDER" | "TRAINEE" | "EMPLOYER" | "ADMIN" | "OTHER";
  message: string;
}

export async function submitContact(
  payload: ContactPayload,
): Promise<{ status: string; id: string; message: string }> {
  return api.post("/contact", payload);
}

// ── Tracer endpoints ─────────────────────────────────────────────────────────

export async function fetchTraineeMessages(): Promise<TraineeMessage[]> {
  return api.get<TraineeMessage[]>("/trainee/messages");
}

export interface TracerReplyPayload {
  employment_status: "EMPLOYED" | "SELF_EMPLOYED" | "UNEMPLOYED" | "FURTHER_STUDY";
  job_title?: string;
  monthly_wage?: number;
}

export async function respondFollowupText(
  followupId: string,
  message: string,
): Promise<{ needs_review: boolean; confidence: number; parsed: Record<string, unknown> }> {
  return api.post(`/trainee/followups/${followupId}/respond/text`, { message });
}

export async function respondFollowupStructured(
  followupId: string,
  payload: TracerReplyPayload,
): Promise<{ followup_id: string; state: string }> {
  return api.post(`/trainee/followups/${followupId}/respond`, payload);
}

export async function runTracerNow(): Promise<TracerRunSummary> {
  return api.post<TracerRunSummary>("/admin/tracer/run");
}

// ── Admin endpoints ──────────────────────────────────────────────────────────

export async function fetchAdminOverview(): Promise<AdminOverview> {
  return api.get("/admin/overview");
}

export async function fetchAdminProviders(): Promise<LeaderboardRow[]> {
  return api.get("/admin/providers");
}

export async function fetchAdminProviderDetail(
  centreId: string,
): Promise<AdminProviderDetail> {
  return api.get(`/admin/providers/${centreId}`);
}

export async function fetchGapReports(): Promise<GapReportRow[]> {
  return api.get("/admin/curriculum-gaps");
}

export async function fetchEvents(limit: number): Promise<EventItem[]> {
  return api.get(`/admin/events?limit=${limit}`);
}

export async function submitAllocation(payload: {
  centre_id: string;
  amount: number;
  rationale: string;
}): Promise<{ allocation_id: string; amount: number; rationale: string }> {
  return api.post("/admin/allocations", payload);
}

export async function resetDemoData(): Promise<{ status: string; users: number }> {
  return api.post("/admin/demo/reset");
}

export async function runAnomalyScan(): Promise<{
  raised: { rule: string }[];
  raised_count: number;
}> {
  return api.post("/admin/anomalies/scan");
}

// ── Admin types ──────────────────────────────────────────────────────────────

export interface AdminOverview {
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

export interface LeaderboardRow {
  centre_id: string;
  centre_name: string;
  district: string;
  rank: number;
  ppi_score: number;
  placement_rate: number;
  verification_rate: number;
  response_rate: number;
}

export interface AdminProviderDetail {
  centre: { id: string; name: string; district: string };
  enrolled: number;
  certified: number;
  placement_rate: number;
  verification_rate: number;
  ppi_score: number;
  score_history: {
    period: string;
    ppi_score: number;
    placement_rate: number;
    verification_rate: number;
  }[];
  allocations: { id: string; amount: number; rationale: string; decided_at: string | null }[];
}

export interface GapReportRow {
  course_id: string;
  title: string;
  sector: string;
  centre_name: string;
  district: string;
  course_skills: string[];
  coverage: number;
  gap_score: number;
  missing_in_demand_skills: { skill: string; demand_score: number }[];
  suggested_modules: string[];
}

export interface EventItem {
  id: string;
  type: string;
  actor_user_id: string | null;
  actor_role: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}


// ── Notifications ────────────────────────────────────────────────────────────

export interface NotificationItem {
  id: string;
  title: string;
  body: string;
  link: string | null;
  read: boolean;
  created_at: string | null;
}

export async function fetchNotifications(): Promise<{
  unread: number;
  items: NotificationItem[];
}> {
  return api.get("/notifications");
}

export async function markNotificationRead(id: string): Promise<void> {
  await api.post(`/notifications/${id}/read`);
}

export async function markAllNotificationsRead(): Promise<void> {
  await api.post("/notifications/read-all");
}

// ── Search ───────────────────────────────────────────────────────────────────

export interface SearchResult {
  type: string;
  label: string;
  detail: string | null;
}

export async function globalSearch(q: string): Promise<{ results: SearchResult[] }> {
  return api.get(`/search?q=${encodeURIComponent(q)}`);
}

// ── Trainee employment + assessment ─────────────────────────────────────────

export interface EmploymentSelfReport {
  employment_status: "EMPLOYED" | "SELF_EMPLOYED" | "UNEMPLOYED" | "FURTHER_STUDY";
  job_title: string;
  monthly_wage: number;
  started_on?: string;
  employer_id?: string;
}

export async function reportEmployment(payload: EmploymentSelfReport): Promise<{
  employment_record_id: string;
  verification_id: string;
  verified: boolean;
}> {
  return api.post("/trainee/employment", payload);
}

export async function assessSkills(payload: {
  self_reported_skills?: string[];
  free_text?: string;
}): Promise<{
  profile: { skill: string; sector: string; confidence: number }[];
  role_matches: { title: string; sector: string; score: number; explanation: string }[];
  mode: string;
}> {
  return api.post("/trainee/skills/assessment", payload);
}

// ── Provider extras ──────────────────────────────────────────────────────────

export interface ProviderCourse {
  id: string;
  title: string;
  sector: string;
}

export async function fetchProviderCourses(): Promise<ProviderCourse[]> {
  return api.get("/provider/courses");
}

export interface ProviderOverview {
  centre: { id: string; name: string; district: string };
  enrolled: number;
  certified: number;
  dropped: number;
  placements: number;
  consent_rate: number;
  response_rate: number;
  placement_rate: number;
  retention_3m: number;
  retention_6m: number;
  retention_12m: number;
  ppi_score: number;
  ppi_rank: number;
  total_centres: number;
}

export interface ProviderTraineeRow {
  id: string;
  name: string;
  email: string;
  course_id: string;
  course_title: string | null;
  status: string;
  enrolled_on: string;
  certified_on: string | null;
  consent_active: boolean;
}

export interface ProviderFollowupItem {
  followup_id: string;
  trainee_id: string;
  trainee_name: string;
  milestone: string;
  due_on: string;
  channel: string;
  state?: string;
  raw_text?: string;
  parsed?: Record<string, unknown>;
}

export interface ProviderFollowups {
  overdue: ProviderFollowupItem[];
  due_soon: ProviderFollowupItem[];
  manual_review: ProviderFollowupItem[];
}

export async function fetchProviderOverview(): Promise<ProviderOverview> {
  return api.get("/provider/overview");
}

export async function fetchProviderTrainees(): Promise<ProviderTraineeRow[]> {
  return api.get("/provider/trainees");
}

export async function fetchProviderFollowups(): Promise<ProviderFollowups> {
  return api.get("/provider/followups");
}

export async function certifyTrainee(traineeId: string): Promise<{
  trainee_id: string;
  certified_on: string;
  consent_active: boolean;
  followups_scheduled: number;
}> {
  return api.patch(`/provider/trainees/${traineeId}/certify`, {});
}

export async function enrolTrainee(payload: {
  name: string;
  email: string;
  phone: string;
  course_id: string;
  centre_id?: string;
}): Promise<{ trainee: { id: string }; temporary_password: string }> {
  return api.post("/provider/trainees", payload);
}

export async function fetchProviderGapAlerts(): Promise<
  { course_id: string; title: string; gap_score: number; missing_in_demand_skills: { skill: string; demand_score: number }[]; suggested_modules: string[] }[]
> {
  return api.get("/provider/curriculum-gaps");
}

// ── Employer extras ──────────────────────────────────────────────────────────

export interface EmployerImpact {
  hires: number;
  verified_hires: number;
  working: number;
  retention_3m: number;
  retention_6m: number;
  retention_12m: number;
  avg_monthly_wage: number;
}

export async function fetchEmployerImpact(): Promise<EmployerImpact> {
  return api.get("/employer/impact");
}

export async function fetchVerifications(
  status?: "pending" | "confirmed" | "disputed",
): Promise<VerificationRow[]> {
  const params = status ? `?status=${status}` : "";
  return api.get(`/employer/verifications${params}`);
}

export async function markConfirmed(
  verificationId: string,
): Promise<{ verification_id: string; verified: boolean }> {
  return api.post(`/employer/verifications/${verificationId}/confirm`);
}

export async function markDisputed(
  verificationId: string,
  reason: string,
): Promise<{ verification_id: string; employer_signal: string }> {
  return api.post(`/employer/verifications/${verificationId}/dispute`, { reason });
}

export interface VerificationRow {
  verification_id: string;
  trainee_name: string;
  employment_status: string;
  job_title: string | null;
  monthly_wage: number | null;
  trainee_signal: string;
}

export interface MaskedContact {
  email: string | null;
  phone: string | null;
}

export interface TalentPoolRow {
  skill: string;
  trainee_count: number;
  districts: string[];
  trainee_names: string[];
  contacts: MaskedContact[];
  match_score: number;
}

export async function fetchTalentPool(
  skill?: string,
  district?: string,
): Promise<TalentPoolRow[]> {
  const params = new URLSearchParams();
  if (skill) params.set("skill", skill);
  if (district) params.set("district", district);
  return api.get(`/employer/talent-pool?${params.toString()}`);
}

// ── Admin extras ─────────────────────────────────────────────────────────────

export interface GapReportRow {
  course_id: string;
  title: string;
  sector: string;
  centre_name: string;
  district: string;
  course_skills: string[];
  coverage: number;
  gap_score: number;
  missing_in_demand_skills: { skill: string; demand_score: number }[];
  suggested_modules: string[];
}

// ── Web push (Phase 10) ──────────────────────────────────────────────────────

export interface PushSubscriptionPayload {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent: string;
}

/** VAPID public key the browser needs to create a push subscription. */
export async function fetchPushPublicKey(): Promise<string> {
  return api.get<{ public_key: string }>("/push/public-key").then((data) => data.public_key);
}

export function savePushSubscription(subscription: PushSubscriptionPayload): Promise<{ status: string }> {
  return api.post("/push/subscriptions", subscription);
}

export function deletePushSubscription(endpoint: string): Promise<{ status: string }> {
  return api.post("/push/subscriptions/delete", { endpoint });
}

/** Ask the API to send a test notification to all of my devices. */
export function sendTestPush(): Promise<{ sent: number; failed: number; pruned: number }> {
  return api.post("/push/test");
}

// ── Data rights (Phase 11) ───────────────────────────────────────────────────

/** DPDP-aligned data access right: everything stored about the signed-in
 * trainee, as one JSON document. */
export function exportMyData(): Promise<Record<string, unknown>> {
  return api.get("/trainee/me/export");
}

/** DPDP-aligned erasure right: permanently deletes the account. */
export function deleteMyData(): Promise<{ status: string; erased: Record<string, number> }> {
  return api.post("/trainee/me/delete", { confirm: true });
}
