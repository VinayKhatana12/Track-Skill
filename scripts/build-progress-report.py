"""Build the Word-ready capstone PROGRESS REPORT (.docx).

Format per spec: A4, 1-inch margins, Times New Roman 12 pt body,
14 pt bold headings, numbered figures/tables with captions, page numbers in
the footer, 10-12 pages. Status is exactly the Phase 0-9 checkpoint the
student specified (10 of 13 phases, ~77%).
"""

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
import sys
OUT = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "TrackSkill-AI-Progress-Report.docx")

BODY_FONT = "Times New Roman"
CODE_FONT = "Consolas"
GREY = RGBColor(0x55, 0x55, 0x55)
PETROL = RGBColor(0x1E, 0x5D, 0x5F)

doc = Document()

# ── Page geometry: A4, 1-inch margins ────────────────────────────────────────
section = doc.sections[0]
section.page_width = Inches(8.27)
section.page_height = Inches(11.69)
for side in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
    setattr(section, side, Inches(1))

# ── Styles ───────────────────────────────────────────────────────────────────
normal = doc.styles["Normal"]
normal.font.name = BODY_FONT
normal.font.size = Pt(12)
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.line_spacing = 1.15

for level, size in (("Heading 1", 14), ("Heading 2", 14), ("Heading 3", 12)):
    style = doc.styles[level]
    style.font.name = BODY_FONT
    style.font.size = Pt(size)
    style.font.bold = True
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.space_before = Pt(10)
    style.paragraph_format.space_after = Pt(6)

# ── Footer: centred page number field ────────────────────────────────────────
footer_paragraph = section.footer.paragraphs[0]
footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = footer_paragraph.add_run("Page ")
run.font.name = BODY_FONT
run.font.size = Pt(10)
field_run = footer_paragraph.add_run()
field_run.font.name = BODY_FONT
field_run.font.size = Pt(10)
begin = OxmlElement("w:fldChar")
begin.set(qn("w:fldCharType"), "begin")
instr = OxmlElement("w:instrText")
instr.set(qn("xml:space"), "preserve")
instr.text = "PAGE"
end = OxmlElement("w:fldChar")
end.set(qn("w:fldCharType"), "end")
field_run._r.append(begin)
field_run._r.append(instr)
field_run._r.append(end)


# ── Helpers ──────────────────────────────────────────────────────────────────

