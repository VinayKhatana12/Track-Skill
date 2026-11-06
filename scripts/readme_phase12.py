"""One-shot script: insert Phase 12 documentation sections into README.md."""

from pathlib import Path

readme = Path("README.md")
text = readme.read_text(encoding="utf-8")

text = text.replace(
    "> **Status: Phase 4 — role-scoped REST APIs with realtime events.** Every endpoint from the Provider / Trainee / Employer / Admin playbooks is live, every mutation publishes an audited realtime event to the right audience, and the flagship chain (enrol → certify → consent → respond → confirm → PPI recalculation → allocation/flag) is proven end-to-end by an automated test that asserts the events delivered to each role's WebSocket.",
    "> **Status: Phase 12 — shippable capstone.** All eleven build phases are complete: consent-based tracer engine, dual-signal verification, AI matching, four realtime dashboards, an installable PWA with Web Push, a hardening pass (security headers, rate limits, read audits, data rights) with 104 tests at 85.8% coverage, a four-role Playwright E2E, green CI, and one-click deploy blueprints (see [DEPLOY.md](DEPLOY.md)).",
)

marker = "## Stack"
architecture = """## Architecture

```mermaid
flowchart LR
    subgraph Browser["Browser (PWA)"]
        UI["Next.js 14 App Router<br/>4 role dashboards · landing · auth"]
        SW["Service worker<br/>offline shell · data cache ·<br/>background sync · push"]
        UI <--> SW
    end

    subgraph API["FastAPI (Render)"]
        R["Routers (role-scoped, JWT RBAC)"]
        S["Services (tracer engine, PPI,<br/>AI matching, privacy, push)"]
        WS["WebSocket manager<br/>user:id + role:ROLE channels"]
        R --> S
        S --> WS
    end

    subgraph Data["PostgreSQL 16"]
        DB[("16 domain tables<br/>audit events · consents ·<br/>verifications · PPI")]
    end

    SCH["APScheduler<br/>tracer tick (5 min)"]
    PUSH["Web Push (VAPID)<br/>browser push services"]

    UI -- "REST (Bearer JWT)" --> R
    UI <-. "wss /ws?token=…" .-> WS
    S -- "SQLAlchemy 2.x" --> DB
    SCH --> S
    S -. "encrypted payloads" .-> PUSH
    PUSH -.-> SW
```

**Realtime contract:** every mutation publishes an append-only `events` row,
fans out to `user:<id>` / `role:<ROLE>` WebSocket channels, creates
notification rows and (for notified users) encrypted Web Push messages. The
browser invalidates its React Query caches on every event and pulses the
affected cards.

## Role and permission matrix

RBAC is enforced **server-side** on every route (`require_role(*roles)`); the
matrix below is what the API actually allows.

| Capability | Trainee | Provider | Employer | Admin |
| --- | :-: | :-: | :-: | :-: |
| View own profile / journey / tracer messages | own | — | — | — |
| Grant / revoke consent (per channel, versioned) | own | — | — | — |
| Respond to milestone tracers (structured + free text) | own | — | — | — |
| Export / erase own data (DPDP rights) | own | — | — | — |
| Enrol / bulk-import trainees | — | own centre(s) | — | — |
| Certify trainees | — | own centre(s) | — | — |
| Centre roster / run tracer now | — | own centre(s) | — | — |
| Curriculum-demand gap report | — | own centre(s) | — | all centres |
| Confirm / dispute employment claims | — | — | own company | — |
| Browse consented talent pool (masked contacts) | — | — | yes | — |
| Hire a certified trainee | — | — | yes | — |
| State KPIs, district heat, PPI leaderboard | — | — | — | yes |
| Fund allocations, centre flags | — | — | — | yes |
| Anomaly scan, live audit feed, demo reset | — | — | — | yes |
| Global search | courses | own-centre trainees (masked) | skills | trainees (masked) + centres |

## API overview (50 routes + WebSocket)

| Prefix | Highlights |
| --- | --- |
| `POST /auth/*` | register, login, rotating refresh cookie, logout, simulated password reset; `GET /auth/me`, `GET /auth/demo-accounts` (DEMO_MODE) |
| `GET /health`, `/health/ready` | liveness + DB readiness (Render health check) |
| `/provider/*` | roster, enrol (+CSV import), certify, centre KPIs + PPI rank, courses, follow-up monitor, curriculum gaps |
| `/trainee/*` | journey (`/me`), consent, messages, tracer responses (structured + parsed free text), skills assessment, `/me/export`, `/me/delete` |
| `/employer/*` | pending claims, confirm/dispute, hire, consented talent pool (masked contacts), impact/retention |
| `/admin/*` | state KPIs, PPI leaderboard + centre history, allocations, flags, curriculum gaps, anomaly scan, live audit feed, tracer run-now, demo reset |
| `/notifications`, `/search`, `/push/*` | notification inbox, role-scoped search, VAPID key + push subscriptions |
| `WS /ws?token=…` | realtime events, user-id and role channels |

Full request/response shapes: run the API and open **/docs** (Swagger UI).

## Realtime event catalogue

| Event | Published when | Audience |
| --- | --- | --- |
| `TRAINEE_ENROLLED` | provider enrols (API or CSV) | provider role + the new trainee |
| `TRAINEES_IMPORTED` | bulk CSV import finishes | provider role |
| `TRAINEE_CERTIFIED` | provider certifies | provider role + the trainee |
| `CONSENT_GRANTED` / `CONSENT_REVOKED` | trainee toggles a channel | provider role (revocation cancels pending tracers) |
| `TRACER_SCHEDULED` | M3/M6/M12 tracers created | trainee |
| `TRACER_SENT` | simulated gateway delivers | trainee |
| `TRACER_MISSED` | expiry window passes without a reply | provider role |
| `FOLLOWUP_RESPONDED` | trainee answers a tracer | provider role + employer user |
| `EMPLOYMENT_SELF_REPORTED` | trainee reports employment | employer user (+ provider) |
| `VERIFICATION_COMPLETE` / `VERIFICATION_EMPLOYER_CONFIRMED` | employer confirms (dual-signal completes) | admin + provider roles, the trainee |
| `VERIFICATION_DISPUTED` | employer disputes | admin + provider roles, the trainee |
| `PPI_RECALCULATED` | after every verification change | admin + provider roles |
| `FUND_ALLOCATED` / `PROVIDER_FLAGGED` | admin allocates / flags | provider role |
| `EMPLOYER_HIRED` | employer records a hire | provider role |
| `TRAINEE_DATA_DELETED` | trainee erases their account | admin role |
| `DEMO_RESET` | admin resets demo data | all roles |
| `READ_AUDIT` | sensitive cross-role reads (talent pool, verification queue, search) | events table only (no broadcast) |
| `CONTACT_RECEIVED` | public contact form | admin role |

## Provider Performance Index (PPI)

```
PPI = 100 × (0.30·placement + 0.25·retention_weighted
             + 0.20·wage_growth_norm + 0.15·verification_rate
             + 0.10·response_rate)

retention_weighted = 0.2·R3 + 0.3·R6 + 0.5·R12
```

- **placement** — share of certified trainees with a working outcome; dual-signal-verified placements count 1.0, unverified 0.5 (unverified outcomes weigh less everywhere).
- **retention_weighted** — respondents still in work at each milestone, weighted toward the 12-month signal.
- **wage_growth_norm** — median relative wage growth M3 → M12, clamped at 50%.
- **verification_rate** — dual-signal-verified placements over claimed placements.
- **response_rate** — responded / (responded + missed) among past-due follow-ups.

Recomputed on every verification completion/dispute and on leaderboard reads;
stored per centre per monthly period.

## Screenshots

> Replace these placeholders with captures from the deployed app before
> submission (suggested path: docs/screenshots/).

| # | Section | Placeholder | What to capture |
| --- | --- | --- | --- |
| 1 | Landing page | docs/screenshots/landing.png | hero + how-it-works, light theme |
| 2 | Login + demo access | docs/screenshots/login.png | demo access panel, four role cards |
| 3 | Provider Centre Command | docs/screenshots/provider.png | roster, PPI card, run-tracer control |
| 4 | Trainee My Journey | docs/screenshots/trainee.png | milestone timeline, consent card, messages |
| 5 | Employer Verify & Hire | docs/screenshots/employer.png | pending claims, talent pool with masked contacts |
| 6 | Admin Governance | docs/screenshots/admin.png | KPIs, district heat, PPI leaderboard, allocations |
| 7 | Realtime pulse | docs/screenshots/realtime.png | two windows mid-chain, pulse rings visible |
| 8 | Installable PWA | docs/screenshots/pwa.png | Chrome install prompt / standalone window |
| 9 | Data rights | docs/screenshots/privacy.png | export + erase card on the trainee dashboard |

## Stack"""

text = text.replace(marker, architecture, 1)
readme.write_text(text, encoding="utf-8")
print("README Phase 12 sections added")
