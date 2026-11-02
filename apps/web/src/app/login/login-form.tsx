"use client";

import { useMutation } from "@tanstack/react-query";
import { Eye, EyeOff, Loader2, LogIn } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import {
  DemoAccessPanel,
  type DemoRoleCard,
} from "@/components/auth/demo-access-panel";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status, user, error, clearError, signIn, bootstrap } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [instantEmail, setInstantEmail] = useState<string | null>(null);

  const nextPath = searchParams.get("next");

  useEffect(() => {
    if (status === "idle") {
      void bootstrap();
    }
  }, [status, bootstrap]);

  useEffect(() => {
    if (status === "authenticated" && user) {
      const fallback = `/dashboard/${user.role.toLowerCase()}`;
      router.replace(nextPath && nextPath.startsWith("/dashboard") ? nextPath : fallback);
    }
  }, [status, user, nextPath, router]);

  const handleSubmit = (formEvent: FormEvent<HTMLFormElement>) => {
    formEvent.preventDefault();
    void signIn(email.trim(), password, remember);
  };

  const instantSignIn = (card: DemoRoleCard) => {
    clearError();
    setInstantEmail(card.email);
    setEmail(card.email);
    setPassword("Demo@1234");
    void signIn(card.email, "Demo@1234", true);
  };

  const busy = status === "loading";

  return (
    <div className="w-full max-w-md space-y-4">
      <div className="flex justify-center">
        <Logo />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="font-display text-2xl">Sign in</CardTitle>
          <CardDescription>Access your TrackSkill AI workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(inputEvent) => setEmail(inputEvent.target.value)}
                placeholder="you@example.com"
                aria-invalid={Boolean(error)}
                className={cn(instantEmail === email && error && "border-destructive")}
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label htmlFor="password" className="text-sm font-medium">
                  Password
                </label>
                <Link
                  href="/forgot-password"
                  className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                >
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(inputEvent) => setPassword(inputEvent.target.value)}
                  aria-invalid={Boolean(error)}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" aria-hidden />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden />
                  )}
                </button>
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={remember}
                onChange={(checkboxEvent) => setRemember(checkboxEvent.target.checked)}
                className="h-4 w-4 rounded border-input"
              />
              Remember me on this device
            </label>

            {error && (
              <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={busy || !email || !password}>
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <LogIn className="h-4 w-4" aria-hidden />
              )}
              Sign in
            </Button>
          </form>

          <div className="relative my-4 h-px bg-border" aria-hidden />
          {process.env.NEXT_PUBLIC_ENABLE_SOCIAL_LOGIN === "true" ? (
            <Button type="button" variant="outline" className="w-full" disabled>
              Continue with Google (coming soon)
            </Button>
          ) : null}

          <p className="mt-4 text-center text-sm text-muted-foreground">
            New here?{" "}
            <Link
              href="/register"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              Create an account
            </Link>
          </p>
        </CardContent>
      </Card>

      <DemoAccessPanel
        pending={busy}
        onPick={(card) => {
          clearError();
          setInstantEmail(null);
          setEmail(card.email);
          setPassword("Demo@1234");
        }}
        onInstantSignIn={instantSignIn}
      />

      <p className="text-center text-sm text-muted-foreground">
        <Link href="/" className="underline-offset-4 hover:underline">
          Back to the landing page
        </Link>
      </p>
    </div>
  );
}
