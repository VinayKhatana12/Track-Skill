import { expect, test, type Page } from "@playwright/test";

/**
 * The Phase 4 flagship chain, proven through the real UI with four browser
 * contexts — one per role — updating in realtime (no page.reload anywhere):
 *
 *   provider enrols → certifies → trainee consents + answers the M3 tracer
 *   → employer confirms → admin sees verification + PPI recalculation live.
 *
 * Cross-role assertions:
 *   1. provider window shows the new enrolment        (TRAINEE_ENROLLED)
 *   2. trainee window shows certification             (TRAINEE_CERTIFIED)
 *   3. employer window shows the pending claim        (EMPLOYMENT_SELF_REPORTED)
 *   4. admin window shows the PPI recalculation       (VERIFICATION_COMPLETE →
 *      PPI_RECALCULATED) and the trainee window flips to "Verified"
 *      (VERIFICATION_COMPLETE on the user channel)
 */

const API = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const DEMO_PASSWORD = "Demo@1234";

interface ApiLogin {
  access_token: string;
}

async function apiLogin(email: string, password = DEMO_PASSWORD): Promise<string> {
  const response = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  expect(response.status).toBe(200);
  const body = (await response.json()) as ApiLogin;
  return body.access_token;
}

async function apiCall<T>(
  path: string,
  method: string,
  token: string,
  payload?: unknown,
): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  expect(response.status).toBeLessThan(300);
  return (await response.json()) as T;
}

async function loginDemo(page: Page, role: string): Promise<void> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    const fillButton = page.getByLabel(`Fill demo credentials for ${role}`);
    try {
      await fillButton.waitFor({ state: "visible", timeout: 20_000 });
    } catch {
      continue; // page hiccup — one clean retry
    }
    await fillButton.click();
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL("**/dashboard/**");
    await dismissTour(page);
    return;
  }
  throw new Error(`Demo login for ${role} failed after a retry`);
}

async function dismissTour(page: Page): Promise<void> {
  const dismiss = page.getByRole("button", { name: "Dismiss onboarding" });
  try {
    await dismiss.click({ timeout: 3000 });
  } catch {
    // Tour already dismissed for this browser profile.
  }
}

async function loginTrainee(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.getByLabel("Email").fill(email);
  await page.getByRole("textbox", { name: "Password" }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard/**");
  await dismissTour(page);
}

test("flagship chain updates all four role dashboards without a reload", async ({
  browser,
}) => {
  const stamp = Date.now();
  const traineeEmail = `e2e.${stamp}@trackskill.in`;
  const traineeName = `E2E Trainee ${stamp}`; // unique per run: no cross-run claim collisions

  // ── Sign in the three demo roles in their own windows ──────────────────
  const providerContext = await browser.newContext();
  const traineeContext = await browser.newContext();
  const employerContext = await browser.newContext();
  const adminContext = await browser.newContext();

  const providerPage = await providerContext.newPage();
  const traineePage = await traineeContext.newPage();
  const employerPage = await employerContext.newPage();
  const adminPage = await adminContext.newPage();

  await loginDemo(providerPage, "PROVIDER");
  await loginDemo(employerPage, "EMPLOYER");
  await loginDemo(adminPage, "ADMIN");

  const providerToken = await apiLogin("provider.demo@trackskill.in");
  const employerToken = await apiLogin("employer.demo@trackskill.in");
  const adminToken = await apiLogin("admin.demo@trackskill.in");

  // ── 1. Provider enrols a trainee over the API ───────────────────────────
  const courses = await apiCall<{ id: string }[]>(
    "/provider/courses",
    "GET",
    providerToken,
  );
  const enrol = await apiCall<{
    trainee: { id: string };
    temporary_password: string;
  }>("/provider/trainees", "POST", providerToken, {
    name: traineeName,
    email: traineeEmail,
    phone: "+91 9078901234",
    course_id: courses[0].id,
  });

  // Provider window updates without a reload (TRAINEE_ENROLLED).
  await expect(
    providerPage.getByRole("cell", { name: traineeName }).or(
      providerPage.getByText(traineeName, { exact: true }),
    ).first(),
  ).toBeVisible();

  // The new trainee signs in — their own window is the TRAINEE role.
  await loginTrainee(traineePage, traineeEmail, enrol.temporary_password);

  // ── 2. Provider certifies; the trainee window flips to certified ────────
  await apiCall(`/provider/trainees/${enrol.trainee.id}/certify`, "PATCH", providerToken, {});
  await expect(
    traineePage.getByText(/Certified .* — milestones follow/),
  ).toBeVisible({ timeout: 15_000 });

  // ── 3. Trainee grants consent (UI) and answers the M3 tracer (API) ──────
  await expect(
    traineePage.getByLabel("Grant WHATSAPP consent"),
  ).toBeVisible();
  await traineePage.getByLabel("Grant WHATSAPP consent").click();
  await expect(
    traineePage.getByLabel("Revoke WHATSAPP consent"),
  ).toBeVisible({ timeout: 15_000 });

  const traineeToken = await apiLogin(traineeEmail, enrol.temporary_password);
  const me = await apiCall<{
    upcoming: { followup_id: string; milestone: string }[];
  }>("/trainee/me", "GET", traineeToken);
  const m3 = me.upcoming.find((item) => item.milestone === "M3");
  expect(m3).toBeTruthy();
  const impact = await apiCall<{ employer_id: string }>(
    "/employer/impact",
    "GET",
    employerToken,
  );
  await apiCall(
    `/trainee/followups/${m3!.followup_id}/respond`,
    "POST",
    traineeToken,
    {
      employment_status: "EMPLOYED",
      job_title: "Welder",
      monthly_wage: 14000,
      employer_id: impact.employer_id,
    },
  );

  // Employer window shows the pending claim without a reload. Scoped to the
  // #verify section: the same name also appears under "Your hires".
  const claimRow = employerPage.locator("#verify li", { hasText: traineeName });
  await expect(claimRow).toBeVisible({ timeout: 15_000 });

  // ── 4. Employer confirms (UI); admin + trainee windows react live ───────
  const feed = adminPage.getByText("PPI_RECALCULATED");
  const feedCountBefore = await feed.count();

  await claimRow.getByRole("button", { name: "Confirm" }).click();
  await expect(claimRow).toHaveCount(0, { timeout: 15_000 });

  await expect(async () => {
    const count = await adminPage.getByText("PPI_RECALCULATED").count();
    expect(count).toBeGreaterThan(feedCountBefore);
  }).toPass({ timeout: 15_000 });
  await expect(adminPage.getByText("VERIFICATION_COMPLETE").first()).toBeVisible();

  // The trainee window flips to a verified outcome (user-channel event).
  await expect(
    traineePage.getByText("Verified", { exact: true }).first(),
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    traineePage.getByText("Awaiting both signals"),
  ).toHaveCount(0);

  // ── Cleanup: the erasure right cleans the new trainee ──────────────────
  await apiCall("/trainee/me/delete", "POST", traineeToken, { confirm: true });

  await Promise.all([
    providerContext.close(),
    traineeContext.close(),
    employerContext.close(),
    adminContext.close(),
  ]);
});
