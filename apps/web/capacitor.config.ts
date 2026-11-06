import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Capacitor wrapper (optional Phase 10 sub-step a).
 *
 * The web app is a Next.js server, not a static export, so the Android build
 * points at a running deployment instead of bundling files: the emulator
 * reaches the host machine on 10.0.2.2, a physical device needs your LAN IP
 * (set CAP_SERVER_URL), and a production APK points at the deployed origin.
 *
 * Exact commands — needs JDK 17 and the Android SDK (Android Studio):
 *   cd apps/web
 *   npm install -D @capacitor/cli
 *   npm install @capacitor/core @capacitor/android
 *   npx cap add android
 *   npx cap sync android
 *   npx cap open android        # or build straight from the CLI:
 *   cd android && ./gradlew assembleDebug
 *   # APK: apps/web/android/app/build/outputs/apk/debug/app-debug.apk
 */
const config: CapacitorConfig = {
  appId: "in.trackskill.app",
  appName: "TrackSkill",
  webDir: "public",
  server: {
    url: process.env.CAP_SERVER_URL ?? "http://10.0.2.2:3000",
    cleartext: true, // local demo runs over plain http
  },
  android: {
    allowMixedContent: false,
  },
};

export default config;
