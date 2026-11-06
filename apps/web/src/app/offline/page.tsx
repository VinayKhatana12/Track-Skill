import { WifiOff } from "lucide-react";
import type { Metadata } from "next";

import { RetryButton } from "./retry-button";

/** Offline fallback served by the service worker when a page is requested
 * with no network and no cached copy. Precached at SW install. */
export const metadata: Metadata = {
  title: "Offline",
};

export default function OfflinePage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-background px-6 text-center">
      <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-secondary">
        <WifiOff className="h-8 w-8 text-primary" aria-hidden />
      </span>
      <h1 className="mt-6 font-display text-2xl font-semibold">You are offline</h1>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        TrackSkill AI could not reach the network. Pages you visited recently and your
        dashboard shell still work offline — responses you submit are queued and sent
        automatically once you reconnect.
      </p>
      <RetryButton />
    </main>
  );
}