def paragraph(text, bold=False, size=12, align=None, space_after=6, italic=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name = BODY_FONT
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    return p


def heading(text, level=1):
    doc.add_heading(text, level=level)


def bullet(text, bold_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    if bold_prefix:
        r = p.add_run(bold_prefix)
        r.bold = True
        r.font.name = BODY_FONT
        r.font.size = Pt(12)
    r = p.add_run(text)
    r.font.name = BODY_FONT
    r.font.size = Pt(12)
    return p


def caption(text, table=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name = BODY_FONT
    r.font.size = Pt(10)
    r.italic = True
    r.bold = True
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(10)
    return p


def code_block(code):
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    cell = table.cell(0, 0)
    cell.paragraphs[0].text = ""
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), "F4F4F1")
    cell._tc.get_or_add_tcPr().append(shading)
    lines = code.strip("\n").split("\n")
    for index, line in enumerate(lines):
        p = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run(line)
        r.font.name = CODE_FONT
        r.font.size = Pt(8.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def image(path, width_inches, figure_number, caption_text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(path), width=Inches(width_inches))
    caption(f"Figure {figure_number}: {caption_text}")
    doc.paragraphs[-1].paragraph_format.page_break_before = False


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def set_cell(cell, text, bold=False, size=9.5, align=None):
    cell.text = ""
    p = cell.paragraphs[0]
    r = p.add_run(text)
    r.font.name = BODY_FONT
    r.font.size = Pt(size)
    r.bold = bold
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.0


# ═════════════════════════════ PAGE 1 — COVER ═══════════════════════════════
title = paragraph(
    "TrackSkill AI",
    bold=True,
    size=18,
    align=WD_ALIGN_PARAGRAPH.CENTER,
    space_after=2,
)
paragraph(
    "Post-Certification Outcome Tracking for Skilling Programs",
    bold=True,
    size=13,
    align=WD_ALIGN_PARAGRAPH.CENTER,
    space_after=10,
)
paragraph("PROGRESS REPORT", bold=True, size=14, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)

for label, value in (
    ("Course / Subject:", "[TO BE FILLED: course name]"),
    ("Institution:", "[TO BE FILLED: institution name]"),
    ("Faculty / Guide:", "[TO BE FILLED: faculty name]"),
    ("Submission date:", "[TO BE FILLED: date]"),
):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"{label} ")
    r.bold = True
    r.font.name = BODY_FONT
    r.font.size = Pt(11)
    r = p.add_run(value)
    r.font.name = BODY_FONT
    r.font.size = Pt(11)
    r.italic = True
    p.paragraph_format.space_after = Pt(2)

heading("Team and Task Allocation", level=1)

TEAM = [
    (
        "[Student 1 name, Reg. No.]",
        "Landing page, sign in / create account, demo credentials UI",
        "Landing page (hero, social proof, FAQ, contact form), sign-in and "
        "multi-step registration with consent, one-click demo credential cards",
        "Built the public marketing pages and the complete sign-in / sign-up "
        "experience including the four demo-access cards",
        "Done",
    ),
    (
        "[Student 2 name, Reg. No.]",
        "Database schema, seed data, auth and role-based access (backend)",
        "16-table schema, Alembic migrations, idempotent seed (329 users), "
        "JWT auth, RBAC",
        "Built the persistence layer and the RBAC security backbone",
        "Done",
    ),
    (
        "[Student 3 name, Reg. No.]",
        "Domain APIs and business rules (PPI formula, dual-signal verification)",
        "50 role-scoped REST APIs, Provider Performance Index, dual-signal "
        "verification rules, fund allocation logic",
        "Built the business rules incl. the PPI formula and verified column",
        "Done",
    ),
    (
        "[Student 4 name, Reg. No.]",
        "Realtime layer (WebSockets, notifications) and the four role dashboards",
        "WS user/role channels, event fan-out, app shell, four realtime "
        "dashboards with pulse feedback",
        "Built the realtime contract and all four no-reload dashboards",
        "Done",
    ),
    (
        "[Student 5 name, Reg. No.]",
        "AI modules (skill assessment, curriculum-demand matching, reply parser) "
        "and tracer simulator",
        "Skill assessment, curriculum-demand matching, tracer reply parser, "
        "anomaly scan, simulated WhatsApp/IVR/SMS tracer engine",
        "Built the AI modules and the consent-gated tracer simulator",
        "Done",
    ),
    (
        "[Student 6 name, Reg. No.]",
        "Testing, documentation, PWA/deployment planning and this report",
        "Pytest suite (77 tests passing incl. the realtime chain test), "
        "lint/build checks, deployment and demo planning drafts",
        "Built the test suite and project documentation; PWA/deployment "
        "execution planned (see remaining work)",
        "In progress",
    ),
]

table = doc.add_table(rows=1, cols=6)
table.style = "Table Grid"
table.alignment = WD_TABLE_ALIGNMENT.CENTER
headers = ("Student Name", "Reg. No.", "Module / Task Assigned", "Work Completed", "Contribution", "Status")
widths = (1.0, 0.75, 1.35, 1.55, 1.55, 0.65)
header_row = table.rows[0]
for index, header in enumerate(headers):
    set_cell(header_row.cells[index], header, bold=True, size=8)
shading = OxmlElement("w:shd")
shading.set(qn("w:val"), "clear")
shading.set(qn("w:fill"), "E4EEED")
header_row.cells[index]._tc.get_or_add_tcPr().append(shading)
for member in TEAM:
    row = table.add_row()
    name, task, completed, contribution, status = member
    reg = "[TO BE FILLED: Reg. No.]"
    set_cell(row.cells[0], name.split(",")[0].strip(), size=8)
    set_cell(row.cells[1], reg, size=8)
    set_cell(row.cells[2], task, size=7.5)
    set_cell(row.cells[3], completed, size=7.5)
    set_cell(row.cells[4], contribution, size=7.5)
    set_cell(row.cells[5], status, size=7.5)
for row in table.rows:
    for index, cell in enumerate(row.cells):
        cell.width = Inches(widths[index])
caption("Table 1: Team composition, assigned modules and status")

paragraph("Overall progress", bold=True)
progress_paragraph = doc.add_paragraph()
progress_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
progress_run = progress_paragraph.add_run()
progress_run.add_picture(str(SHOTS / "progress-bar.png"), width=Inches(4.1))
paragraph(
    "10 of 13 phases complete (about 77%). The application currently runs "
    "locally (localhost) and is not yet deployed to a public URL or installable "
    "as a PWA; Phases 10-12 cover those items.",
    size=11,
    align=WD_ALIGN_PARAGRAPH.CENTER,
)
page_break()

# ═════════════════════════════ PAGE 2 — OVERVIEW ════════════════════════════
heading("Project Overview", level=1)
paragraph(
    "TrackSkill AI tracks the outcomes of skilling programs after certification: "
    "employment status, wages and job retention at 3, 6 and 12 months. Trainees "
    "grant version-stamped consent per channel (WhatsApp, IVR, SMS); a simulated "
    "tracer engine then asks milestone questions and parses the replies. Every "
    "employment claim is verified by two independent signals — the trainee's "
    "self-report and the named employer's confirmation — and only dual-confirmed "
    "outcomes count at full weight. Four roles work on one realtime platform: "
    "Training Providers enrol and certify, Trainees answer tracers, Employers "
    "verify claims, and the State Skilling Mission Admin steers funding with a "
    "Provider Performance Index (PPI) that ranks centres by placement, "
    "retention, wage growth, verification and response rates. An AI module "
    "assesses trainee skills and matches curricula to market demand. The stack "
    "is Next.js, FastAPI, PostgreSQL, WebSockets and NLP; the product is "
    "English-only."
)
paragraph("SDG mapping", bold=True, space_after=2)
bullet("SDG 8 (Decent Work and Economic Growth) — primary: measures what funders actually need, verified employment, retention and wage growth after certification, and ties funding decisions to those outcomes through the PPI.")
bullet("SDG 4 (Quality Education) — supporting: the curriculum-demand gap report tells centres which modules to teach, and the skill assessment shows trainees where they stand against market needs.")
bullet("SDG 9 (Industry, Innovation and Infrastructure) — supporting: audited realtime infrastructure that runs without telco contracts (simulated gateways) and is deployable on commodity hosting.")
page_break()

# ═══════════════════════ PAGE 3-4 — FLOW CHARTS ═════════════════════════════
heading("Flow Chart of Work", level=1)
paragraph(
    "The project followed a fourteen-step build order grouped into thirteen "
    "delivery phases. Steps 1-11 (Phases 0-9) are complete and shown green; "
    "Phases 10-12 (PWA, security and full test suite, deployment and final "
    "documentation) are pending and shown grey. No step is in progress."
)
image(SHOTS / "fig-workflow.png", 6.15, 1, "Flow chart of work — green = completed (Phases 0-9), grey = pending (Phases 10-12)")
paragraph(
    "The system flow below is the flagship cross-department chain that the "
    "product is built around; it is demonstrated live in the demo and asserted "
    "end-to-end by the automated integration test."
)
image(SHOTS / "fig-systemflow.png", 4.6, 2, "System flow: the dual-signal verification chain with its realtime events")
page_break()

# ═══════════════════════ PAGE 4+ — IMPLEMENTATION ═══════════════════════════
heading("Implementation Details (completed modules)", level=1)

heading("4.1 Landing page, sign in / create account — Student 1", level=2)
paragraph(
    "Purpose: the public entry point and every authentication surface. The "
    "landing page (hero, how-it-works, sample social proof, FAQ, working "
    "contact form) converts visitors; the sign-in page offers one-click demo "
    "cards for each role; registration is a multi-step form with a "
    "version-stamped consent screen."
)
bullet("apps/web/src/app/page.tsx — landing page with ten sections")
bullet("apps/web/src/app/login/login-form.tsx — sign-in form with instant demo sign-in")
bullet("apps/web/src/components/auth/demo-access-panel.tsx — demo credential cards")
bullet("apps/web/src/app/register/page.tsx — multi-step registration with consent step")
paragraph("Key logic — one-click demo sign-in:", bold=True, space_after=2)
code_block(
    """const instantSignIn = (card: DemoRoleCard) => {
  clearError();
  setInstantEmail(card.email);
  setEmail(card.email);
  setPassword("Demo@1234");
  void signIn(card.email, "Demo@1234", true);
};"""
)

heading("4.2 Database schema, seed data, auth and RBAC — Student 2", level=2)
paragraph(
    "Purpose: the persistence and security backbone. Sixteen domain tables "
    "cover users, centres, trainees, consents, tracers, verifications, "
    "market demand, provider scores, allocations, audit events, notifications "
    "and push subscriptions. Alembic migrations 0001-0006 apply cleanly to an "
    "empty database, and the seed generator is idempotent (safe to re-run). "
    "Authentication issues a 15-minute JWT access token plus a rotating "
    "httpOnly refresh cookie; every route is guarded server-side by "
    "require_role(*roles)."
)
bullet("apps/api/alembic/versions/0002_core_schema.py — core schema migration")
bullet("apps/api/app/models/ — 16 ORM tables incl. generated dual-signal column")
bullet("apps/api/app/seed.py — idempotent demo data (329 users, 8 centres)")
bullet("apps/api/app/dependencies.py — get_current_user and require_role guards")
paragraph("Key logic — the database-computed dual-signal column:", bold=True, space_after=2)
code_block(
    """# The database computes this column: verified exactly when both signals agree.
_VERIFIED_EXPRESSION = (
    "(trainee_signal = 'CONFIRMED'::verification_signal) "
    "AND (employer_signal = 'CONFIRMED'::verification_signal)"
)

class Verification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    verified: Mapped[bool] = mapped_column(
        Boolean,
        Computed(_VERIFIED_EXPRESSION, persisted=True),
        nullable=False,
    )"""
)

heading("4.3 Domain APIs and business rules — Student 3", level=2)
paragraph(
    "Purpose: the role-scoped REST layer (50 routes) and the business rules "
    "that make outcomes trustworthy. The Provider Performance Index combines "
    "five weighted components into one comparable score per centre per month, "
    "and verification is dual-signal: an outcome counts at full weight only "
    "when both the trainee and the employer confirm it."
)
bullet("apps/api/app/services/ppi.py — PPI formula and monthly storage")
bullet("apps/api/app/services/employer_service.py — claim confirm/dispute, talent pool, impact")
bullet("apps/api/app/routers/ — 50 role-scoped endpoints (provider, trainee, employer, admin)")
paragraph("Key logic — the Provider Performance Index:", bold=True, space_after=2)
code_block(
    """ppi = 100 * (
    PPI_WEIGHTS["placement"] * placement_rate
    + PPI_WEIGHTS["retention"] * retention_weighted
    + PPI_WEIGHTS["wage_growth"] * wage_growth_norm
    + PPI_WEIGHTS["verification"] * verification_rate
    + PPI_WEIGHTS["response"] * response_rate
)
return {..., "ppi_score": round(ppi, 2)}"""
)

heading("4.4 Realtime layer and the four dashboards — Student 4", level=2)
paragraph(
    "Purpose: one shared truth across departments. Every mutation publishes an "
    "append-only audit event and fans it out to per-user and per-role "
    "WebSocket channels plus notification rows; the browser invalidates its "
    "queries on every event and pulses the affected cards for about two "
    "seconds. The four dashboards (Provider Centre Command, Trainee My "
    "Journey, Employer Verify & Hire, Admin Governance) render from real API "
    "data with skeletons and empty states."
)
bullet("apps/api/app/services/realtime.py — event fan-out (WebSocket + notifications)")
bullet("apps/api/app/realtime/manager.py — WebSocket channel manager")
bullet("apps/web/src/components/dashboard/app-shell.tsx — shell, search, bell, profile")
bullet("apps/web/src/hooks/use-pulse.ts — 2-second realtime pulse hook")
paragraph("Key logic — the realtime fan-out:", bold=True, space_after=2)
code_block(
    """message_payload = {**resolved_payload, "event_id": str(event.id)}
for user_id in dict.fromkeys(audience_user_ids):
    await manager.broadcast(f"user:{user_id}", event_type, message_payload)
for role in dict.fromkeys(audience_roles):
    await manager.broadcast(f"role:{role}", event_type, message_payload)
return event.id"""
)

heading("4.5 AI modules and tracer simulator — Student 5", level=2)
paragraph(
    "Purpose: reduce manual work in tracing and matching. The AI module "
    "assesses trainee skills, matches course curricula to market demand, "
    "flags statistical anomalies, and parses free-text tracer replies into "
    "structured outcomes with a confidence score — low-confidence replies "
    "route to provider review. The tracer simulator delivers consent-gated "
    "WhatsApp/IVR/SMS follow-ups through pluggable channel adapters with "
    "retries and expiry."
)
bullet("apps/api/app/ai/tracer_nlp.py — free-text reply parser with confidence")
bullet("apps/api/app/ai/skills.py — skill assessment and role matching")
bullet("apps/api/app/ai/curriculum_matcher.py — curriculum-demand gap report")
bullet("apps/api/app/services/tracer_service.py — consent-gated tracer engine")
paragraph("Key logic — reply parsing with confidence scoring:", bold=True, space_after=2)
code_block(
    """def parse_reply(text: str) -> ParsedReply:
    normalised = re.sub(r"\\s+", " ", (text or "").strip().lower())
    employment_status = _detect_employment(normalised)
    working = employment_status in (EMPLOYED, SELF_EMPLOYED)
    job_title = _detect_title(normalised) if working else None
    monthly_wage = _detect_wage(normalised)
    if employment_status is None:
        confidence = 0.15
    else:
        confidence = 0.35 + 0.30
        if monthly_wage is not None:
            confidence += 0.15
        if job_title:
            confidence += 0.15
    return ParsedReply(employment_status, job_title, monthly_wage, confidence)"""
)

heading("4.6 Testing, documentation and planning — Student 6", level=2)
paragraph(
    "Purpose: prove the flagship behaviour automatically and keep the project "
    "documented. The pytest suite covers auth, domain chains, tracers, the AI "
    "modules and health; its centrepiece is the four-role realtime chain test "
    "that opens one WebSocket per role and asserts the exact event sequence "
    "of the verification chain. Ruff lint and the Next.js production build "
    "are part of every check."
)
bullet("apps/api/tests/test_chain.py — four-role realtime chain integration test")
bullet("apps/api/tests/ — 77 tests passing at this checkpoint")
bullet("DEPLOY.md, DEMO-SCRIPT.md — deployment and demo planning drafts")
paragraph("Key logic — the realtime chain assertion:", bold=True, space_after=2)
code_block(
    """# Employer confirms -> the provider and admin sockets receive, in order:
confirm = client.post(
    f"/employer/verifications/{verification_id}/confirm",
    headers=_auth(employer_token),
)
assert confirm.status_code == 200
assert [event["event"] for event in _recv(ws_provider, 2)] == [
    "VERIFICATION_COMPLETE",
    "PPI_RECALCULATED",
]"""
)

heading("Files Delivered", level=1)
files_table = doc.add_table(rows=1, cols=3)
files_table.style = "Table Grid"
for index, header in enumerate(("File / Folder", "Description", "Author")):
    set_cell(files_table.rows[0].cells[index], header, bold=True, size=9.5)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), "E4EEED")
    files_table.rows[0].cells[index]._tc.get_or_add_tcPr().append(shading)
