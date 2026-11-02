import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy",
  description:
    "How the TrackSkill AI demo handles consent, personal data and tracer messages.",
};

const SECTIONS = [
  {
    heading: "Consent comes first",
    body: "A trainee is traced only after granting consent for a channel (WhatsApp, IVR or SMS) from their own dashboard. Consent is stored per channel with a purpose statement and version, and can be revoked at any time. Revoking cancels every tracer that has not yet been delivered — this rule is enforced in the database layer, not just the interface.",
  },
  {
    heading: "What we store",
    body: "The demo stores: account basics (name, email, bcrypt-hashed password, role), enrolment and certification dates, consent records, tracer messages and replies, employment records, and verification signals. Tracer replies may contain free text; the reply parser extracts structured fields and always preserves the original text alongside them.",
  },
  {
    heading: "This is sample data",
    body: "Every person, organisation, phone number and outcome in this demo environment is generated sample data. No real trainees, employers or missions are represented.",
  },
  {
    heading: "Who can see what",
    body: "Role-based access control is enforced on the backend. Providers see only their own centre, trainees only their own data, employers only verifications that name their company, and admins see aggregates and the audit feed. Contact enquiries submitted through the landing page are stored for the demo team only.",
  },
  {
    heading: "Your choices",
    body: "In the production vision, a trainee can export or delete their profile on request. In this demo, deleting a user (with consent rows and tracers cascading) is possible through the database and demonstrates the same data-minimisation posture.",
  },
] as const;

export default function PrivacyPage() {
  return (
    <main className="container max-w-3xl py-16">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Privacy</h1>
      <p className="mt-3 text-muted-foreground">
        Consent-first, sample-data-only. Last updated: November 2026 (demo).
      </p>
      <div className="mt-10 space-y-8">
        {SECTIONS.map((section) => (
          <section key={section.heading} aria-labelledby={`privacy-${section.heading.split(" ")[0].toLowerCase()}`}>
            <h2 id={`privacy-${section.heading.split(" ")[0].toLowerCase()}`} className="font-display text-xl font-semibold">
              {section.heading}
            </h2>
            <p className="mt-2 leading-relaxed text-muted-foreground">{section.body}</p>
          </section>
        ))}
      </div>
    </main>
  );
}
