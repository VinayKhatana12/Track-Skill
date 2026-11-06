# TrackSkill AI

**Post-certification outcome tracking for skilling programs.** Skilling programs lose sight of trainees the day they certify: job retention, wage growth and self-employment go unrecorded. TrackSkill AI follows trainees at 3/6/12-month milestones through consent-based digital profiles, simulated WhatsApp/IVR tracers and dual-signal verification (trainee self-report + employer confirmation). AI maps candidate skills and vocational curricula to market demand, and a governance dashboard benchmarks training centres with a Provider Performance Index (PPI) to guide fund allocation.

SDGs: primary **SDG 8** (Decent Work and Economic Growth); supporting **SDG 4** (Quality Education) and **SDG 9** (Industry, Innovation and Infrastructure).

> **Status: Phase 4 — role-scoped REST APIs with realtime events.** Every endpoint from the Provider / Trainee / Employer / Admin playbooks is live, every mutation publishes an audited realtime event to the right audience, and the flagship chain (enrol → certify → consent → respond → confirm → PPI recalculation → allocation/flag) is proven end-to-end by an automated test that asserts the events delivered to each role's WebSocket.

## Stack

- **Web:** Next.js 14 (App Router) · TypeScript · Tailwind CSS · shadcn/ui · Recharts · Framer Motion · TanStack Query · Zustand
- **API:** Python 3.11+ · FastAPI · SQLAlchemy 2.x · Alembic · JWT access+refresh (auth phase) · FastAPI WebSockets · sentence-transformers with TF-IDF fallback (AI phase)
- **Infra:** PostgreSQL 16 · Docker Compose · ESLint + Prettier · Ruff · pre-commit (optional)

## Monorepo layout

```
trackskill/
├── apps/
│   ├── api/                  FastAPI service
│   │   ├── alembic/          Migrations (env wired to app metadata)
│   │   ├── app/
│   │   │   ├── ai/           NLP matching (later phase)
│   │   │   ├── core/         Settings, DB engine/session, password hashing
│   │   │   ├── models/       SQLAlchemy ORM models (15 tables + enums)
│   │   │   ├── realtime/     WebSocket manager + /ws endpoint
│   │   │   ├── routers/      HTTP routers
│   │   │   ├── schemas/      Pydantic schemas
│   │   │   ├── services/     Business logic
│   │   │   ├── main.py       App factory, CORS, routers
│   │   │   └── seed.py       Idempotent demo-data generator
│   │   └── tests/            Pytest suite
│   └── web/                  Next.js 14 App Router app
│       └── src/
│           ├── app/          Layout, landing page, providers, icon
│           ├── components/   UI (shadcn-style), logo, status cards
│           ├── hooks/        TanStack Query + WebSocket hooks
│           ├── lib/          API client, design tokens, utils
│           └── types/        Shared API types
├── docker-compose.yml        postgres:16 + api + web
├── .env.example
├── Makefile
└── README.md
```

## Quickstart (Docker)

Prerequisites: Docker Desktop with Compose v2. Ports 3000, 8000 and 5432 must be free.

```bash
cp .env.example .env
docker compose up --build
```

The first start pulls images and installs API/web dependencies. The web page compiles on first open — give it about 30 seconds.

| Service | URL |
| --- | --- |
| Web app | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Liveness | http://localhost:8000/health |
| Readiness (DB ping) | http://localhost:8000/health/ready |

**Realtime smoke test:** open http://localhost:3000 in two tabs, type a message into the "Realtime · WebSocket" card of either tab and broadcast — it appears in both instantly.

Then create the schema and load demo data (idempotent — safe to re-run):

```bash
make migrate   # alembic upgrade head
make seed      # python -m app.seed
```

## Demo credentials

The four headline demo accounts share the password **`Demo@1234`** (every other seeded account uses it too; all are flagged `is_demo`).

| Role | Email | Dashboard | What it can do |
| --- | --- | --- | --- |
| ADMIN | `admin.demo@trackskill.in` | /dashboard/admin | State Skilling Mission governance (Phase 5 analytics) |
| PROVIDER | `provider.demo@trackskill.in` | /dashboard/provider | Staff of North District Skill Centre |
| TRAINEE | `trainee.demo@trackskill.in` | /dashboard/trainee | Certified trainee with employment and milestones due |
| EMPLOYER | `employer.demo@trackskill.in` | /dashboard/employer | Linked to several trainees' employment records |

