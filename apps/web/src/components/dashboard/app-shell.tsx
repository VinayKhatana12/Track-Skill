"use client";

import { useQueryClient } from "@tanstack/react-query";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConnectionPill } from "@/components/dashboard/connection-pill";
import { GlobalSearch } from "@/components/dashboard/global-search";
import { NotificationsBell } from "@/components/dashboard/notifications-bell";
import { ProfileMenu } from "@/components/dashboard/profile-menu";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { useRealtimeConnection } from "@/hooks/use-realtime-connection";
import { useAuthStore } from "@/stores/auth-store";
import { useRealtimeStore } from "@/stores/realtime-store";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/types/api";

const ROLE_NAV: Record<UserRole, { id: string; label: string }[]> = {
  PROVIDER: [
    { id: "overview", label: "Overview" },
    { id: "trainees", label: "Trainees" },
    { id: "followups", label: "Follow-ups" },
    { id: "insights", label: "Insights" },
  ],
  TRAINEE: [
    { id: "journey", label: "My Journey" },
    { id: "consent", label: "Consent" },
    { id: "messages", label: "Messages" },
    { id: "skills", label: "Skills" },
  ],
  EMPLOYER: [
    { id: "verify", label: "Verify" },
    { id: "hires", label: "Hires" },
    { id: "talent", label: "Talent pool" },
    { id: "impact", label: "Impact" },
  ],
  ADMIN: [
    { id: "governance", label: "Governance" },
    { id: "providers", label: "Providers" },
    { id: "gaps", label: "Gaps" },
    { id: "activity", label: "Activity" },
  ],
};

export function DashboardShell({
  children,
  role,
  headline,
  subheading,
}: {
  children: React.ReactNode;
  role: UserRole;
  headline: string;
  subheading: string;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const status = useAuthStore((state) => state.status);
  const bootstrap = useAuthStore((state) => state.bootstrap);
  const connected = useRealtimeStore((state) => state.connected);
  const [collapsed, setCollapsed] = useState(false);

  useRealtimeConnection(status === "authenticated");

  useEffect(() => {
    if (status === "idle") {
      void bootstrap();
    }
  }, [status, bootstrap]);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status !== "authenticated" || !user) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background text-muted-foreground">
        <p role="status">
          {status === "loading" ? "Loading your workspace…" : "Redirecting to sign-in…"}
        </p>
      </div>
    );
  }

  const firstName = (user.name ?? "").split(" ")[0];
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const sections = ROLE_NAV[role];

  const mobileNavigate = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="flex min-h-dvh bg-background">
      {/* Desktop sidebar */}
      <aside
        data-collapsed={collapsed || undefined}
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-border/70 bg-card transition-[width] md:flex",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <div
          className={cn(
            "flex h-16 items-center border-b border-border/60",
            collapsed ? "justify-center px-2" : "px-4",
          )}
        >
          <Link href="/" aria-label="TrackSkill AI home" className="flex items-center">
            <Logo withWordmark={!collapsed} />
          </Link>
        </div>
        <nav aria-label="Dashboard sections" className="flex-1 space-y-1 p-2">
          {sections.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              title={section.label}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                collapsed && "justify-center px-2",
              )}
            >
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-marigold-400" />
              {!collapsed && <span>{section.label}</span>}
            </a>
          ))}
        </nav>
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex w-full items-center justify-center gap-2 border-t border-border/60 py-3 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" aria-hidden />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4" aria-hidden />
              <span className="text-xs">Collapse</span>
            </>
          )}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar — its own safe-area top padding so the translucent iOS
            status bar in standalone mode never covers the controls. */}
        <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 pt-[env(safe-area-inset-top)] backdrop-blur">
          <div className="flex h-16 items-center gap-3 px-4">
            <button
              type="button"
              onClick={() => setCollapsed((value) => !value)}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              className="hidden rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground md:inline-flex"
            >
              {collapsed ? (
                <PanelLeftOpen className="h-4 w-4" aria-hidden />
              ) : (
                <PanelLeftClose className="h-4 w-4" aria-hidden />
              )}
            </button>
            <Link href="/login" aria-label="TrackSkill AI home" className="md:hidden">
              <Logo withWordmark={false} />
            </Link>

            <div className="hidden min-w-0 flex-1 sm:block">
              <GlobalSearch />
            </div>

            <div className="ml-auto flex items-center gap-2 sm:gap-3">
              <ConnectionPill connected={connected} />
              <ThemeToggle />
              <NotificationsBell />
              <ProfileMenu />
            </div>
          </div>
        </header>

        {/* Page header */}
        <div className="border-b border-border/70 bg-muted/30 px-4 py-6 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
              {greeting}, {firstName} · {user.role}
            </p>
            <h1 className="mt-1 font-display text-2xl font-semibold tracking-tight sm:text-3xl">
              {headline}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">{subheading}</p>
          </div>
        </div>

        {/* Content */}
        <main className="flex-1 pb-24 md:pb-10">
          <div className="mx-auto max-w-6xl space-y-10 px-4 py-8 sm:px-6">{children}</div>
        </main>
      </div>

      {/* Mobile bottom tabs — sized above the home-bar safe area */}
      <nav
        aria-label="Dashboard sections"
        className="fixed bottom-0 left-0 right-0 z-40 grid grid-cols-4 border-t border-border bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {sections.map((section) => (
          <button
            key={section.id}
            type="button"
            onClick={() => mobileNavigate(section.id)}
            className="flex min-h-[52px] flex-col items-center justify-center gap-0.5 py-2 text-[10px] text-muted-foreground hover:text-foreground"
          >
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-marigold-400" />
            {section.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
