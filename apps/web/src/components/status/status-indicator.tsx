import { cn } from "@/lib/utils";

export type StatusTone = "online" | "offline" | "connecting";

const toneStyles: Record<StatusTone, { dot: string; text: string; label: string }> = {
  online: {
    dot: "bg-emerald-500",
    text: "text-emerald-600 dark:text-emerald-400",
    label: "Online",
  },
  offline: {
    dot: "bg-red-500",
    text: "text-red-600 dark:text-red-400",
    label: "Offline",
  },
  connecting: {
    dot: "bg-marigold-400 animate-pulse",
    text: "text-marigold-700 dark:text-marigold-300",
    label: "Connecting",
  },
};

export function StatusIndicator({ tone, label }: { tone: StatusTone; label?: string }) {
  const styles = toneStyles[tone];
  return (
    <span className="inline-flex items-center gap-2 text-sm font-medium" role="status">
      <span className={cn("h-2.5 w-2.5 rounded-full", styles.dot)} aria-hidden />
      <span className={styles.text}>{label ?? styles.label}</span>
    </span>
  );
}