FILES = [
    ("apps/web/src/app/page.tsx", "Landing page (hero, social proof, FAQ, contact)", "Student 1"),
    ("apps/web/src/app/login/, register/", "Sign-in and multi-step registration with consent", "Student 1"),
    ("apps/web/src/components/auth/demo-access-panel.tsx", "One-click demo credential cards", "Student 1"),
    ("apps/api/alembic/versions/", "Six migrations building the full schema", "Student 2"),
    ("apps/api/app/models/", "16 ORM tables incl. generated verified column", "Student 2"),
    ("apps/api/app/seed.py", "Idempotent demo seed (329 users, 8 centres)", "Student 2"),
    ("apps/api/app/services/auth_service.py + app/dependencies.py", "JWT auth, refresh cookie, RBAC guards", "Student 2"),
    ("apps/api/app/services/ppi.py", "Provider Performance Index formula", "Student 3"),
    ("apps/api/app/services/employer_service.py", "Verification queue, confirm/dispute, talent pool", "Student 3"),
    ("apps/api/app/routers/", "50 role-scoped REST endpoints", "Student 3"),
    ("apps/api/app/services/realtime.py + app/realtime/", "Event fan-out to user/role WebSocket channels", "Student 4"),
    ("apps/web/src/components/dashboard/app-shell.tsx", "Application shell (sidebar, search, bell)", "Student 4"),
    ("apps/web/src/app/dashboard/{provider,trainee,employer,admin}/", "The four realtime role dashboards", "Student 4"),
    ("apps/api/app/ai/", "Skill assessment, curriculum matcher, reply parser, anomalies", "Student 5"),
    ("apps/api/app/services/tracer_service.py + tracer_channels.py", "Consent-gated tracer engine and channel adapters", "Student 5"),
    ("apps/api/tests/", "Pytest suite incl. the four-role realtime chain test", "Student 6"),
    ("README.md, DEPLOY.md, DEMO-SCRIPT.md", "Documentation and planning drafts", "Student 6"),
]
for file_path, description, author in FILES:
    row = files_table.add_row()
    set_cell(row.cells[0], file_path, size=8.5)
    set_cell(row.cells[1], description, size=8.5)
    set_cell(row.cells[2], author, size=8.5)
