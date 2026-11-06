/*
 * TrackSkill AI service worker.
 *
 * Strategies:
 * - App shell pages (navigations): network-first, every successful HTML
 *   response is cached; offline falls back to the cached page or /offline.
 * - Static assets (/_next/static, icons, splash, manifest): cache-first.
 * - Other same-origin GETs (RSC flights, prefetches): stale-while-revalidate.
 * - API GETs (the FastAPI origin): stale-while-revalidate with a 30-second
 *   freshness window — young entries are served from cache instantly while a
 *   background fetch refreshes them; older entries try the network first so
 *   dashboards stay live, falling back to cache when offline.
 * - Auth endpoints (/auth/*): never cached — login/refresh always hit the
 *   network so credentials can never be served from a stale copy.
 * - Offline follow-up responses: POSTs to /trainee/followups/{id}/respond are
 *   queued in IndexedDB and replayed by a Background Sync event, then the page
 *   is told via postMessage so it can refresh.
 *
 * Bump VERSION whenever the precache list changes; the browser detects SW
 * updates by byte-diff of this file and the page shows "Refresh to update".
 */

const VERSION = "trackskill-v1";
const PAGES_CACHE = `pages-${VERSION}`;
const STATIC_CACHE = `static-${VERSION}`;
const API_CACHE = `api-${VERSION}`;
const PAGES_CAP = 20;
const API_CAP = 150;
const API_FRESH_MS = 30_000;

const PRECACHE_URLS = [
  "/offline",
  "/dashboard",
  "/login",
  "/",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-192.png",
  "/icons/icon-maskable-512.png",
];

const STATIC_PATTERNS = [
  /^\/_next\/static\//,
  /^\/icons\//,
  /^\/splash\//,
  /^\/apple-touch-icon\.png$/,
  /^\/manifest\.webmanifest$/,
  /^\/favicon\./,
];

// Same-origin GETs that are neither static nor navigations (RSC flights etc.)
// use stale-while-revalidate.
const RSC_PATTERN = /^\/_next\//;

const RESPOND_PATTERN = /^\/trainee\/followups\/[0-9a-fA-F-]{36}\/respond$/;
const MAX_REPLAY_ATTEMPTS = 5;

/* ── IndexedDB: the offline follow-up queue ──────────────────────────────── */

const DB_NAME = "trackskill-sw";
const QUEUE_STORE = "queue";
const META_STORE = "meta";

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(QUEUE_STORE)) {
        db.createObjectStore(QUEUE_STORE, { autoIncrement: true });
      }
      if (!db.objectStoreNames.contains(META_STORE)) {
        db.createObjectStore(META_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function idbRun(storeName, mode, run) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    let result;
    try {
      result = run(store);
    } catch (error) {
      reject(error);
      return;
    }
    tx.oncomplete = () => resolve(result && result.result !== undefined ? result.result : result);
    tx.onerror = () => reject(tx.error);
  });
}

function queueAdd(item) {
  return idbRun(QUEUE_STORE, "readwrite", (store) => store.add(item));
}

function queueAll() {
  return idbRun(QUEUE_STORE, "readonly", (store) => store.getAll());
}

function queueAllKeys() {
  return idbRun(QUEUE_STORE, "readonly", (store) => store.getAllKeys());
}

function queueDelete(key) {
  return idbRun(QUEUE_STORE, "readwrite", (store) => store.delete(key));
}

function metaGet(key) {
  return idbRun(META_STORE, "readonly", (store) => store.get(key));
}

function metaSet(key, value) {
  return idbRun(META_STORE, "readwrite", (store) => store.put(value, key));
}

/* ── Small helpers ───────────────────────────────────────────────────────── */

async function putCapped(cacheName, request, response, cap) {
  const cache = await caches.open(cacheName);
  await cache.put(request, response);
  const keys = await cache.keys();
  if (keys.length > cap) {
    for (const staleKey of keys.slice(0, keys.length - cap)) {
      await cache.delete(staleKey);
    }
  }
}

function cacheable(response) {
  return response && response.ok && response.type !== "opaque";
}

