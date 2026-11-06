# Deploying TrackSkill AI — Render (API + PostgreSQL) and Vercel (web)

Everything in the repo is deploy-ready: `render.yaml` is a Render Blueprint
for the API + database, the API Dockerfile runs migrations + seed before
serving, and Vercel needs no config beyond a root directory. What follows is
the exact click-by-click path, every environment variable, the CORS/WebSocket
settings, and the post-deploy smoke test.

Time budget: **~30 minutes**, of which ~15 is waiting for builds.

> Render's free Postgres expires after **30 days** — upgrade the database
> (or redeploy the blueprint) if you need the demo to live longer. Free web
> services spin down after 15 minutes idle; the first request after a nap
> takes ~50 s to wake (upgrade to a paid instance for a snappy demo).

---

## 0. Prerequisites (manual, one-time)

1. **GitHub** — the code is already pushed to
   `https://github.com/VinayKhatana12/Track-Skill` (branch `main`).
2. **Render account** — <https://dashboard.render.com/register> →
   **Sign up with GitHub** → authorise Render to read your repositories.
3. **Vercel account** — <https://vercel.com/signup> →
   **Continue with GitHub** → install the Vercel GitHub app on the repo.

Generate the production secrets now (run locally, keep the output):

```bash
cd apps/api
# JWT secret (≥ 32 bytes):
python -c "import secrets; print(secrets.token_urlsafe(48))"
# VAPID key pair for Web Push:
../api/.venv/Scripts/python -m app.core.vapid     # Windows (venv)
#   or, in CI-like shells: python -m app.core.vapid
```

---

## 1. Deploy the API + PostgreSQL on Render

### 1.1 Create the services from the Blueprint

1. Dashboard → **New +** → **Blueprint**.
2. Choose the repository `VinayKhatana12/Track-Skill`, branch `main`
   → **Connect**. Render reads `render.yaml` (repo root) and shows:
   - `trackskill-postgres` (free PostgreSQL)
   - `trackskill-api` (Python web service, root dir `apps/api`)
3. Review the pre-filled env vars → **Apply Services**. First build runs
   `pip install` then `bash start.sh`, which applies migrations, seeds the
   demo data (idempotent) and serves on `$PORT`. Takes ~5 minutes.
4. When it goes live, note the URL: `https://trackskill-api-xxxx.onrender.com`
   → open `<url>/health` — you should see
   `{"status":"ok",...,"environment":"production"}`.

### 1.2 Fill the two `sync: false` variables

Dashboard → `trackskill-api` → **Environment**:

| Key | Value | Notes |
| --- | --- | --- |
| `CORS_ORIGINS` | `https://<your-vercel-app>.vercel.app` | set after step 2.4; comma-separate extra origins. This list also drives the CSRF Origin check on `/auth/refresh`. |
| `VAPID_PRIVATE_KEY` | from `python -m app.core.vapid` | enables Web Push in production |
| `VAPID_PUBLIC_KEY` | from the same output | handed to browsers via `/push/public-key` |
| `PUSH_SUBJECT` | `mailto:you@yourmail.example` | VAPID contact claim |

Already set by the blueprint (edit here if needed):

| Key | Value set by blueprint | Why |
| --- | --- | --- |
| `DATABASE_URL` | injected from `trackskill-postgres` | `postgres://` URLs are normalised to `postgresql+psycopg://` by a settings validator |
| `SECRET_KEY` | auto-generated (`generateValue: true`) | JWT signing |
| `ENVIRONMENT` | `production` | turns on HSTS |
| `COOKIE_SECURE` | `true` | HTTPS-only cookies |
| `COOKIE_SAMESITE` | `none` | cross-site refresh cookie: Vercel page → Render API. Requires Secure (set) |
| `DEMO_MODE` / `DEMO_PASSWORD` | `true` / `Demo@1234` | demo accounts + admin demo reset; the login page shows the demo cards |
| `USE_LIGHT_NLP` | `true` | deterministic AI fallback, no model download on free tier |
| `SCHEDULER_ENABLED` | `true` | background tracer cycles every 5 min |
| `TRACER_PROVIDER` | `simulated` | simulated WhatsApp/IVR/SMS gateways |

**Save** — Render redeploys automatically (~2 min).

### 1.3 Migrations and seed in production

They are part of every start (`start.sh`):

```bash
python -m alembic upgrade head     # 0001 → 0006
python -m app.seed                 # idempotent: inserts only missing rows
```

No shell access needed on the free tier — every deploy/restart migrates.
For a manual run with shell access (paid instances): Render dashboard →
`trackskill-api` → **Shell** → run the two commands above.

---

## 2. Deploy the web app on Vercel

### 2.1 Import the project

