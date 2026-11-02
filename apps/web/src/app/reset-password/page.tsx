"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, Loader2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { PasswordStrengthMeter } from "@/components/auth/password-strength";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { resetPassword } from "@/lib/api";

const resetSchema = z.object({
  new_password: z
    .string()
    .min(10, "Use at least 10 characters.")
    .regex(/[A-Z]/, "Needs an uppercase letter.")
    .regex(/[a-z]/, "Needs a lowercase letter.")
    .regex(/[0-9]/, "Needs a number.")
    .regex(/[^A-Za-z0-9]/, "Needs a symbol."),
});

type ResetValues = z.infer<typeof resetSchema>;

function FieldError({ message }: { message?: string }) {
  if (!message) {
    return null;
  }
  return (
    <p role="alert" className="text-xs text-destructive">
      {message}
    </p>
  );
}

function ResetForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [done, setDone] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register: field,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ResetValues>({
    resolver: zodResolver(resetSchema),
    defaultValues: { new_password: "" },
  });

  const password = watch("new_password");

  const onSubmit = handleSubmit(async (values) => {
    setServerError(null);
    try {
      await resetPassword(token, values.new_password);
      setDone(true);
    } catch (resetError) {
      if (resetError instanceof Error) {
        setServerError(resetError.message);
      } else {
        setServerError("Could not reset the password. The link may have expired.");
      }
    }
  });

  if (!token) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="font-display text-2xl">Invalid link</CardTitle>
          <CardDescription>
            This page needs a reset token. Request a new link from the forgot-password page.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <Link href="/forgot-password">Request a new link</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle className="font-display text-2xl">Choose a new password</CardTitle>
        <CardDescription>Pick something strong — you will use it to sign in.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {done ? (
          <div role="status" className="space-y-3">
            <p className="flex items-center gap-2 font-medium text-primary">
              <CheckCircle2 className="h-5 w-5" aria-hidden />
              Password updated.
            </p>
            <Button asChild className="w-full">
              <Link href="/login">Sign in with your new password</Link>
            </Button>
          </div>
        ) : (
          <form onSubmit={onSubmit} noValidate className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="new-password" className="text-sm font-medium">
                New password
              </label>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                {...field("new_password")}
                aria-invalid={Boolean(errors.new_password)}
              />
              <PasswordStrengthMeter password={password ?? ""} />
              {errors.new_password && <FieldError message={errors.new_password.message} />}
            </div>
            {serverError && (
              <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {serverError}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              Update password
            </Button>
          </form>
        )}

        <p className="text-center text-sm text-muted-foreground">
          <Link href="/login" className="underline-offset-4 hover:underline">
            Back to sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-5 py-16">
      <Suspense fallback={null}>
        <ResetForm />
      </Suspense>
    </main>
  );
}
