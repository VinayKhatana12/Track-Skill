import { cn } from "@/lib/utils";

/** Rising milestone path — the TrackSkill AI brand mark. */
export function Logo({
  className,
  withWordmark = true,
}: {
  className?: string;
  withWordmark?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg viewBox="0 0 32 32" role="img" aria-label="TrackSkill AI logo" className="h-8 w-8">
        <rect width="32" height="32" rx="8" fill="#1E5D5F" />
        <path
          d="M6 24.5 L13 18 L19.5 13.5 L26 7.5"
          fill="none"
          stroke="#E3AE27"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="13" cy="18" r="2.1" fill="#EEF9F7" />
        <circle cx="19.5" cy="13.5" r="2.1" fill="#EEF9F7" />
        <path
          d="M20.8 7.1 L26 7.5 L25.6 12.7"
          fill="none"
          stroke="#E3AE27"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {withWordmark && (
        <span className="font-display text-lg font-semibold tracking-tight">
          TrackSkill <span className="text-primary">AI</span>
        </span>
      )}
    </span>
  );
}
