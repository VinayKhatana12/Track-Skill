"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Mail, MapPin, Phone } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { submitContact, type ContactPayload } from "@/lib/api";

const ROLES = ["PROVIDER", "TRAINEE", "EMPLOYER", "ADMIN", "OTHER"] as const;
type ContactRole = ContactPayload["role"];
const MAP_PLACEHOLDER = "Map placeholder — deployment region shown here in the production build.";

export function ContactSection() {
  const [form, setForm] = useState<{
    name: string;
    email: string;
    organisation: string;
    role: ContactRole;
    message: string;
  }>({ name: "", email: "", organisation: "", role: "PROVIDER", message: "" });
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () => submitContact(form),
    onSuccess: (result) => {
      setConfirmation(result.message);
      setForm({ name: "", email: "", organisation: "", role: "PROVIDER", message: "" });
      setFieldError(null);
    },
    onError: () => setFieldError(null),
  });

  const handleSubmit = (formEvent: FormEvent<HTMLFormElement>) => {
    formEvent.preventDefault();
    const name = form.name.trim();
    const email = form.email.trim();
    if (name.length < 2) {
      setFieldError("Please enter your full name.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setFieldError("Please enter a valid email address.");
      return;
    }
    if (form.message.trim().length < 10) {
      setFieldError("Please write at least a short message (10+ characters).");
      return;
    }
    setFieldError(null);
    submit.mutate();
  };

  const update = (key: keyof typeof form) => (value: string) =>
    setForm((previous) => ({ ...previous, [key]: value }));

  return (
    <section id="contact" aria-labelledby="contact-heading" className="scroll-mt-20 py-16 md:py-20">
      <div className="container">
        <div className="mb-10 max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
            Contact
          </p>
          <h2 id="contact-heading" className="mt-2 font-display text-3xl font-semibold tracking-tight">
            Talk to the team
          </h2>
          <p className="mt-3 text-muted-foreground">
            Missions, centres and employers — ask anything about piloting TrackSkill AI.
            This form posts to the live API and stores your enquiry.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl">Send an enquiry</CardTitle>
              <CardDescription>All fields except organisation are required.</CardDescription>
            </CardHeader>
            <CardContent>
              {submit.isSuccess ? (
                <div
                  role="status"
                  className="flex flex-col items-start gap-3 rounded-md border border-primary/30 bg-secondary/50 p-5"
                >
                  <p className="flex items-center gap-2 font-medium text-primary">
                    <CheckCircle2 className="h-5 w-5" aria-hidden />
                    Enquiry received — thank you!
                  </p>
                  <p className="text-sm text-muted-foreground">{confirmation}</p>
                  <Button variant="outline" size="sm" onClick={() => submit.reset()}>
                    Send another
                  </Button>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Full name" htmlFor="contact-name">
                      <Input
                        id="contact-name"
                        value={form.name}
                        onChange={(e) => update("name")(e.target.value)}
                        autoComplete="name"
                        required
                      />
                    </Field>
                    <Field label="Email" htmlFor="contact-email">
                      <Input
                        id="contact-email"
                        type="email"
                        value={form.email}
                        onChange={(e) => update("email")(e.target.value)}
                        autoComplete="email"
                        required
                      />
                    </Field>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Organisation (optional)" htmlFor="contact-org">
                      <Input
                        id="contact-org"
                        value={form.organisation}
                        onChange={(e) => update("organisation")(e.target.value)}
                        autoComplete="organization"
                      />
                    </Field>
                    <Field label="I am a…" htmlFor="contact-role">
                      <select
                        id="contact-role"
                        value={form.role}
                        onChange={(event) => update("role")(event.target.value as ContactRole)}
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>
                            {role === "OTHER" ? "Other" : role.charAt(0) + role.slice(1).toLowerCase()}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                  <Field label="Message" htmlFor="contact-message">
                    <textarea
                      id="contact-message"
                      value={form.message}
                      onChange={(event) => update("message")(event.target.value)}
                      rows={4}
                      required
                      minLength={10}
                      className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      placeholder="What would you like to know or pilot?"
                    />
                  </Field>

                  {fieldError && (
                    <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      {fieldError}
                    </p>
                  )}
                  {submit.isError && (
                    <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      Could not submit right now. Please try again.
                    </p>
                  )}

                  <Button type="submit" disabled={submit.isPending}>
                    {submit.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : null}
                    Send enquiry
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="font-display text-lg">Reach the team</CardTitle>
                <CardDescription>
                  Demo contact block — replace with mission details in production.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <p className="flex items-center gap-2">
                  <Mail className="h-4 w-4 text-primary" aria-hidden />
                  <a href="mailto:hello@trackskill.example" className="underline-offset-4 hover:underline">
                    hello@trackskill.example
                  </a>
                </p>
                <p className="flex items-center gap-2">
                  <Phone className="h-4 w-4 text-primary" aria-hidden />
                  <span>+00 000 000 0000 (demo)</span>
                </p>
                <p className="flex items-start gap-2">
                  <MapPin className="mt-0.5 h-4 w-4 text-primary" aria-hidden />
                  <span>State Skilling Mission (demo), Room 000, Capital Complex</span>
                </p>
                <p className="text-xs italic text-muted-foreground">
                  Sample contact details — no real office.
                </p>
              </CardContent>
            </Card>

            <div
              role="img"
              aria-label={MAP_PLACEHOLDER}
              className="flex h-48 items-center justify-center rounded-xl border border-dashed border-border bg-muted/40 text-center text-sm text-muted-foreground"
            >
              <span className="max-w-[16rem]">{MAP_PLACEHOLDER}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  htmlFor,
  error,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}