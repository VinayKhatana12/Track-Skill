import type { MetadataRoute } from "next";

/** PWA manifest — installable app with role shortcuts. The service worker
 * (public/sw.js) handles offline caching, background sync and push. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/dashboard",
    name: "TrackSkill AI",
    short_name: "TrackSkill",
    description:
      "Consent-based trainee outcome tracking, AI curriculum matching and governance analytics for skilling programs.",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    // Portrait-first for the native feel on phones; desktop standalone windows
    // ignore the orientation lock and tablets can still be rotated.
    orientation: "portrait",
    background_color: "#FAF9F6",
    theme_color: "#1E5D5F",
    categories: ["education", "productivity", "business"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icons/icon-maskable-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    shortcuts: [
      {
        name: "Provider command centre",
        short_name: "Provider",
        description: "Enrol trainees, run follow-ups and view centre insights.",
        url: "/dashboard/provider",
        icons: [{ src: "/icons/shortcut-provider.png", sizes: "96x96", type: "image/png" }],
      },
      {
        name: "My journey",
        short_name: "Trainee",
        description: "Milestones, consent and simulated tracer messages.",
        url: "/dashboard/trainee",
        icons: [{ src: "/icons/shortcut-trainee.png", sizes: "96x96", type: "image/png" }],
      },
      {
        name: "Verify and hire",
        short_name: "Employer",
        description: "Confirm employment claims and browse the talent pool.",
        url: "/dashboard/employer",
        icons: [{ src: "/icons/shortcut-employer.png", sizes: "96x96", type: "image/png" }],
      },
      {
        name: "Governance",
        short_name: "Admin",
        description: "Provider Performance Index, gaps and fund allocations.",
        url: "/dashboard/admin",
        icons: [{ src: "/icons/shortcut-admin.png", sizes: "96x96", type: "image/png" }],
      },
    ],
  };
}