function withAge(response) {
  const dateHeader = response.headers.get("date");
  const age = dateHeader ? Date.now() - new Date(dateHeader).getTime() : Infinity;
  return { response, age: Number.isFinite(age) ? age : 0 };
}

/** Stale-while-revalidate with a freshness window: a young cached entry is
 * answered immediately (revalidation continues in the background via
 * event.waitUntil); anything older tries the network first so live data
 * wins, falling back to cache when offline.
 *
 * Returns { respond, revalidate }: call event.respondWith(respond) and
 * event.waitUntil(revalidate) SYNCHRONOUSLY during event dispatch — calling
 * waitUntil after an await inside respondWith rejects the event. */
function staleWhileRevalidate(request, cacheName, cap, freshMs) {
  const revalidate = fetch(request)
    .then(async (response) => {
      if (cacheable(response)) {
        await putCapped(cacheName, request, response.clone(), cap);
      }
      return response;
    })
    .catch(() => null);

  const respond = (async () => {
    const cache = await caches.open(cacheName);
    const cached = withAge(await cache.match(request));
    if (cached.response && cached.age < freshMs) {
      return cached.response;
    }
    const network = await revalidate;
    if (network) {
      return network.clone();
    }
    return cached.response ?? null;
  })();

  return { respond, revalidate };
}

/* ── Install / activate ──────────────────────────────────────────────────── */

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(PAGES_CACHE);
      await Promise.allSettled(
        PRECACHE_URLS.map(async (url) => {
          const response = await fetch(new Request(url, { credentials: "same-origin" }));
          if (response.ok) {
            await cache.put(new Request(url), response);
          }
        }),
      );
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) {
        if (!key.endsWith(VERSION)) {
          await caches.delete(key);
        }
      }
      await self.clients.claim();
      await replayQueue().catch(() => undefined);
    })(),
  );
});

/* ── Fetch strategies ────────────────────────────────────────────────────── */

async function handleNavigation(request) {
  try {
    const response = await fetch(request);
    if (cacheable(response)) {
      await putCapped(PAGES_CACHE, request, response.clone(), PAGES_CAP);
    }
    return response;
  } catch {
    const cache = await caches.open(PAGES_CACHE);
    return (
      (await cache.match(request)) ??
      (await cache.match("/dashboard")) ??
      (await cache.match("/offline")) ??
      new Response(
        "<!doctype html><title>Offline</title><p>You are offline.</p>",
        { headers: { "Content-Type": "text/html" }, status: 503 },
      )
    );
  }
}

async function handleFollowupRespond(request) {
  try {
    return await fetch(request);
  } catch {
    const body = await request.clone().arrayBuffer();
    const headers = {};
    request.headers.forEach((value, key) => {
      if (["content-type", "authorization"].includes(key.toLowerCase())) {
        headers[key] = value;
      }
    });
    await queueAdd({
      url: request.url,
      headers,
      body,
      attempts: 0,
      created_at: new Date().toISOString(),
    });
    if (self.registration.sync) {
      try {
        await self.registration.sync.register("tsk-followup-replay");
      } catch {
        // Background Sync unavailable — the queue replays on next activate,
        // next online event or explicit REPLAY_NOW from the page.
      }
    }
    await notifyClients({ type: "followup-queued" });
    return new Response(JSON.stringify({ queued: true, offline: true }), {
      status: 202,
      headers: { "Content-Type": "application/json" },
    });
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" && !(request.method === "POST" && RESPOND_PATTERN.test(new URL(request.url).pathname))) {
    return; // all other mutations go straight to the network
  }

  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;
  const pathname = url.pathname;

  if (request.method === "POST" && RESPOND_PATTERN.test(pathname)) {
    event.respondWith(handleFollowupRespond(request));
    return;
  }

  if (pathname.startsWith("/auth/")) {
    return; // auth is network-only, never cached and never queued
  }

  if (request.mode === "navigate") {
    event.respondWith(handleNavigation(request));
    return;
  }

  if (!sameOrigin) {
    // Cross-origin API GET — stale-while-revalidate (handles the FastAPI data).
    if (pathname.startsWith("/ws")) {
      return;
    }
    const { respond, revalidate } = staleWhileRevalidate(request, API_CACHE, API_CAP, API_FRESH_MS);
    event.waitUntil(revalidate.then(() => undefined));
    event.respondWith(
      respond.then(
        (response) =>
          response ??
          new Response(JSON.stringify({ detail: "Offline and no cached data." }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }),
        () =>
          new Response(JSON.stringify({ detail: "Offline and no cached data." }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    return;
  }

  if (STATIC_PATTERNS.some((pattern) => pattern.test(pathname))) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(STATIC_CACHE);
        const cached = await cache.match(request);
        if (cached) {
          return cached;
        }
        const response = await fetch(request);
        if (cacheable(response)) {
          await cache.put(request, response.clone());
        }
        return response;
      })(),
    );
    return;
  }

  if (RSC_PATTERN.test(pathname) || request.headers.has("Next-Router-Prefetch")) {
    const { respond, revalidate } = staleWhileRevalidate(request, PAGES_CACHE, PAGES_CAP, 0);
    event.waitUntil(revalidate.then(() => undefined));
    event.respondWith(
      respond.then(
        (response) => response ?? new Response("{}", { status: 503, headers: { "Content-Type": "application/json" } }),
        () => new Response("{}", { status: 503, headers: { "Content-Type": "application/json" } }),
      ),
    );
  }
});

