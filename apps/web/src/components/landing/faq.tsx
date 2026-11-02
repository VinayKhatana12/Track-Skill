"use client";

import { useMemo, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const FAQS = [
  {
    question: "How does consent work? Can a trainee be traced without it?",
    answer:
      "No — consent is enforced in the database, not just the UI. A trainee grants WhatsApp, IVR or SMS consent per channel from their dashboard and can revoke it at any time. Revoking immediately cancels every tracer that has not been delivered, and the tracer engine double-checks consent again before each send.",
  },
  {
    question: "How does verification work?",
    answer:
      "Outcomes carry two independent signals: the trainee's own claim and the employer's confirmation. The verified flag becomes true only when both say CONFIRMED — enforced as a generated column in PostgreSQL. Unverified outcomes still appear, but they count at half weight in every statistic.",
  },
  {
    question: "Who can see what?",
    answer:
      "Role-based access control is enforced on the backend for every endpoint. Providers see only their own centre's trainees, trainees only their own profile and tracers, employers only verifications that name their company, and admins see state-level aggregates plus the audit feed. Every endpoint returns a generic 403 when a role tries to cross this line.",
  },
  {
    question: "What happens when a trainee types a messy reply?",
    answer:
      "The reply parser extracts employment status, job title, wage and employer with a confidence score. High-confidence replies are recorded automatically; anything below the threshold is routed to a manual-review queue that provider staff see in their dashboard — the raw text is always preserved.",
  },
  {
    question: "How is data secured?",
    answer:
      "Passwords are bcrypt-hashed, sessions use short-lived JWT access tokens plus an httpOnly refresh cookie, and all endpoints validate role and ownership server-side. The demo database contains only generated sample people — no real trainees.",
  },
  {
    question: "Does it work offline?",
    answer:
      "The web app is installable, and the tracer engine queues and retries delivery. Full offline support (service worker shell + queued replies) lands with the PWA phase — the tracer engine already stores every state transition, so nothing is lost.",
  },
  {
    question: "What does it cost?",
    answer:
      "This is a capstone demo, so there is no pricing yet. The design goal is one shared instance per state skilling mission: the heaviest cost (AI embedding) runs on a laptop-class CPU in light-NLP mode, and real gateway fees would apply only if simulated channels are replaced with Twilio/Meta.",
  },
  {
    question: "How is the PPI calculated?",
    answer:
      "PPI = 100 × (0.30·placement_rate + 0.25·retention_weighted + 0.20·wage_growth_norm + 0.15·verification_rate + 0.10·response_rate), where retention_weighted = 0.2·R3 + 0.3·R6 + 0.5·R12. Verified outcomes count fully, unverified ones at half weight. It recalculates live on every completed verification.",
  },
  {
    question: "Can the tracers use real WhatsApp or IVR gateways?",
    answer:
      "The adapter interface is ready for Twilio and Meta Cloud API — those adapters are stubs that fail loudly until real credentials exist. The simulated gateways make the full demo work with zero external accounts.",
  },
  {
    question: "What about the AI — does it invent outcomes?",
    answer:
      "No. The AI modules only classify and match: they score skills against a taxonomy, parse replies the trainee actually typed, and flag statistical anomalies. Low-confidence parses are never auto-accepted, and every score can be traced back to the input that produced it.",
  },
] as const;

export function FaqSection() {
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return FAQS;
    }
    return FAQS.filter(
      (faq) =>
        faq.question.toLowerCase().includes(needle) ||
        faq.answer.toLowerCase().includes(needle),
    );
  }, [query]);

  return (
    <section id="faq" aria-labelledby="faq-heading" className="scroll-mt-20 border-y border-border/70 bg-muted/40 py-16 md:py-20">
      <div className="container">
        <div className="mb-8 max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
            FAQ
          </p>
          <h2 id="faq-heading" className="mt-2 font-display text-3xl font-semibold tracking-tight">
            Questions missions ask first
          </h2>
          <div className="mt-4">
            <Input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search the questions…"
              aria-label="Search frequently asked questions"
              className="max-w-md"
            />
          </div>
        </div>

        {filtered.length === 0 ? (
          <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground" role="status">
            No questions match “{query}”. Try a different word.
          </p>
        ) : (
          <div className="space-y-3">
            {filtered.map((faq) => {
              const isOpen = openId === faq.question;
              const panelId = `faq-panel-${faq.question.slice(0, 20).replace(/\W+/g, "-").toLowerCase()}`;
              return (
                <Card key={faq.question} className="overflow-hidden">
                  <h3>
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      aria-controls={panelId}
                      onClick={() => setOpenId(isOpen ? null : faq.question)}
                      className={cn(
                        "flex w-full items-center justify-between gap-4 px-6 py-4 text-left text-sm font-medium transition-colors hover:bg-accent",
                        isOpen && "bg-accent/60",
                      )}
                    >
                      {faq.question}
                      <span aria-hidden className={cn("text-lg leading-none transition-transform", isOpen && "rotate-45")}>
                        +
                      </span>
                    </button>
                  </h3>
                  <div
                    id={panelId}
                    role="region"
                    hidden={!isOpen}
                    aria-labelledby={undefined}
                  >
                    <CardContent className="pt-0">
                      <p className="text-sm leading-relaxed text-muted-foreground">{faq.answer}</p>
                    </CardContent>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
