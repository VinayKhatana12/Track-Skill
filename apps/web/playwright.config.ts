import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

/**
 * Flagship E2E: four browser contexts (one per role) watch the realtime chain
 * update all four dashboards without a reload.
 *
 * The API database must be migrated + seeded; global-setup runs Alembic and
 * the seed script with the right interpreter (venv on Windows, python on CI).
 * Servers start automatically unless SKIP_SERVERS=1 (local dev loop).
 */

const API_DIR = path.resolve(__dirname, "../api");
const VENV_PYTHON = path.join(API_DIR, ".venv/Scripts/python.exe");
const PY = process.env.E2E_PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: path.resolve(__dirname, "e2e/global-setup.ts"),
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    navigationTimeout: 30_000,
    actionTimeout: 15_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.SKIP_SERVERS
    ? undefined
    : [
        {
          command: `${PY} -m uvicorn app.main:app --port 8000`,
          cwd: API_DIR,
          url: "http://127.0.0.1:8000/health",
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            DATABASE_URL:
              process.env.DATABASE_URL ??
              "postgresql+psycopg://postgres@127.0.0.1:5433/trackskill",
          },
        },
        {
          command: "npm run start",
          url: "http://localhost:3000",
          reuseExistingServer: !process.env.CI,
          timeout: 180_000,
        },
      ],
});
