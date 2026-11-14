// One-shot capture of the ten report screenshots into docs/screenshots/.
// Run: node e2e/capture-report.mjs   (web :3000 and api :8000 must be up)

import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = "http://localhost:3000";
const API = "http://127.0.0.1:8000";
const OUT = path.resolve("..", "..", "docs", "screenshots");
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
});

async function newPage(fresh = false) {
  const target = fresh ? await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  }) : context;
  const page = await target.newPage();
  return page;
}

async function shot(page, name) {
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, name) });
  console.log("captured", name);
}

async function loginDemo(page, role) {
  await page.goto(`${WEB}/login`, { waitUntil: "domcontentloaded" });
  const fill = page.getByLabel(`Fill demo credentials for ${role}`);
  await fill.waitFor({ state: "visible", timeout: 20000 });
  await fill.click();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard/**");
  const dismiss = page.getByRole("button", { name: "Dismiss onboarding" });
  try {
    await dismiss.click({ timeout: 3000 });
  } catch {
    /* already dismissed */
  }
  await page.waitForTimeout(1200);
}

// ── 1. Landing hero + social proof (two viewport captures, stitched later) ──
const landing = await newPage();
await landing.goto(WEB, { waitUntil: "domcontentloaded" });
await landing.waitForTimeout(1500);
await shot(landing, "shot-01a-landing-hero.png");
const proofHeading = landing
  .getByRole("heading")
  .filter({ hasText: /proof|outcome|trusted|impact/i })
  .first();
let proofFound = false;
try {
  await proofHeading.scrollIntoViewIfNeeded({ timeout: 4000 });
  proofFound = true;
} catch {
  await landing.evaluate(() => window.scrollTo(0, document.body.scrollHeight * 0.45));
}
await landing.waitForTimeout(600);
await shot(landing, "shot-01b-landing-social.png");

// ── 2. FAQ + contact ────────────────────────────────────────────────────────
const faqHeading = landing
  .getByRole("heading")
  .filter({ hasText: /faq|question/i })
  .first();
try {
  await faqHeading.scrollIntoViewIfNeeded({ timeout: 4000 });
} catch {
  await landing.evaluate(() => window.scrollTo(0, document.body.scrollHeight * 0.8));
}
await landing.waitForTimeout(600);
await shot(landing, "shot-02a-landing-faq.png");
await landing.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await landing.waitForTimeout(600);
await shot(landing, "shot-02b-landing-contact.png");

// ── 3. Login with demo cards ────────────────────────────────────────────────
const login = await newPage();
await login.goto(`${WEB}/login`, { waitUntil: "domcontentloaded" });
await login.getByLabel("Fill demo credentials for PROVIDER").waitFor({ timeout: 20000 });
await shot(login, "shot-03-login-demo.png");

// ── 4. Create-account flow (step 1) ─────────────────────────────────────────
const register = await newPage();
await register.goto(`${WEB}/register`, { waitUntil: "domcontentloaded" });
await register.waitForTimeout(1200);
await shot(register, "shot-04-register.png");

// ── 5-8. The four dashboards ────────────────────────────────────────────────
const dashboards = [
  ["PROVIDER", "shot-05-provider.png"],
  ["TRAINEE", "shot-06-trainee.png"],
  ["EMPLOYER", "shot-07-employer.png"],
  ["ADMIN", "shot-08-admin.png"],
];
for (const [role, file] of dashboards) {
  const page = await newPage(true);
  await loginDemo(page, role);
  await shot(page, file);
  await page.close();
}

// ── 9. Realtime update visible in two windows ───────────────────────────────
const providerPage = await newPage(true);
await loginDemo(providerPage, "PROVIDER");
const adminPage = await newPage(true);
await loginDemo(adminPage, "ADMIN");

async function apiLogin(email, password = "Demo@1234") {
  const response = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return (await response.json()).access_token;
}
const providerToken = await apiLogin("provider.demo@trackskill.in");
const adminToken = await apiLogin("admin.demo@trackskill.in");
const courses = await (
  await fetch(`${API}/provider/courses`, {
    headers: { Authorization: `Bearer ${providerToken}` },
  })
).json();
const stamp = Date.now();
const enrol = await fetch(`${API}/provider/trainees`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${providerToken}` },
  body: JSON.stringify({
    name: "Report Demo Trainee",
    email: `report.${stamp}@trackskill.in`,
    phone: "+91 9012345678",
    course_id: courses[0].id,
  }),
});
console.log("enrol status:", enrol.status);

// Wait until the admin feed actually shows the new event.
await adminPage.getByText("TRAINEE_ENROLLED").first().waitFor({ timeout: 15000 });
await providerPage
  .getByText("Report Demo Trainee")
  .first()
  .waitFor({ timeout: 15000 });

const providerShot = await providerPage.screenshot();
const adminShot = await adminPage.screenshot();
const { writeFileSync } = await import("node:fs");
writeFileSync(path.join(OUT, "shot-09a-realtime-provider.png"), providerShot);
writeFileSync(path.join(OUT, "shot-09b-realtime-admin.png"), adminShot);
console.log("captured realtime pair");

// ── 10. Swagger ─────────────────────────────────────────────────────────────
const docs = await newPage();
await docs.goto(`${API}/docs`, { waitUntil: "domcontentloaded" });
await docs.waitForTimeout(2000);
await shot(docs, "shot-10-swagger.png");

await browser.close();
console.log("DONE");
