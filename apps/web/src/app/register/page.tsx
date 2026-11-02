"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Loader2, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { PasswordStrengthMeter } from "@/components/auth/password-strength";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/types/api";

const registerSchema = z
  .object({
    role: z.enum(["TRAINEE", "EMPLOYER"]),
    name: z.string().min(2, "Please enter your full name."),
    email: z.string().email("Please enter a valid email address."),
    password: z
      .string()
      .min(10, "Use at least 10 characters.")
      .regex(/[A-Z]/, "Needs an uppercase letter.")
      .regex(/[a-z]/, "Needs a lowercase letter.")
      .regex(/[0-9]/, "Needs a number.")
      .regex(/[^A-Za-z0-9]/, "Needs a symbol."),
    phone: z.string().optional(),
    district: z.string().optional(),
    centre_code: z.string().optional(),
    company_name: z.string().optional(),
    company_district: z.string().optional(),
    acknowledge: z.boolean(),
  })
  .superRefine((data, ctx) => {
    if (data.role === "TRAINEE") {
      if (!data.phone || data.phone.trim().length < 5) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["phone"],
          message: "Please enter a contact number.",
        });
      }
      if (!data.district || data.district.trim().length < 2) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["district"],
          message: "Please enter your district.",
        });
      }
    } else if (!data.company_name || data.company_name.trim().length < 2) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["company_name"],
        message: "Please enter your company name.",
      });
    }
  });

type RegisterValues = z.infer<typeof registerSchema>;

const STEPS = ["Account", "Profile", "Consent"] as const;

const STEP_HINTS: Record<"TRAINEE" | "EMPLOYER", string> = {
  TRAINEE:
    "Consent means we may send you follow-up messages at 3, 6 and 12 months after certification — asking about your job, wage or studies.",
  EMPLOYER:
    "As an employer you confirm or dispute employment claims for trainees who name you. Verified outcomes count towards their centre's performance.",
};

const CHANNELS = [
  { id: "WHATSAPP", label: "WhatsApp" },
  { id: "IVR", label: "IVR call" },
  { id: "SMS", label: "SMS" },
] as const;

