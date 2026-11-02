/**
 * Client-side session hints for the role-aware middleware.
 *
 * These cookies are convenience-only (readable, unsigned): they let
 * middleware.ts route between dashboards instantly. Real authorization is
 * enforced by the backend on every request.
 */
const PERSISTENT_MAX_AGE = 60 * 60 * 24 * 7; // 7 days, mirrors the refresh cookie

export function setAuthCookies(role: string, remember = true): void {
  // "Remember me" keeps the routing hints for a week; without it they are
  // session cookies that vanish when the browser closes.
  const lifetime = remember ? `; max-age=${PERSISTENT_MAX_AGE}` : "";
  document.cookie = `ts_auth=1; path=/${lifetime}; samesite=lax`;
  document.cookie = `ts_role=${encodeURIComponent(role)}; path=/${lifetime}; samesite=lax`;
}

export function clearAuthCookies(): void {
  document.cookie = "ts_auth=; path=/; max-age=0";
  document.cookie = "ts_role=; path=/; max-age=0";
}
