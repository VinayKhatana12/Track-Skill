# TrackSkill AI — 5-minute demo script

Four browser windows, left→right on the screen: **PROVIDER · TRAINEE ·
EMPLOYER · ADMIN**. Sign in each with its demo card ("Sign in instantly") and
dismiss the onboarding card in every window **before** the audience arrives.
Everything below happens in realtime — no window is ever reloaded.

Time budget: 4 minutes of clicks + 1 minute of close. Every step names the
window, the action, and what the audience should see.

---

## Step 0 (30 s) — Set the scene (ADMIN window)

**Do:** Admin window, scroll through the Governance dashboard briefly: state
KPIs, district heat tiles, PPI leaderboard. Point at the **Live** pill in the
top bar.

**Say:** "Four actors, one shared truth. Every dashboard you'll see is
connected by realtime events — the pill in the corner means the WebSocket is
live. Nothing in this demo will be refreshed."

**Audience sees:** governance data on seeded demo numbers; "Live" indicator.

## Step 1 (45 s) — Enrol + certify (PROVIDER window, admin watching)

**Do:** Provider window → Trainees → **Enrol trainee** → fill name "Asha
Demo", email `asha.demo@trackskill.in`, pick the first course → Enrol.
Then find Asha in the roster → **Certify**.

**Say:** "The provider enrolls and certifies. Certification is the consent
gate: no tracers are scheduled yet — consent first."

**Audience sees:** the roster updates instantly (pulse ring on the Trainees
card); over in the ADMIN window the live activity feed shows
`TRAINEE_ENROLLED` and `TRAINEE_CERTIFIED` appear — **without any reload**.

## Step 2 (40 s) — Consent (TRAINEE window)

**Do:** This demo uses the **seeded trainee** (Asha has no password hand-off
step to keep timing tight): Trainee window → Consent card → confirm
**WhatsApp** shows Active. Show the Messages tab: the M3 tracer has already
arrived as a chat message.

**Say:** "Consent is version-stamped per channel. Revoking it cancels every
unsent tracer — that's enforced in the engine, not the UI."

**Audience sees:** consent card + the simulated WhatsApp message in the
Messages panel.

## Step 3 (45 s) — Tracer response (TRAINEE window → employer watching)

**Do:** Trainee window → Messages → open the M3 message → answer "Employed
at HarbourCare Logistics as Inventory Clerk, ₹18,000 per month" (structured
form or the free-text one-liner) → Send.

**Say:** "The free-text reply is parsed with confidence scoring. The trainee
claims the job; the employer must confirm it — dual-signal."

**Audience sees:** the tracer thread shows the reply; EMPLOYER window — the
pending claim for the seeded trainee appears in "Pending verifications" in
real time; ADMIN feed gains `FOLLOWUP_RESPONDED` /
`EMPLOYMENT_SELF_REPORTED`.

## Step 4 (45 s) — Employer confirms (EMPLOYER window → everyone watching)

**Do:** Employer window → Pending verifications → **Confirm**.

**Say:** "Employer confirms — dual-signal verification completes. Watch three
dashboards at once."

**Audience sees:** claim leaves the queue; TRAINEE window "Verification
status" flips to **Verified**; PROVIDER window PPI card pulses with the new
score; ADMIN feed shows `VERIFICATION_COMPLETE` + `PPI_RECALCULATED` — all
in ~1–2 seconds, no reloads.

## Step 5 (40 s) — Governance acts (ADMIN window)

**Do:** Admin window → find the demo centre in the PPI leaderboard →
**Allocate funds** (form pre-fills from PPI — accept) → Allocate. Then point
at the anomaly inbox.

**Say:** "Money follows measured outcomes. The allocation is audited and the
provider is notified instantly — and the anomaly scan flags statistical
outliers before humans do."

**Audience sees:** PROVIDER window notifications bell gains an item
(`FUND_ALLOCATED`); ADMIN feed shows it.

## Step 6 (35 s) — Ship-ability (any window)

**Do:** Chrome address bar → install icon → **Install** (if not already
installed, do this before the demo). Open the installed window; toggle
DevTools → Network → Offline → reload → the shell opens; switch back online.
Finally: Trainee window → **Your data** card → Export my data (JSON
downloads).

**Say:** "It's an installable app with an offline shell and a background-sync
queue — an offline tracer response is replayed the moment connectivity
returns. And the trainee owns the data: one click exports or erases
everything, DPDP-aligned."

**Audience sees:** standalone window, offline shell, downloaded JSON.

## Close (10 s)

"From consent to verified outcome to funded provider — one realtime chain,
audited end to end. Thank you."

---

### Timing summary

| Step | Window(s) | Seconds |
| --- | --- | --- |
| 0 Scene | Admin | 30 |
| 1 Enrol+certify | Provider (+Admin feed) | 45 |
| 2 Consent | Trainee | 40 |
| 3 Tracer response | Trainee (+Employer) | 45 |
| 4 Confirm | Employer (+Trainee/Provider/Admin) | 45 |
| 5 Governance | Admin (+Provider bell) | 40 |
| 6 PWA + data rights | Any | 35 |
| Close | — | 10 |
| **Total** | | **~4:50** |

### Rehearsal notes

- Run **Admin → Reset demo data** before rehearsing so the seeded trainee has
  a fresh M3 tracer due.
- Do the Chrome **Install** during rehearsal, not live (the prompt is
  one-shot per site).
- Keep a second monitor on the ADMIN activity feed — it is the "proof"
  screen for every step.

### Fallback plan — no internet

The demo runs entirely on the local Docker Compose stack
(`docker-compose.yml` at the repo root):

```bash
# one-time: build images (needs Docker Desktop running)
docker compose build

# demo machine, offline-safe:
docker compose up -d
# open http://localhost:3000 — same demo accounts, same script
```

Only difference: everything runs from localhost, so say "deployed on a local
container stack" instead of naming Vercel/Render. The screenshots in the
report are pre-captured from the public deployment, so the submission is
unaffected. If Docker is also unavailable: `start-demo.bat` (local
PostgreSQL + uvicorn + `next start`) runs the same script.