caption("Table 2: Files and folders delivered, with owning student")

# ═════════════════════ SCREENSHOTS ══════════════════════════════════════════
heading("Screenshots", level=1)
paragraph(
    "Captured from the running application (localhost) during report "
    "preparation. Each figure below replaces its [INSERT SCREENSHOT: ...] "
    "placeholder."
)
SCREENSHOTS = [
    ("shot-01-landing.png", 6.15, "Landing page — hero and social proof section"),
    ("shot-02-faq-contact.png", 6.15, "Landing page — FAQ and contact section"),
    ("shot-03-login-demo.png", 4.0, "Login page with demo credential cards"),
    ("shot-04-register.png", 4.0, "Create-account flow (step 1)"),
    ("shot-05-provider.png", 5.2, "Provider dashboard — Centre Command"),
    ("shot-06-trainee.png", 5.2, "Trainee dashboard — My Journey"),
    ("shot-07-employer.png", 5.2, "Employer dashboard — Verify & Hire"),
    ("shot-08-admin.png", 5.2, "Admin dashboard — Governance"),
    ("shot-09-realtime.png", 5.6, "Realtime update visible in two windows (provider roster pulse + admin notification)"),
    ("shot-10-swagger.png", 4.0, "Swagger API documentation"),
]
for number, (filename, width, text) in enumerate(SCREENSHOTS, start=3):
    image(SHOTS / filename, width, number, text)