export default function RegisterPage() {
  const router = useRouter();
  const { status, user, error, clearError, signUp, bootstrap } = useAuthStore();
  const [step, setStep] = useState(0);
  const [consentChannels, setConsentChannels] = useState<string[]>(["WHATSAPP"]);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register: field,
    handleSubmit,
    trigger,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    mode: "onTouched",
    defaultValues: {
      role: "TRAINEE",
      name: "",
      email: "",
      password: "",
      phone: "",
      district: "",
      centre_code: "",
      company_name: "",
      company_district: "",
      acknowledge: false,
    },
  });

  const role = watch("role");
  const password = watch("password");

  useEffect(() => {
    if (status === "idle") {
      void bootstrap();
    }
  }, [status, bootstrap]);

  useEffect(() => {
    if (status === "authenticated" && user) {
      router.replace(`/dashboard/${user.role.toLowerCase()}`);
    }
  }, [status, user, router]);

  const nextFromAccount = async () => {
    const valid = await trigger(["role", "name", "email", "password"]);
    if (valid) {
      setStep(1);
    }
  };

  const nextFromProfile = async () => {
    const fields =
      role === "TRAINEE" ? (["phone", "district"] as const) : (["company_name"] as const);
    const valid = await trigger(fields);
    if (valid) {
      setStep(2);
    }
  };

  const toggleChannel = (channel: string) =>
    setConsentChannels((previous) =>
      previous.includes(channel)
        ? previous.filter((item) => item !== channel)
        : [...previous, channel],
    );

  const onFinalSubmit = handleSubmit(async (values) => {
    clearError();
    setSubmitError(null);
    try {
      await signUp({
        name: values.name,
        email: values.email,
        password: values.password,
        role: values.role,
        phone: values.role === "TRAINEE" ? values.phone : undefined,
        district: values.role === "TRAINEE" ? values.district : undefined,
        centre_code: values.role === "TRAINEE" ? values.centre_code || undefined : undefined,
        company_name: values.role === "EMPLOYER" ? values.company_name : undefined,
        company_district: values.role === "EMPLOYER" ? values.company_district : undefined,
        consent_channels:
          values.role === "TRAINEE"
            ? consentChannels
            : [],
      });
      router.replace(`/dashboard/${values.role.toLowerCase()}`);
    } catch {
      setSubmitError("Registration failed. Please review the errors and try again.");
    }
  });

  const busy = isSubmitting || status === "loading";

  return (
    <main className="flex min-h-dvh items-center justify-center px-5 py-16">
      <div className="w-full max-w-md space-y-4">
        <div className="flex justify-center">
          <Logo />
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="font-display text-2xl">Create an account</CardTitle>
            <CardDescription>
              Step {step + 1} of {STEPS.length}: {STEPS[step]}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="mb-5 flex gap-1.5" aria-hidden>
              {STEPS.map((label, index) => (
                <span
                  key={label}
                  className={cn("h-1.5 flex-1 rounded-full", index <= step ? "bg-primary" : "bg-border")}
                />
              ))}
            </div>

            <form onSubmit={onFinalSubmit} noValidate>
              <AnimatePresence mode="wait" initial={false}>
                {step === 0 && (
                  <motion.div
                    key="step-account"
                    initial={{ opacity: 0, x: 16 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -16 }}
                    transition={{ duration: reduceSafe() }}
                    className="space-y-4"
                  >
                    <fieldset className="space-y-2">
                      <legend className="text-sm font-medium">I am joining as</legend>
                      <div className="grid grid-cols-2 gap-2">
                        {(["TRAINEE", "EMPLOYER"] as const).map((option) => (
                          <label
                            key={option}
                            className={cn(
                              "flex cursor-pointer items-center justify-center rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                              role === option
                                ? "border-primary bg-secondary text-secondary-foreground"
                                : "border-input hover:bg-accent",
                            )}
                          >
                            <input
                              type="radio"
                              value={option}
                              {...field("role")}
                              className="sr-only"
                            />
                            {option === "TRAINEE" ? "Trainee" : "Employer"}
                          </label>
                        ))}
                      </div>
                    </fieldset>

                    <div className="space-y-2">
                      <label htmlFor="reg-name" className="text-sm font-medium">
                        Full name
                      </label>
                      <Input
                        id="reg-name"
                        autoComplete="name"
                        {...field("name")}
                        aria-invalid={Boolean(errors.name)}
                        placeholder="Your name"
                      />
                      {errors.name && <FieldError message={errors.name.message} />}
                    </div>

                    <div className="space-y-2">
                      <label htmlFor="reg-email" className="text-sm font-medium">
                        Email
                      </label>
                      <Input
                        id="reg-email"
                        type="email"
                        autoComplete="email"
                        {...field("email")}
                        aria-invalid={Boolean(errors.email)}
                        placeholder="you@example.com"
                      />
                      {errors.email && <FieldError message={errors.email.message} />}
                    </div>

                    <div className="space-y-2">
                      <label htmlFor="reg-password" className="text-sm font-medium">
                        Password
                      </label>
                      <Input
                        id="reg-password"
                        type="password"
                        autoComplete="new-password"
                        {...field("password")}
                        aria-invalid={Boolean(errors.password)}
                      />
                      <PasswordStrengthMeter password={password ?? ""} />
                      {errors.password && <FieldError message={errors.password.message} />}
                    </div>
                  </motion.div>
                )}

                {step === 1 && role === "TRAINEE" && (
                  <motion.div
                    key="step-profile-trainee"
                    initial={{ opacity: 0, x: 16 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -16 }}
                    transition={{ duration: reduceSafe() }}
                    className="space-y-4"
                  >
                    <div className="space-y-2">
                      <label htmlFor="reg-phone" className="text-sm font-medium">
                        Phone number
                      </label>
                      <Input
                        id="reg-phone"
                        type="tel"
                        autoComplete="tel"
                        {...field("phone")}
                        aria-invalid={Boolean(errors.phone)}
                        placeholder="+91 …"
                      />
                      {errors.phone && <FieldError message={errors.phone.message} />}
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="reg-district" className="text-sm font-medium">
                        District
                      </label>
                      <Input
                        id="reg-district"
                        {...field("district")}
                        aria-invalid={Boolean(errors.district)}
                        placeholder="e.g. North District"
                      />
                      {errors.district && <FieldError message={errors.district.message} />}
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="reg-centre" className="text-sm font-medium">
                        Centre code{" "}
                        <span className="font-normal text-muted-foreground">(if already enrolled)</span>
                      </label>
                      <Input id="reg-centre" {...field("centre_code")} placeholder="e.g. TC-01" />
                      <p className="text-xs text-muted-foreground">
                        Ask your training centre for its code. You can skip this and be linked
                        later.
                      </p>
                    </div>
                  </motion.div>
                )}

                {step === 1 && role === "EMPLOYER" && (
                  <motion.div
                    key="step-profile-employer"
                    initial={{ opacity: 0, x: 16 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -16 }}
                    transition={{ duration: reduceSafe() }}
                    className="space-y-4"
                  >
                    <div className="space-y-2">
                      <label htmlFor="reg-company" className="text-sm font-medium">
                        Company name
                      </label>
                      <Input
                        id="reg-company"
                        autoComplete="organization"
                        {...field("company_name")}
                        aria-invalid={Boolean(errors.company_name)}
                      />
                      {errors.company_name && <FieldError message={errors.company_name.message} />}
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="reg-company-district" className="text-sm font-medium">
                        District
                      </label>
                      <Input
                        id="reg-company-district"
                        {...field("company_district")}
                        aria-invalid={Boolean(errors.company_district)}
                      />
                      {errors.company_district && (
                        <FieldError message={errors.company_district.message} />
                      )}
                    </div>
                  </motion.div>
                )}

                {step === 2 && (
                  <motion.div
                    key="step-consent"
                    initial={{ opacity: 0, x: 16 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -16 }}
                    transition={{ duration: reduceSafe() }}
                    className="space-y-4"
                  >
                    <p className="text-sm leading-relaxed text-muted-foreground">
                      {STEP_HINTS[role as "TRAINEE" | "EMPLOYER"]}
                    </p>

                    {role === "TRAINEE" && (
                      <fieldset className="space-y-2">
                        <legend className="text-sm font-medium">
                          Choose your tracer channels (consent version 1.0)
                        </legend>
                        {CHANNELS.map((channel) => (
                          <label
                            key={channel.id}
                            className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
                          >
                            <span>{channel.label}</span>
                            <input
                              type="checkbox"
                              checked={consentChannels.includes(channel.id)}
                              onChange={() => toggleChannel(channel.id)}
                              className="h-4 w-4"
                            />
                          </label>
                        ))}
                        <p className="text-xs text-muted-foreground">
                          Consent is version-stamped and stored via the API. You can revoke any
                          channel later — revoking cancels undelivered tracers. Tracers start once
                          a provider certifies you.
                        </p>
                      </fieldset>
                    )}

                    {role === "EMPLOYER" && (
                      <p className="rounded-md bg-secondary/60 px-3 py-2 text-sm text-secondary-foreground">
                        No tracer consent applies to employers. You will see verification claims
                        only for trainees who name your company.
                      </p>
                    )}

                    <label className="flex items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        {...field("acknowledge")}
                        className="mt-0.5 h-4 w-4"
                        aria-invalid={Boolean(errors.acknowledge)}
                      />
                      <span>
                        I understand my data is demo sample data and I have read the{" "}
                        <a href="/privacy" className="underline underline-offset-4">
                          privacy notice
                        </a>
                        .
                      </span>
                    </label>
                    {errors.acknowledge && <FieldError message={errors.acknowledge.message} />}

                    {(error || submitError) && (
                      <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                        {error ?? submitError}
                      </p>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="mt-5 flex items-center justify-between gap-2">
                {step > 0 ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setStep((current) => current - 1)}
                    disabled={busy}
                  >
                    <ArrowLeft className="h-4 w-4" aria-hidden />
                    Back
                  </Button>
                ) : (
                  <span />
                )}
                {step < 2 ? (
                  <Button
                    type="button"
                    onClick={step === 0 ? nextFromAccount : nextFromProfile}
                    disabled={busy}
                  >
                    Continue
                    <ArrowRight className="h-4 w-4" aria-hidden />
                  </Button>
                ) : (
                  <Button type="submit" disabled={busy}>
                    {busy ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <UserPlus className="h-4 w-4" aria-hidden />
                    )}
                    Create account
                  </Button>
                )}
              </div>
            </form>

            <p className="mt-4 text-center text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link
                href="/login"
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                Sign in
              </Link>
            </p>
          </CardContent>
        </Card>

        <p className="text-center text-sm text-muted-foreground">
          <Link href="/" className="underline-offset-4 hover:underline">
            Back to the landing page
          </Link>
        </p>
      </div>
    </main>
  );
}

function reduceSafe() {
  return { duration: 0.2 };
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
