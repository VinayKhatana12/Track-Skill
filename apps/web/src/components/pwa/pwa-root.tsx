"use client";

/** Single mount point for all PWA UX: service-worker registration with the
 * "Refresh to update" toast, the custom install prompt (with an iOS Safari
 * hint), "App installed" detection, the push opt-in shown only after login,
 * and offline follow-up sync messages from the service worker. */

import { useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, Download, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { ensureFreshToken, getAccessToken } from "@/lib/api";
import {
  enablePush,
  isIosSafari,
  isStandalone,
  pushPermission,
  pushSupported,
  registerServiceWorker,
  requestQueueReplay,
} from "@/lib/push-client";
import { useAuthStore } from "@/stores/auth-store";

type Banner =
  | { kind: "none" }
  | { kind: "update" }
  | { kind: "install" }
  | { kind: "ios-install" }
  | { kind: "push" }
  | { kind: "message"; text: string };

type InstallPromptEvent = Event & { prompt: () => Promise<void> };

const INSTALL_DISMISS_KEY = "pwa-install-dismissed";
const PUSH_CHOICE_KEY = "pwa-push-choice";

export function PwaRoot() {
  const queryClient = useQueryClient();
  const status = useAuthStore((state) => state.status);
  const [banner, setBanner] = useState<Banner>({ kind: "none" });
  const [waitingWorker, setWaitingWorker] = useState<ServiceWorker | null>(null);
  const [promptEvent, setPromptEvent] = useState<InstallPromptEvent | null>(null);
  const [busy, setBusy] = useState(false);

  /* Service worker registration + update detection. */
  useEffect(() => {
    void registerServiceWorker().then((registration) => {
      registration?.addEventListener("updatefound", () => {
        const worker = registration.installing;
        worker?.addEventListener("statechange", () => {
          if (worker.state === "installed" && navigator.serviceWorker.controller) {
            setWaitingWorker(worker);
          }
        });
      });
      if (registration?.waiting && navigator.serviceWorker.controller) {
        setWaitingWorker(registration.waiting);
      }
    });
  }, []);

  /* Update toast. */
  useEffect(() => {
    if (waitingWorker) {
      setBanner({ kind: "update" });
    }
  }, [waitingWorker]);

  /* Install prompt capture (Chromium) / hint (iOS Safari) + installed event. */
  useEffect(() => {
    if (localStorage.getItem(INSTALL_DISMISS_KEY) === "1" || isStandalone()) {
      return;
    }
    const onBeforeInstall = (event: Event) => {
      event.preventDefault();
      setPromptEvent(event as InstallPromptEvent);
      setBanner({ kind: "install" });
    };
    const onInstalled = () => {
      setPromptEvent(null);
      setBanner({ kind: "message", text: "TrackSkill AI installed — find it in your app list." });
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);
    // iOS Safari never fires beforeinstallprompt — offer the manual route.
    const iosTimer = isIosSafari()
      ? window.setTimeout(() => setBanner({ kind: "ios-install" }), 2000)
      : undefined;
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
      if (iosTimer) {
        window.clearTimeout(iosTimer);
      }
    };
  }, []);

  /* Push opt-in — only offered once signed in, never on first load. */
  useEffect(() => {
    if (status !== "authenticated") {
      return;
    }
    if (localStorage.getItem(PUSH_CHOICE_KEY) || !pushSupported()) {
      return;
    }
    if (pushPermission() !== "default") {
      return;
    }
    const timer = window.setTimeout(
      () => setBanner((current) => (current.kind === "none" ? { kind: "push" } : current)),
      1500,
    );
    return () => window.clearTimeout(timer);
  }, [status]);

  /* Offline follow-up queue messages from the service worker. */
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data as { type?: string; status?: number } | null;
      if (!data?.type) {
        return;
      }
      if (data.type === "followup-synced") {
        void queryClient.invalidateQueries();
        setBanner({ kind: "message", text: "Offline response synced with the server." });
      } else if (data.type === "followup-queued") {
        setBanner({
          kind: "message",
          text: "You are offline — the response will send automatically once you reconnect.",
        });
      } else if (data.type === "followup-failed") {
        setBanner({
          kind: "message",
          text: "An offline response could not be delivered after several attempts.",
        });
      } else if (data.type === "followup-auth-needed") {
        void ensureFreshToken().then((fresh) => {
          if (!fresh) {
            return;
          }
          const token = getAccessToken();
          void navigator.serviceWorker.ready.then((registration) => {
            registration.active?.postMessage({ type: "QUEUE_TOKEN", token });
          });
        });
      }
    };
    navigator.serviceWorker?.addEventListener("message", onMessage);
    const onOnline = () => requestQueueReplay();
    window.addEventListener("online", onOnline);
    return () => {
      navigator.serviceWorker?.removeEventListener("message", onMessage);
      window.removeEventListener("online", onOnline);
    };
  }, [queryClient]);

  const dismiss = useCallback((storageKey?: string) => {
    if (storageKey) {
      localStorage.setItem(storageKey, "1");
    }
    setBanner({ kind: "none" });
  }, []);

  const applyUpdate = () => {
    waitingWorker?.postMessage({ type: "SKIP_WAITING" });
    navigator.serviceWorker.addEventListener(
      "controllerchange",
      () => window.location.reload(),
      { once: true },
    );
  };

  const runInstall = async () => {
    if (!promptEvent) {
      return;
    }
    setBusy(true);
    try {
      await promptEvent.prompt();
    } finally {
      setBusy(false);
      setPromptEvent(null);
      setBanner({ kind: "none" });
    }
  };

  const turnOnPush = async () => {
    setBusy(true);
    const result = await enablePush();
    localStorage.setItem(PUSH_CHOICE_KEY, result);
    setBusy(false);
    setBanner({
      kind: "message",
      text:
        result === "granted"
          ? "Notifications are on — tracers, verifications and fund decisions will reach your device."
          : result === "denied"
            ? "Notifications are blocked in the browser — change it in site settings."
            : "Notifications are not available on this device.",
    });
  };

  if (banner.kind === "none") {
    return null;
  }

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-[60] flex justify-center px-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] sm:justify-end sm:px-6"
      role="status"
      aria-live="polite"
    >
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-4 shadow-lg">
        {banner.kind === "update" && (
          <CardRow
            icon={<RefreshCw className="h-5 w-5 text-primary" aria-hidden />}
            title="A new version is ready"
            body="Refresh to update TrackSkill AI."
            actionLabel="Refresh to update"
            onAction={applyUpdate}
            onDismiss={() => setBanner({ kind: "none" })}
          />
        )}
        {banner.kind === "install" && (
          <CardRow
            icon={<Download className="h-5 w-5 text-primary" aria-hidden />}
            title="Install TrackSkill AI"
            body="Works offline and opens in its own window."
            actionLabel={busy ? "Installing…" : "Install"}
            onAction={() => void runInstall()}
            onDismiss={() => dismiss(INSTALL_DISMISS_KEY)}
            busy={busy}
          />
        )}
        {banner.kind === "ios-install" && (
          <CardRow
            icon={<Download className="h-5 w-5 text-primary" aria-hidden />}
            title="Add to Home Screen"
            body="Tap Share, then “Add to Home Screen” to install TrackSkill AI."
            onDismiss={() => dismiss(INSTALL_DISMISS_KEY)}
          />
        )}
        {banner.kind === "push" && (
          <CardRow
            icon={<Bell className="h-5 w-5 text-primary" aria-hidden />}
            title="Turn on notifications?"
            body="Milestone tracers, verification results and fund decisions — straight to your device."
            actionLabel={busy ? "Enabling…" : "Turn on"}
            onAction={() => void turnOnPush()}
            onDismiss={() => {
              localStorage.setItem(PUSH_CHOICE_KEY, "off");
              setBanner({ kind: "none" });
            }}
            busy={busy}
          />
        )}
        {banner.kind === "message" && (
          <CardRow
            icon={<CheckCheck className="h-5 w-5 text-primary" aria-hidden />}
            title={banner.text}
            onDismiss={() => setBanner({ kind: "none" })}
          />
        )}
      </div>
    </div>
  );
}

function CardRow({
  icon,
  title,
  body,
  actionLabel,
  onAction,
  onDismiss,
  busy = false,
}: {
  icon: React.ReactNode;
  title: string;
  body?: string;
  actionLabel?: string;
  onAction?: () => void;
  onDismiss: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{title}</p>
        {body && <p className="mt-0.5 text-xs text-muted-foreground">{body}</p>}
        {actionLabel && onAction && (
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={onAction}
              disabled={busy}
              className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {actionLabel}
            </button>
            <button
              type="button"
              onClick={onDismiss}
              className="inline-flex min-h-11 items-center gap-2 rounded-md border border-input px-4 text-sm font-medium hover:bg-accent"
            >
              Not now
            </button>
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <X className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
