import type { Metadata } from "next";

import { LandingPage } from "@/components/landing/landing-page";

const title = "TrackSkill AI — Close the post-certification blind spot";
const description =
  "Consent-based trainee outcome tracking at 3/6/12 months, dual-signal verification, AI curriculum matching and a Provider Performance Index for skilling programs.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/" },
  openGraph: {
    title,
    description,
    url: "/",
    siteName: "TrackSkill AI",
    type: "website",
    locale: "en_GB",
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
  },
};

export default function HomePage() {
  return <LandingPage />;
}
