import type { Metadata, Viewport } from "next";
import { Public_Sans, Space_Grotesk } from "next/font/google";

import { PwaRoot } from "@/components/pwa/pwa-root";
import { Providers } from "./providers";

import "./globals.css";

const publicSans = Public_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "TrackSkill AI",
    template: "%s | TrackSkill AI",
  },
  description:
    "Consent-based trainee outcome tracking at 3/6/12-month milestones, AI curriculum-to-market matching and governance analytics with a Provider Performance Index.",
  applicationName: "TrackSkill AI",
  appleWebApp: {
    capable: true,
    title: "TrackSkill",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FAF9F6" },
    { media: "(prefers-color-scheme: dark)", color: "#0F171A" },
  ],
};

/** Apple startup images — one link per standard device size (3x phones plus
 * the 12.9-inch iPad at 2x). */
const APPLE_SPLASHES_3X = [
  { width: 1290, height: 2796, deviceWidth: 430, deviceHeight: 932 },
  { width: 1179, height: 2556, deviceWidth: 393, deviceHeight: 852 },
  { width: 1284, height: 2778, deviceWidth: 428, deviceHeight: 926 },
  { width: 1170, height: 2532, deviceWidth: 390, deviceHeight: 844 },
  { width: 1125, height: 2436, deviceWidth: 375, deviceHeight: 812 },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {APPLE_SPLASHES_3X.map(({ width, height, deviceWidth, deviceHeight }) => (
          <link
            key={`${width}x${height}`}
            rel="apple-touch-startup-image"
            media={`(device-width: ${deviceWidth}px) and (device-height: ${deviceHeight}px) and (-webkit-device-pixel-ratio: 3)`}
            href={`/splash/splash-${width}x${height}.png`}
          />
        ))}
        <link
          rel="apple-touch-startup-image"
          media="(device-width: 1024px) and (device-height: 1366px) and (-webkit-device-pixel-ratio: 2)"
          href="/splash/splash-2048x2732.png"
        />
      </head>
      <body className={`${publicSans.variable} ${spaceGrotesk.variable} font-sans`}>
        <Providers>
          {children}
          <PwaRoot />
        </Providers>
      </body>
    </html>
  );
}
