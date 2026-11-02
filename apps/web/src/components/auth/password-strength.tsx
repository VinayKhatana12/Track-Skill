"use client";

import { cn } from "@/lib/utils";

/** Shared password-strength scoring mirroring the backend validator:
 * ≥10 chars with upper, lower, number and symbol. */

export interface PasswordStrength {
  score: 0 | 1 | 2 | 3 | 4;
  label: "Too short" | "Weak" | "Fair" | "Good" | "Strong";
  missing: string[];
}

export function scorePassword(password: string): PasswordStrength {
  if (password.length < 10) {
    return { score: 0, label: "Too short", missing: ["at least 10 characters"] };
  }
  const missing: string[] = [];
  if (!/[A-Z]/.test(password)) missing.push("an uppercase letter");
  if (!/[a-z]/.test(password)) missing.push("a lowercase letter");
  if (!/[0-9]/.test(password)) missing.push("a number");
  if (!/[^A-Za-z0-9]/.test(password)) missing.push("a symbol");
  if (missing.length > 0) {
    return { score: 1, label: "Weak", missing };
  }
  const bonus =
    (password.length >= 14 ? 1 : 0) + (/[^A-Za-z0-9].*[^A-Za-z0-9]/.test(password) ? 1 : 0);
  const score = Math.min(4, 3 + bonus) as 3 | 4;
  return { score: score === 4 ? 4 : 3, label: score === 4 ? "Strong" : "Good", missing: [] };
}

const BAR_COLORS: Record<PasswordStrength["score"], string> = {
  0: "bg-border",
  1: "bg-destructive",
  2: "bg-marigold-400",
  3: "bg-brand-400",
  4: "bg-emerald-500",
};

export function PasswordStrengthMeter({ password }: { password: string }) {
  const strength = password ? scorePassword(password) : null;
  if (!strength) {
    return null;
  }
  return (
    <div className="space-y-1" aria-live="polite">
      <div className="flex gap-1" aria-hidden>
        {[1, 2, 3, 4].map((bar) => (
          <span
            key={bar}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors",
              strength.score >= bar ? BAR_COLORS[strength.score] : "bg-border",
            )}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        {strength.label}
        {strength.missing.length > 0 && ` — needs ${strength.missing.join(", ")}`}
      </p>
    </div>
  );
}
