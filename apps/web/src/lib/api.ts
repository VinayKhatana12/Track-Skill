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
