"use client";

/** Retry control for the offline fallback page — client-side so it can
 * re-attempt the current URL. */
export function RetryButton() {
  return (
    <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="inline-flex min-h-11 items-center rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        Try again
      </button>
      <a
        href="/dashboard"
        className="inline-flex min-h-11 items-center rounded-md border border-input px-5 text-sm font-medium hover:bg-accent"
      >
        Open dashboard
      </a>
    </div>
  );
}