# ═════════════════════ TESTING ══════════════════════════════════════════════
heading("Testing Done So Far", level=1)
paragraph("What was actually run against the current codebase, with results:")
TESTING = [
    ("Pytest integration/unit suite", "77 tests, all passing", "apps/api/tests — auth, roles, domain APIs, tracer engine, AI modules, four-role realtime chain"),
    ("Realtime chain test", "Passing", "Opens one WebSocket per role and asserts the exact event sequence enrol → certify → consent → respond → confirm → PPI recalculation"),
    ("Ruff lint (backend)", "All checks passed", "Static analysis over apps/api"),
    ("ESLint + production build (frontend)", "Clean; 15 routes compiled", "next lint, tsc --noEmit, next build"),
    ("Manual four-window demonstration", "Verified", "Provider enrols/certifies; trainee consents and answers; employer confirms; admin sees VERIFICATION_COMPLETE and PPI_RECALCULATED live, no reload"),
    ("Tracer run-now (manual)", "Verified", "Admin trigger delivered 262 scheduled tracers through the simulated gateways in one cycle"),
]
test_table = doc.add_table(rows=1, cols=3)
test_table.style = "Table Grid"
for index, header in enumerate(("Check", "Result", "Notes")):
    set_cell(test_table.rows[0].cells[index], header, bold=True, size=9.5)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), "E4EEED")
    test_table.rows[0].cells[index]._tc.get_or_add_tcPr().append(shading)
