"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PullToRefresh } from "@/components/pwa/pull-to-refresh";
import { useRealtimeConnection } from "@/hooks/use-realtime-connection";
import { useAuthStore } from "@/stores/auth-store";
import { useRealtimeStore } from "@/stores/realtime-store";

/** Authenticated shell wrapper: guards unauthenticated visitors, opens the
 * realtime socket and invalidates React Query caches when domain events
 * arrive. The visual chrome (sidebar, top bar, tabs) is rendered per role
 * page via DashboardShell. */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const status = useAuthStore((state) => state.status);
  const bootstrap = useAuthStore((state) => state.bootstrap);

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

  // Any domain event may change data anywhere — invalidate all queries.
  useEffect(() => {
    const unsubscribe = useRealtimeStore.subscribe((state) => {
      if (state.lastEvent) {
        void queryClient.invalidateQueries();
      }
    });
    return unsubscribe;
  }, [queryClient]);

  if (status !== "authenticated" || !user) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background text-muted-foreground">
        <p role="status">
          {status === "loading" ? "Loading your workspace…" : "Redirecting to sign-in…"}
        </p>
      </div>
    );
  }

  return (
    <PullToRefresh>
      {children}
    </PullToRefresh>
  );
}
