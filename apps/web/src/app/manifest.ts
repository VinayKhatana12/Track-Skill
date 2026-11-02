import type { MetadataRoute } from "next";

/** PWA manifest — installability for the "Install app" button. The offline
 * service worker itself lands in the PWA phase. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "TrackSkill AI",
    short_name: "TrackSkill",
    description:
      "Consent-based trainee outcome tracking, AI curriculum matching and governance analytics for skilling programs.",
    start_url: "/",
    display: "standalone",
    background_color: "#faf9f6",
    theme_color: "#1e5d5f",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
  };
}