for check, result, notes in TESTING:
    row = test_table.add_row()
    set_cell(row.cells[0], check, size=8.5)
    set_cell(row.cells[1], result, size=8.5)
    set_cell(row.cells[2], notes, size=8.5)
caption("Table 3: Testing performed at this checkpoint")
paragraph(
    "[TO BE FILLED: attach or reference the faculty-required test report "
    "format and screenshots of test output if the submission template needs "
    "them.] Broader component tests, an end-to-end browser suite, coverage "
    "measurement and security hardening checks are planned as part of Phase 11 "
    "(see remaining work).",
    italic=True,
)

heading("Challenges Faced and Solutions", level=1)
CHALLENGES = [
    (
        "Alembic migrations created empty tables",
        "op.create_table(Table) rebuilt tables from names only, silently "
        "emitting CREATE TABLE users (). Fixed by emitting table.create(bind) "
        "directly; verified by row counts after migration.",
    ),
    (
        "Cross-origin sign-in broke sessions in hosted setups",
        "The refresh cookie used SameSite=Lax, which browsers drop on "
        "cross-site requests. Fixed by SameSite=None; Secure behind HTTPS plus "
        "an explicit CORS origin list, and validated against the local stack.",
    ),
    (
        "Cached API responses delayed realtime updates",
        "The service worker's cache-first strategy served seconds-old data to "
        "realtime-triggered refetches. Fixed by switching API GETs to "
        "network-first with cached fallback, keeping the offline shell intact.",
    ),
    (
        "PostgreSQL development cluster stalled on Windows",
        "The local cluster repeatedly stopped accepting connections under "
        "memory pressure. Recovered with WAL replay, moved the data directory "
        "to a durable path, and added a ready-check to the start script.",
    ),
    (
        "Enum comparisons caused a 500 on the employer claim queue",
        "An SQLAlchemy is_(PENDING) comparison rendered IS $2, invalid in "
        "PostgreSQL. Fixed to equality and covered by a regression test.",
    ),
]
for index, (challenge, solution) in enumerate(CHALLENGES, start=1):
    p = doc.add_paragraph()
    r = p.add_run(f"{index}. {challenge}. ")
    r.bold = True
    r.font.name = BODY_FONT
    r.font.size = Pt(12)
    r = p.add_run("Solution: " + solution)
    r.font.name = BODY_FONT
    r.font.size = Pt(12)

