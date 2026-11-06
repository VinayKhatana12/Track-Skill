"use client";

/** Browser-side Web Push plumbing: service worker registration, permission,
 * subscription management and small environment probes. */

import {
  deletePushSubscription,
  fetchPushPublicKey,
  getAccessToken,
  savePushSubscription,
} from "@/lib/api";

export function isStandalone(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: fullscreen)").matches ||
    // iOS Safari reports standalone via navigator
    Boolean((window.navigator as { standalone?: boolean }).standalone)
  );
}

export function isIosSafari(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const ua = window.navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) && !/CriOS|FxiOS/.test(ua);
}

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) {
    return null;
  }
  try {
    return await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  } catch {
    return null;
  }
}

/** Trigger a Background Sync replay of any offline follow-up responses. */
export function requestQueueReplay(): void {
  navigator.serviceWorker?.ready.then((registration) => {
    registration.active?.postMessage({ type: "REPLAY_NOW" });
  });
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const output = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) {
    output[index] = raw.charCodeAt(index);
  }
  return output;
}

/** Ask permission, subscribe to push and register the subscription with the
 * API. Returns "granted" | "denied" | "unsupported" | "error". */
export async function enablePush(): Promise<"granted" | "denied" | "unsupported" | "error"> {
  if (!pushSupported() || !getAccessToken()) {
    return "unsupported";
  }
  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      return "denied";
    }
    const registration = await navigator.serviceWorker.ready;
    const vapidPublicKey = await fetchPushPublicKey();
    const existing = await registration.pushManager.getSubscription();
    const subscription =
      existing ??
      (await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey) as unknown as BufferSource,
      }));
    const json = subscription.toJSON() as {
      endpoint: string;
      keys?: { p256dh?: string; auth?: string };
    };
    if (!json.keys?.p256dh || !json.keys?.auth) {
      return "error";
    }
    await savePushSubscription({
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
      user_agent: window.navigator.userAgent,
    });
    return "granted";
  } catch {
    return "error";
  }
}

/** Remove the browser subscription and tell the API to drop it. */
export async function disablePush(): Promise<void> {
  if (!pushSupported()) {
    return;
  }
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      const json = subscription.toJSON() as { endpoint?: string };
      await subscription.unsubscribe();
      if (json.endpoint) {
        await deletePushSubscription(json.endpoint);
      }
    }
  } catch {
    // best-effort cleanup
  }
}

export function pushPermission(): NotificationPermission | "unsupported" {
  if (typeof window === "undefined" || !("Notification" in window)) {
    return "unsupported";
  }
  return Notification.permission;
}
