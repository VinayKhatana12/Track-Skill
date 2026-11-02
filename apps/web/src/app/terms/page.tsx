import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of use",
  description: "Terms that apply to the TrackSkill AI capstone demo.",
};

const TERMS = [
  {
    heading: "Demo software",
    body: "TrackSkill AI is a capstone project made available for evaluation. It is provided as-is, without warranties of any kind, and must not be used to make real funding or hiring decisions in its current form.",
  },
  {
    heading: "Sample data only",
    body: "All accounts, trainees, employers, outcomes and statistics in this environment are generated sample data. Any resemblance to real persons or organisations is unintentional, and testimonial content is explicitly labelled as illustrative.",
  },
  {
    heading: "Simulated communications",
    body: "The WhatsApp, IVR and SMS gateways are simulated locally. No messages are sent to real phone networks, and phone numbers in the demo are fictional.",
  },
  {
    heading: "Acceptable use",
    body: "Do not attempt to disrupt the demo, extract other users' data, or submit unlawful content through public forms. Enquiries are stored and may be reviewed by the demo team.",
  },
  {
    heading: "Credits",
    body: "Built with Next.js, FastAPI, PostgreSQL and open-source libraries. The skills taxonomy and all copy are original to this project.",
  },
] as const;

export default function TermsPage() {
  return (
    <main className="container max-w-3xl py-16">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Terms of use</h1>
      <p className="mt-3 text-muted-foreground">Demo evaluation terms. Last updated: November 2026.</p>
      <div className="mt-10 space-y-8">
        {TERMS.map((term) => (
          <section key={term.heading} aria-labelledby={`terms-${term.heading.split(" ")[0].toLowerCase()}`}>
            <h2 id={`terms-${term.heading.split(" ")[0].toLowerCase()}`} className="font-display text-xl font-semibold">
              {term.heading}
            </h2>
            <p className="mt-2 leading-relaxed text-muted-foreground">{term.body}</p>
          </section>
        ))}
      </div>
    </main>
  );
}