`GET /auth/demo-accounts` returns this list for the sign-in page, but only while `DEMO_MODE=true`. The seed also creates 16 more provider staff, 11 more employers and 299 more trainees (same password) so every role sees realistic data.

## REST APIs and realtime (Phase 4)

Swagger (http://localhost:8000/docs) groups every endpoint by role tag: **Provider**, **Trainee**, **Employer**, **Admin**, plus auth and health.

| Role | Endpoints |
| --- | --- |
| Provider | `GET/POST /provider/trainees`, `POST /provider/trainees/import` (CSV), `PATCH /provider/trainees/{id}/certify`, `GET /provider/overview`, `GET /provider/followups` |
| Trainee | `GET /trainee/me` (journey timeline + upcoming milestones), `POST /trainee/consent`, `POST /trainee/followups/{id}/respond`, `GET /trainee/skills` |
| Employer | `GET /employer/verifications`, `POST /employer/verifications/{id}/confirm` / `dispute`, `POST /employer/trainees/{id}/hire`, `GET /employer/talent-pool` |
| Admin | `GET /admin/overview`, `GET /admin/providers` + `/{id}`, `POST /admin/allocations`, `POST /admin/providers/{id}/flag`, `GET /admin/curriculum-gaps`, `GET /admin/events` |

**Provider enrolment** returns a one-time temporary password (shown once, handed to the trainee out of band). **Every mutation** writes an `events` audit row and broadcasts live to `user:<id>` and `role:<ROLE>` WebSocket channels (`/ws?token=<access token>`); anonymous sockets only get isolated `public:<channel>` sandboxes. Enrol/certify/complete/allocate/flag also create notification rows for their target users.

### The flagship chain (covered by `tests/test_chain.py`)

1. Provider enrols + certifies → trainee gets a notification + consent prompt (`TRAINEE_ENROLLED`, `TRAINEE_CERTIFIED`).
2. Trainee grants consent (3 tracers scheduled) and answers the M3 follow-up claiming a job → `CONSENT_GRANTED`, `FOLLOWUP_RESPONDED` hits the provider and the named employer instantly.
3. Employer confirms → `VERIFICATION_COMPLETE` (both signals CONFIRMED, `verified` turns true) → PPI recalculated → `PPI_RECALCULATED` reaches provider and admin.
4. Admin allocates funds or flags the centre → `FUND_ALLOCATED` / `PROVIDER_FLAGGED` reach the provider with notification rows.

### Provider Performance Index (PPI)

```
PPI = 100 × (0.30·placement_rate + 0.25·retention_weighted
             + 0.20·wage_growth_norm + 0.15·verification_rate + 0.10·response_rate)

retention_weighted = 0.2·R3 + 0.3·R6 + 0.5·R12
```

- placement counts verified outcomes at full weight, unverified ones at 0.5
- wage_growth_norm: median M3→M12 relative wage growth, clamped at 50%
- verification_rate: share of the centre's verifications with both signals CONFIRMED
- response_rate: responded / (responded + missed) among past-due tracers

Recalculated on every `VERIFICATION_COMPLETE` and published as `PPI_RECALCULATED`. Source of truth: `apps/api/app/services/ppi.py`.

### Simulated tracer service (Phase 6)

The demo works without real WhatsApp/IVR gateways:

- **Engine** (`app/services/tracer_service.py`): creates M3/M6/M12 tracers from `certified_on` (only with active consent), delivers due tracers through a `ChannelAdapter`, expires SENT tracers with no reply after `TRACER_EXPIRY_DAYS`, and marks tracers MISSED after `TRACER_MAX_ATTEMPTS` failed delivery attempts (exponential backoff). Every transition publishes a realtime event: `TRACER_SCHEDULED`, `TRACER_SENT`, `FOLLOWUP_RESPONDED`, `TRACER_MISSED`.
- **Background scheduler**: APScheduler (`AsyncIOScheduler`) runs a cycle every `TRACER_INTERVAL_SECONDS`; disable with `SCHEDULER_ENABLED=false`.
- **Adapters** (`app/services/tracer_channels.py`): `SimulatedWhatsApp`, `SimulatedIVR`, `SimulatedSMS` for the demo; `TwilioWhatsAppAdapter` / `MetaCloudAdapter` stubs raise loudly behind `TRACER_PROVIDER=twilio|meta` until real credentials land.
- **Trainee dashboard**: a Messages panel renders each tracer as a WhatsApp-style chat (reply inline — the free-text parser scores it) or an IVR call-card with a 1–4 keypad flow.
- **Admin demo control**: `POST /admin/tracer/run` + the "Run tracer now" button fast-forward demo tracers to today and deliver instantly (DEMO_MODE only).

### AI features (Phase 5, `apps/api/app/ai/`)

| Module | What it does |
| --- | --- |
| `taxonomy.py` | 60-skill taxonomy across the 6 sectors (+ aliases) and 14 job roles as weighted skill sets |
| `embedder.py` | Lazy, cached text embedder. `USE_LIGHT_NLP=true` (default) → deterministic hashed n-gram vectors that run on any laptop; `false` → sentence-transformers **all-MiniLM-L6-v2** (chosen for CPU speed + short-text semantic similarity; `pip install sentence-transformers`) |
| `skill_assessment.py` | `POST /trainee/skills/assessment` — embeds course skills + self-described skills + free-text/voice transcripts against the taxonomy → skill profile (confidence 0–1) + top-5 job-role matches with "Matches on: …" explanations |
| `curriculum_matcher.py` | `GET /admin/curriculum-gaps` — per-course demand-weighted coverage vs `market_demand` for the course's district/sector, with gap score, missing in-demand skills and suggested module additions |
| `tracer_nlp.py` | English-only WhatsApp/IVR/SMS tracer templates (surfaced in `/trainee/me` and `/provider/followups`) + a reply parser: "I got a job as a welder, 14000 per month" → structured fields with confidence. `POST /trainee/followups/{id}/respond/text` auto-fills structured responses at confidence ≥ 0.6; lower confidence routes to manual review (provider `manual_review` bucket + notification) |
| `anomalies.py` | Statistical rules — wage outliers (vs sector median), impossible start dates, employer confirmation spikes — raising deduplicated `FLAG_RAISED` events for Admin. Auto-runs after employer confirm/hire; `POST /admin/anomalies/scan` runs a full sweep |

## Authentication and RBAC (Phase 2)

| Endpoint | What it does |
| --- | --- |
| `POST /auth/register` | Self-signup for **TRAINEE and EMPLOYER only** (403 otherwise); validates email + strong password (10+ chars, upper/lower/number/symbol); signs the caller in |
| `POST /auth/login` | Returns a 15-minute **access token** (JSON body) and sets a 7-day **refresh token** as an httpOnly cookie (`Path=/auth`); rate limited per IP + email (5 failures / 5 min); generic `Incorrect email or password.` for every failure |
| `POST /auth/refresh` | Exchanges the cookie for a fresh access token and rotates the refresh cookie |
| `POST /auth/logout` | Clears the refresh cookie |
| `GET /auth/me` | Profile of the authenticated user (any role) |
| `GET /auth/demo-accounts` | Demo logins, only while `DEMO_MODE=true` |
| `GET /trainees/me`, `GET /trainees/{id}` | Ownership-scoped reads: a trainee can only ever read their own profile (others get 404) |

Every guarded endpoint resolves the caller through `require_role(*roles)` — a 403 with a generic message is returned by the **backend**, independent of what the UI hides. JWTs are signed with `SECRET_KEY` (HS256). On the frontend, a Zustand store owns the session, the access token stays in memory, a single-flight refresh retries any 401 once, and `middleware.ts` routes unauthenticated visitors to `/sign-in` and bounces users who open another role's dashboard.

## Database schema (Phase 1)

15 tables, UUID primary keys, `created_at`/`updated_at` on every row, native PostgreSQL enums, indexes and FKs:

| Area | Tables |
| --- | --- |
| Identity & access | `users` (roles: PROVIDER/TRAINEE/EMPLOYER/ADMIN), `provider_staff` |
| Skilling supply | `training_centres`, `courses` (skills `text[]`, NSQF level) |
| Trainees & consent | `trainees`, `consents` (channel, granted/revoked, purpose, version) |
| Outcomes & tracing | `employers`, `employment_records`, `followups` (M3/M6/M12, simulated WhatsApp/IVR tracers), `verifications` (dual-signal; `verified` is a DB-generated column: true exactly when both signals are CONFIRMED) |
| Market & governance | `market_demand` (12 months × sector × skill × district), `provider_scores` (PPI), `fund_allocations` |
| Activity | `events` (audit log + realtime source), `notifications` |

**PPI formula** (seed-computed, fractions 0–1 → score 0–100): `35% placement + 25% avg retention (M3/M6/M12) + 20% verification rate + 20% wage growth (capped at 50% growth)`.

## Seed data

`python -m app.seed` generates deterministic sample data (fixed RNG seed + UUID5 identities): 8 centres across 8 fictional districts, ~26 courses, 300 trainees with consent ledgers, employment records and M3/M6/M12 follow-up history, 12 employers, 12 months × 15 skills × 8 districts of market demand, computed provider scores for the last 3 months, fund allocations, audit events and notifications. It prints per-table row counts and demo credentials at the end. Running it again inserts nothing.

## Make targets

Run `make dev` first; `seed`, `test`, `lint`, `migrate` and `revision` need the stack up.

| Target | What it does |
| --- | --- |
| `make dev` | Start Postgres + API + Web with hot reload |
| `make down` | Stop the stack (data volumes kept) |
| `make logs` | Follow API + Web logs |
| `make seed` | Run demo-data seeding inside the API container |
| `make test` | Pytest + web typecheck + web lint |
| `make lint` | Ruff (API) + ESLint (Web) |
| `make format` | Ruff format (API) + Prettier (Web) |
| `make migrate` | Apply Alembic migrations |
| `make revision m="..."` | Autogenerate a migration |
| `make api-shell` / `make web-shell` / `make db-shell` | Shells into api / web / psql |
| `make clean` | Stop and **delete all volumes** (destroys local data) |

## Environment variables

Copy `.env.example` to `.env` (Docker Compose auto-loads it; the defaults already work locally).

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | db | Postgres credentials |
| `DATABASE_URL` | api (outside Docker) | SQLAlchemy URL; inside Compose it is built from the POSTGRES_* values |
| `SECRET_KEY` | api | JWT signing secret (used from the auth phase) |
| `CORS_ORIGINS` | api | Comma-separated allowed browser origins |
| `ENVIRONMENT` / `LOG_LEVEL` | api | Development flags |
| `NEXT_PUBLIC_API_URL` | web | Browser → API base URL |
| `NEXT_PUBLIC_WS_URL` | web | Browser → WebSocket endpoint (`ws://…/ws`) |

## Running without Docker

API (needs Postgres on localhost:5432 — start `docker compose up -d db`, or point `DATABASE_URL` elsewhere):

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head              # once domain migrations exist
uvicorn app.main:app --reload
```

Web:

```bash
cd apps/web
npm install
npm run dev
```

## Testing and code style

```bash
# with the stack up
make test         # pytest + tsc + eslint
make lint         # ruff + eslint
make format       # ruff format + prettier

# locally
cd apps/api && .venv\Scripts\python -m pytest
cd apps/web && npm run typecheck && npm run lint
```

Optional git hooks: `pip install pre-commit && pre-commit install`.

## Design language

- **Petrol teal** (`brand-*`): institutions, trust, the primary action colour.
- **Marigold** (`marigold-*`): milestones, signals, highlights.
- Warm paper surfaces; **Space Grotesk** display + **Public Sans** body via `next/font`.
- Tokens live in `apps/web/src/lib/design-tokens.ts` and as CSS variables in `src/app/globals.css` (light/dark, WCAG AA).

## Privacy and data protection (DPDP-aligned design intent)

> **Design intent, not legal advice.** The product is built to make an
> independent India DPDP Act 2023 compliance review straightforward; it does
> not assert compliance. Rule-check with your DPO and counsel before any real
> deployment.

**Consent-first tracing.** No tracer is scheduled or sent without a recorded,
version-stamped consent grant (purpose text + version `1.0` on every row).
Revoking consent cancels every un-happened tracer immediately — the scheduler
also re-checks consent before each send, and revoked trainees disappear from
the employer talent pool at once.

**Purpose limitation.** Personal data serves exactly three purposes, stated at
consent time: milestone outcome tracing, verification of the trainee's own
employment claim, and program governance analytics (aggregates).

**Data minimisation.** The schema stores what the milestone outcome needs —
contact channel, employment status, job title, wage band, district — and
nothing else: no demographic proxies, no location tracking, no message content
beyond the tracer replies the trainee chose to send. Phone numbers never
cross role boundaries: they stay with the trainee (owner) and their centre's
provider staff; where contact details must appear to other roles they are
masked at the field level (`+91 ••••••5678`, `me••••••••@example.com`) in
`app/services/privacy.py`.

**Data subject rights (in product).** A signed-in trainee can export
everything stored about them (`GET /trainee/me/export` — one JSON document)
and erase their account (`POST /trainee/me/delete`, explicit
`{"confirm": true}`): profile, consents, tracers, employment claims and
notifications are deleted in the same transaction; audit events survive with
the actor reference nulled, so the trail stays complete without personal
data. Erasure is itself audited (`TRAINEE_DATA_DELETED`) for admins.

**Auditability.** Every mutation publishes an append-only audit event; every
sensitive cross-role read (talent pool, verification queue, trainee search)
writes a `READ_AUDIT` event with the reader, kind and filters.

**Security measures.** Argon-grade password hashing (bcrypt), short-lived JWT
access tokens (15 min) with rotating httpOnly refresh cookies (SameSite=Lax,
Path=/auth, cross-origin refresh rejected), RBAC enforced server-side on
every route, rate limiting on login/contact/reset/push-test, OWASP secure
headers (CSP, nosniff, frame-deny, referrer policy; HSTS in production), and
parameterised ORM queries only — no string-built SQL anywhere.

**Retention.** Tracer records and audit events are the accountability
backbone and are retained; everything personal can be erased by the trainee
or removed by admin demo reset in demo mode. A production deployment must add
a documented retention schedule per DPDP.

**Grievance and breach intent.** The contact endpoint routes questions to
admins; a production deployment must add a grievance officer identity and a
72-hour breach-notification runbook.

## Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Monorepo scaffold, theme, health, realtime wiring, Docker dev stack | ✅ |
| 1 | PostgreSQL schema (15 tables), Alembic migration, idempotent demo seed | ✅ |
| 2 | Auth (JWT access + refresh), RBAC, sign-in/create-account, demo credentials, role dashboards | ✅ |
| 3 | Role-scoped REST APIs, realtime event publishing, PPI service, AI skills fallback | ✅ |
| 4 | AI features: skill assessment, curriculum matcher, tracer NLP, anomaly flagging | ✅ |
| 5 | Simulated WhatsApp/IVR tracer service, scheduler, adapters, Messages panel, demo run-now | ✅ |
| 6 | Frontend dashboards consuming the APIs (provider console, tracer, verification queue, governance) | Planned |
| 7 | sentence-transformers semantic upgrade (behind USE_LIGHT_NLP) + governance screens | Planned |
| 8 | Auth screens polish, onboarding tour, consent versioning | Planned |
| 9 | Authenticated app shell + four realtime role dashboards, CSV/PDF exports | ✅ |
| 10 | Installable PWA: manifest + shortcuts, service worker (offline shell, data cache, background sync), Web Push (VAPID), native-feel, Capacitor/Electron wrappers | ✅ |
| 11 | Hardening: OWASP secure headers, rate limits, read audits, field masking, consent revocation guarantees, data rights (export/erase), DPDP-aligned privacy notes, pytest-cov ≥ 80%, Vitest, Playwright 4-role E2E, GitHub Actions CI | ✅ |

## Known limitations (Phase 6)

- The login rate limiter is in-process memory; running multiple API workers needs a shared store (Redis).
- Refresh tokens are rotated but not server-revocable yet (no jti denylist); logout clears the cookie client-side.
- Frontend dashboards render tracer messages and the demo run-now button; they do not yet subscribe to `user:`/`role:` WebSocket channels for push updates (the Messages panel invalidates on reply instead).
- Real gateway integrations (Twilio/Meta) are stubs; `TRACER_PROVIDER=simulated` is the only fully working mode.
- Tracer delivery is simulated: `FOLLOWUP_RESPONDED` events stand in for the WhatsApp/IVR channel integrations.
- Provider enrolment returns a one-time temporary password by design; there is no self-service password reset flow yet.
- PPI is recomputed per centre on `VERIFICATION_COMPLETE` and on read for leaderboards/overviews — no scheduled batch job yet.
- The AI module is the TF-IDF fallback; semantic (sentence-transformers) matching arrives in the AI phase.
- Containers run dev servers; a production build target lands with the PWA/deploy phase. `NEXT_PUBLIC_*` is inlined per page compile — restart the web container after changing it. On Windows bind mounts the API `--reload` watcher may not fire — restart the api container after backend edits. Fonts and npm/pip packages download on first build.
