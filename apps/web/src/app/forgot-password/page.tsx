"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, MailCheck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { requestPasswordReset } from "@/lib/api";

const forgotSchema = z.object({
  email: z.string().email("Please enter a valid email address."),
});

type ForgotValues = z.infer<typeof forgotSchema>;

export default function ForgotPasswordPage() {
  const [resetLink, setResetLink] = useState<string | null>(null);
  const [submittedFor, setSubmittedFor] = useState<string | null>(null);

  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotValues>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    const result = await requestPasswordReset(values.email);
    setSubmittedFor(values.email);
    setResetLink(result.reset_link ?? null);
  });

  return (
    <main className="flex min-h-dvh items-center justify-center px-5 py-16">
      <div className="w-full max-w-md space-y-4">
        <div className="flex justify-center">
          <Logo />
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="font-display text-2xl">Forgot password</CardTitle>
            <CardDescription>
              Enter your email and we will send a reset link. In this demo the link is shown
              here instead of being emailed.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={onSubmit} noValidate className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="email" className="text-sm font-medium">
                  Email
                </label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  {...field("email")}
                  aria-invalid={Boolean(errors.email)}
                  placeholder="you@example.com"
                />
                {errors.email && <FieldError message={errors.email.message} />}
              </div>
              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <MailCheck className="h-4 w-4" aria-hidden />
                )}
                Send reset link
              </Button>
            </form>

            {resetLink && submittedFor && (
              <div
                role="status"
                className="space-y-2 rounded-md border border-primary/30 bg-secondary/50 p-4"
              >
                <p className="flex items-center gap-2 text-sm font-medium text-primary">
                  <MailCheck className="h-4 w-4" aria-hidden />
                  Demo reset link for {submittedFor}:
                </p>
                <Link
                  href={resetLink}
                  className="block break-all font-mono text-xs text-primary underline underline-offset-4"
                >
                  {resetLink}
                </Link>
                <p className="text-xs text-muted-foreground">
                  In production this link would be emailed instead of shown.
                </p>
              </div>
            )}

            <p className="text-center text-sm text-muted-foreground">
              <Link href="/login" className="underline-offset-4 hover:underline">
                Back to sign in
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

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