heading("Remaining Work (two-week plan)", level=1)
paragraph(
    "Dates are relative to the plan start [TO BE FILLED: start date]; each "
    "phase has one owner from the team."
)
PLAN = [
    (
        "Phase 10 — Installable PWA",
        "Student 4",
        "Days 1-4: manifest with role shortcuts, maskable icons, service worker "
        "(offline shell, API data cache), install prompt and update toast. "
        "Days 5-7: pull-to-refresh, safe-area polish, push permission flow; "
        "verify Lighthouse PWA checks.",
    ),
    (
        "Phase 11 — Security hardening and full test suite",
        "Student 2",
        "Days 8-10: secure headers, rate limits, read-audit events, phone "
        "masking, consent-revocation guarantees. Days 11-14: component tests, "
        "four-role end-to-end browser test, coverage gate at 80%, CI workflow.",
    ),
    (
        "Phase 12 — Deployment, README, final report, demo script",
        "Student 6",
        "Days 10-14 (parallel): Render Blueprint for API + PostgreSQL, Vercel "
        "deploy for the web app, production environment variables, smoke-test "
        "checklist, final README with architecture diagram, this report "
        "finalised, 5-minute demo script rehearsed.",
    ),
]
plan_table = doc.add_table(rows=1, cols=3)
plan_table.style = "Table Grid"
for index, header in enumerate(("Phase / scope", "Owner", "Schedule")):
    set_cell(plan_table.rows[0].cells[index], header, bold=True, size=9.5)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), "E4EEED")
    plan_table.rows[0].cells[index]._tc.get_or_add_tcPr().append(shading)
for phase, owner, schedule in PLAN:
    row = plan_table.add_row()
    set_cell(row.cells[0], phase, size=8.5)
    set_cell(row.cells[1], owner, size=8.5)
    set_cell(row.cells[2], schedule, size=8.5)
caption("Table 4: Two-week plan to complete Phases 10-12")

heading("Conclusion", level=1)
paragraph(
    "Ten of thirteen phases are complete: the platform's full domain — "
    "consent-based tracing, dual-signal verification, the Provider Performance "
    "Index, AI matching and four realtime dashboards — works end to end and is "
    "proven by a 77-test automated suite including a four-role realtime chain "
    "test. The remaining two weeks cover packaging (installable PWA), a "
    "security and test-coverage pass, and a public deployment, after which the "
    "demo can run entirely on live URLs with the same demo accounts used "
    "throughout this report."
)

doc.save(OUT)
print("saved", OUT)