/* ── Background sync: replay offline follow-up responses ─────────────────── */

async function notifyClients(message) {
  const clients = await self.clients.matchAll({ includeUncontrolled: true });
  for (const client of clients) {
    client.postMessage(message);
  }
}

async function replayQueue() {
  const items = await queueAll();
  const keys = await queueAllKeys();
  let pendingAuth = false;

  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    const key = keys[index];
    try {
      const token = (await metaGet("replay-token")) || null;
      const headers = { ...item.headers };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const response = await fetch(item.url, {
        method: "POST",
        headers,
        body: item.body,
      });
      if (response.status === 401) {
        pendingAuth = true;
        await metaSet("replay-token", null);
        continue;
      }
      await queueDelete(key);
      await notifyClients({
        type: "followup-synced",
        url: item.url,
        status: response.status,
      });
    } catch {
      const attempts = (item.attempts ?? 0) + 1;
      await queueDelete(key);
      if (attempts >= MAX_REPLAY_ATTEMPTS) {
        await notifyClients({ type: "followup-failed", url: item.url });
      } else {
        await queueAdd({ ...item, attempts });
      }
    }
  }

  if (pendingAuth) {
    await notifyClients({ type: "followup-auth-needed" });
    if (self.registration.sync) {
      try {
        await self.registration.sync.register("tsk-followup-replay");
      } catch {
        // The page will send REPLAY_NOW once it refreshes the token.
      }
    }
  }
}

self.addEventListener("sync", (event) => {
  if (event.tag === "tsk-followup-replay") {
    event.waitUntil(replayQueue().catch(() => undefined));
  }
});

/* ── Push notifications ──────────────────────────────────────────────────── */

self.addEventListener("push", (event) => {
  let payload = { title: "TrackSkill AI", body: "You have a new update.", link: "/dashboard" };
  try {
    if (event.data) {
      payload = { ...payload, ...event.data.json() };
    }
  } catch {
    if (event.data) {
      payload.body = event.data.text();
    }
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: payload.event_id || payload.title,
      data: { url: payload.link || "/dashboard" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data?.url || "/dashboard";
  event.waitUntil(
    (async () => {
      const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of clients) {
        if (client.url.includes(self.location.origin)) {
          await client.focus();
          if (client.navigate) {
            await client.navigate(target).catch(() => undefined);
          }
          return;
        }
      }
      await self.clients.openWindow(target);
    })(),
  );
});

/* ── Messages from the page ──────────────────────────────────────────────── */

self.addEventListener("message", (event) => {
  const type = event.data?.type;
  if (type === "SKIP_WAITING") {
    self.skipWaiting();
  } else if (type === "REPLAY_NOW") {
    event.waitUntil(replayQueue().catch(() => undefined));
  } else if (type === "QUEUE_TOKEN") {
    event.waitUntil(
      (async () => {
        await metaSet("replay-token", event.data.token);
        await replayQueue().catch(() => undefined);
      })(),
    );
  }
});
