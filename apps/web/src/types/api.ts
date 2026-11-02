/** Shared API response and realtime event types. */

export type UserRole = "PROVIDER" | "TRAINEE" | "EMPLOYER" | "ADMIN";

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

export interface ReadinessResponse extends HealthResponse {
  database: boolean;
}

export interface UserPublic {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  is_demo: boolean;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserPublic;
}

export interface DemoAccount {
  role: UserRole;
  email: string;
  password: string;
  dashboard: string;
}

export type TraineeStatus = "ENROLLED" | "CERTIFIED" | "DROPPED";

export interface TraineeProfile {
  id: string;
  user_id: string;
  centre_id: string;
  course_id: string;
  district: string;
  gender: string;
  enrolled_on: string;
  certified_on: string | null;
  status: TraineeStatus;
}

export interface RealtimeEvent {
  event: string;
  payload: Record<string, unknown>;
}

export type RealtimeStatus = "connecting" | "online" | "offline";

export type TracerChannel = "WHATSAPP" | "IVR" | "SMS";

export type FollowUpState = "SCHEDULED" | "SENT" | "RESPONDED" | "MISSED";

export interface TraineeMessage {
  followup_id: string;
  milestone: string;
  channel: TracerChannel;
  kind: "chat" | "call";
  state: FollowUpState;
  due_on: string;
  sent_at: string | null;
  attempts: number;
  message: string;
  responded: boolean;
  needs_review: boolean;
  response: {
    employment: string | null;
    job_title: string | null;
    wage: number | null;
    raw_text: string | null;
  } | null;
}

export interface TracerRunSummary {
  fast_forwarded: number;
  created: number;
  sent: { followup_id: string; trainee_name: string; milestone: string; channel: string }[];
  missed: unknown[];
  sent_count: number;
  missed_count: number;
}
