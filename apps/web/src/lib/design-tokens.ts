/**
 * Civic-tech design tokens for TrackSkill AI.
 *
 * Petrol teal = institutions and trust (primary actions).
 * Marigold = milestones, signals and highlights.
 *
 * This file is the single source of truth for the raw colour scales:
 * tailwind.config.ts consumes it and the landing page renders swatches
 * from it, so the two can never drift apart.
 */
export const brandScale = {
  50: "#EEF9F7",
  100: "#D6F0EC",
  200: "#ADE0DA",
  300: "#7CC8C2",
  400: "#4BAAA6",
  500: "#2F8F8C",
  600: "#237474",
  700: "#1E5D5F",
  800: "#1C4B4E",
  900: "#1A3E41",
  950: "#0C2326",
} as const;

export const marigoldScale = {
  50: "#FDF8EB",
  100: "#F9EDC7",
  200: "#F2D98A",
  300: "#EAC24E",
  400: "#E3AE27",
  500: "#D69617",
  600: "#BA7712",
  700: "#955913",
  800: "#7B4716",
  900: "#693C17",
  950: "#3D1F0B",
} as const;

export const brandSwatches = Object.entries(brandScale) as [string, string][];

export const marigoldSwatches = Object.entries(marigoldScale) as [string, string][];
