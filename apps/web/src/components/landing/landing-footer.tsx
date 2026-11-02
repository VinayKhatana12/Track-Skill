"use client";

import { Logo } from "@/components/logo";

const LINK_GROUPS = [
  {
    heading: "Product",
    links: [
      { href: "/#features", label: "Features" },
      { href: "/#how-it-works", label: "How it works" },
      { href: "/#roles", label: "Role explorer" },
      { href: "/register", label: "Get started" },
    ],
  },
  {
    heading: "Resources",
    links: [
      { href: "/#faq", label: "FAQ" },
      { href: "/#contact", label: "Contact" },
      { href: "/privacy", label: "Privacy" },
      { href: "/terms", label: "Terms of use" },
    ],
  },
  {
    heading: "Demo access",
    links: [
      { href: "/login?role=PROVIDER", label: "Try as Provider" },
      { href: "/login?role=TRAINEE", label: "Try as Trainee" },
      { href: "/login?role=EMPLOYER", label: "Try as Employer" },
      { href: "/login?role=ADMIN", label: "Try as Admin" },
    ],
  },
] as const;

export function LandingFooter() {
  return (
    <footer className="border-t border-border/70 bg-background py-12">
      <div className="container grid gap-10 md:grid-cols-[1.2fr_repeat(3,1fr)]">
        <div className="space-y-3">
          <Logo />
          <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
            Consent-based outcome tracking, AI curriculum matching and governance
            analytics for skilling programs. Capstone demo — all data is sample data.
          </p>
          <p className="text-xs text-muted-foreground">
            Aligned with SDG 8 (primary), SDG 4 and SDG 9.
          </p>
        </div>

        {LINK_GROUPS.map((group) => (
          <nav key={group.heading} aria-label={group.heading}>
            <h3 className="text-sm font-semibold">{group.heading}</h3>
            <ul className="mt-3 space-y-2">
              {group.links.map((link) => (
                <li key={link.href + link.label}>
                  <a
                    href={link.href}
                    className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>

      <div className="container mt-10 flex flex-col items-start justify-between gap-2 border-t border-border/70 pt-6 text-xs text-muted-foreground sm:flex-row sm:items-center">
        <p>© 2026 TrackSkill AI — capstone project. English-only demo build.</p>
        <p>
          <a href="/privacy" className="underline-offset-4 hover:underline">
            Privacy
          </a>
          {" · "}
          <a href="/terms" className="underline-offset-4 hover:underline">
            Terms
          </a>
        </p>
      </div>
    </footer>
  );
}
