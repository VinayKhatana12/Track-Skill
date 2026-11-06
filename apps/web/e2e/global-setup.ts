import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/** Migrate + seed the API database before the E2E servers start.
 * Uses the repo venv interpreter when present (Windows dev), otherwise the
 * ambient python (CI installs requirements into it). The seed is idempotent. */
export default function globalSetup(): void {
  const apiDir = path.resolve(__dirname, "../../api");
  const venvPython = path.join(apiDir, ".venv", "Scripts", "python.exe");
  const venvLinux = path.join(apiDir, ".venv", "bin", "python");
  const py = fs.existsSync(venvPython)
    ? `"${venvPython}"`
    : fs.existsSync(venvLinux)
      ? `"${venvLinux}"`
      : process.env.E2E_PYTHON ?? "python";

  const databaseUrl =
    process.env.DATABASE_URL ??
    "postgresql+psycopg://postgres@127.0.0.1:5433/trackskill";

  console.log("[e2e] applying migrations...");
  execSync(`${py} -m alembic upgrade head`, {
    cwd: apiDir,
    env: { ...process.env, DATABASE_URL: databaseUrl },
    stdio: "inherit",
  });
  console.log("[e2e] seeding demo data (idempotent)...");
  execSync(`${py} -m app.seed`, {
    cwd: apiDir,
    env: { ...process.env, DATABASE_URL: databaseUrl },
    stdio: "inherit",
  });
}
