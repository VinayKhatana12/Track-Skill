import { NextResponse, type NextRequest } from "next/server";

const ROLE_SEGMENTS = new Set(["provider", "trainee", "employer", "admin"]);

/**
 * UX-level route protection: unauthenticated visitors are routed to
 * /login, and signed-in users land on (or are redirected to) their own
 * role dashboard. The ts_* cookies are readable hints set at login — the
 * API enforces real authorization on every request.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isAuthenticated = request.cookies.get("ts_auth")?.value === "1";
  const role = request.cookies.get("ts_role")?.value;
  const activeRole = role !== undefined && ROLE_SEGMENTS.has(role.toLowerCase()) ? role.toLowerCase() : null;

  if (pathname === "/login" || pathname === "/register") {
    if (isAuthenticated && activeRole) {
      return NextResponse.redirect(new URL(`/dashboard/${activeRole}`, request.url));
    }
    return NextResponse.next();
  }

  // Everything under /dashboard/**
  if (!isAuthenticated || !activeRole) {
    const signInUrl = new URL("/login", request.url);
    signInUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(signInUrl);
  }

  const requestedSegment = pathname.split("/")[2]?.toLowerCase();
  if (requestedSegment && requestedSegment !== activeRole) {
    // A signed-in trainee poking at /dashboard/admin goes home.
    return NextResponse.redirect(new URL(`/dashboard/${activeRole}`, request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/register"],
};