1. Vercel dashboard → **Add New…** → **Project**.
2. Import `VinayKhatana12/Track-Skill`.
3. **Root Directory**: `apps/web` (Vercel → Edit next to Root Directory →
   type `apps/web` → Continue). Framework auto-detects **Next.js**.
4. Build/Install commands stay default (`npm run build`; install respects
   the committed `apps/web/.npmrc`).

### 2.2 Environment variables (Production)

| Key | Value | Why |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://trackskill-api-xxxx.onrender.com` (your Render URL, no trailing slash) | REST base; also derives the WebSocket URL (`https` → `wss`) |
| `NEXT_PUBLIC_WS_URL` | *(optional)* `wss://trackskill-api-xxxx.onrender.com/ws` | only needed to override the derived URL |

> `NEXT_PUBLIC_*` is inlined at build time — add them **before** deploying,
> and trigger **Redeploy** after any change.

### 2.3 Deploy

**Deploy** → ~3 minutes → Vercel shows
`https://<your-app>.vercel.app`. Keep this URL.

### 2.4 Close the loop: CORS

Render → `trackskill-api` → Environment → set
`CORS_ORIGINS=https://<your-app>.vercel.app` → **Save** (auto-redeploys).
This single list drives: browser CORS, the CSRF Origin check, and the
allowed origins for WebSocket tokens.

(Optional) Vercel → Settings → Domains → **Add** a custom domain; then add
it to `CORS_ORIGINS` the same way.

---

## 3. Post-deploy smoke test checklist (~5 minutes)

Run from a normal browser window (not the demo machine) at
`https://<your-app>.vercel.app`:

| # | Check | Expected |
| --- | --- | --- |
| 1 | Open `/` | landing page renders; theme toggle works |
| 2 | Open `<api>/health` | `{"status":"ok","environment":"production"}` |
| 3 | Open `<api>/docs` | Swagger loads (auth-protected routes still require tokens) |
| 4 | `/login` → demo card **Provider** → Sign in instantly | lands on `/dashboard/provider`; **Live** pill in the top bar |
| 5 | Repeat 4 for **Trainee**, **Employer**, **Admin** (four windows) | all four dashboards render with real seeded data |
| 6 | Admin window → **Run tracer now** | trainee window Messages panel gains messages within seconds (realtime, no reload) |
| 7 | Provider window → enrol a trainee → certify | trainee roster + trainee journey update live |
| 8 | Trainee window → grant consent → answer the M3 tracer (or Admin → Run tracer now to deliver it) | employer window shows the pending claim |
| 9 | Employer window → **Confirm** | admin window feed shows `VERIFICATION_COMPLETE` + `PPI_RECALCULATED` without reload |
| 10 | DevTools → Application → Cookies | `refresh_token` present with `SameSite=None; Secure; Path=/auth` |
| 11 | Network tab → any `/trainee/me` request | no CORS errors; WebSocket connects as `wss://…/ws?token=…` |
| 12 | Sign out → sign back in → close the browser → reopen the app | session restores via the refresh cookie |
| 13 | Admin window → **Reset demo data** | counters return to seed values (proves DEMO_MODE endpoint) |
| 14 | Lighthouse (Chrome DevTools) on `/` | PWA checks pass on the HTTPS origin (install icon available) |

If anything fails, the fastest reset is: Render → `trackskill-api` →
**Manual Deploy → Clear build cache & deploy** (re-runs migrations + seed).

---

## 4. Troubleshooting

| Symptom | Cause → fix |
| --- | --- |
| Login works, then 401s after 15 min | refresh cookie missing → check `COOKIE_SAMESITE=none` and `COOKIE_SECURE=true`, and that the site is HTTPS |
| CORS error in the console | `CORS_ORIGINS` must list the exact Vercel origin (scheme + host, no trailing slash) |
| Realtime pill stuck on "Offline" | WebSocket upgrade: make sure the API URL is the Render HTTPS URL (wss derives automatically); Render free tier wakes ~50 s — retry after first request |
| 502 / very slow first request | free service went to sleep; wake it with a request, or upgrade the instance |
| Seed missing rows after redeploy | seed is idempotent; check the deploy log for the `[start] seeding` line and `Seed summary` |
| Push notifications silently fail | `VAPID_*` env vars missing, or `PUSH_SUBJECT` not a `mailto:` address |
| Demo reset returns 403 | `DEMO_MODE` is not `true` in the environment |

## 5. Redis (optional)

The rate limiter is in-process memory — correct for Render's single free
instance. If you scale to multiple workers later: add a Render **Key Value**
(Redis) instance, set `REDIS_URL`, and swap
`app/services/rate_limit.py`'s store for Redis (the limiter interface is
already isolated for exactly this swap). Nothing else in the app needs Redis.
