"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { globalSearch, type SearchResult } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

export function GlobalSearch() {
  const role = useAuthStore((state) => state.user?.role);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const search = useQuery({
    queryKey: ["global-search", query],
    queryFn: () => globalSearch(query),
    enabled: query.trim().length >= 2,
  });

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const results: SearchResult[] = query.trim().length >= 2 ? (search.data?.results ?? []) : [];

  return (
    <div className="relative w-full max-w-xs" ref={boxRef}>
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search…"
          aria-label="Global search"
          className="h-9 w-full rounded-md border border-input bg-background pl-8 pr-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>
      {open && query.trim().length >= 2 && (
        <div
          className="absolute left-0 top-10 z-50 w-full overflow-hidden rounded-lg border border-border bg-card shadow-lg"
          role="listbox"
          aria-label="Search results"
        >
          {search.isFetching ? (
            <p className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> Searching…
            </p>
          ) : results.length === 0 ? (
            <p className="px-3 py-3 text-sm text-muted-foreground">No matches found.</p>
          ) : (
            <ul className="max-h-72 overflow-y-auto">
              {results.map((result, index) => (
                <li
                  key={`${result.type}-${result.label}-${index}`}
                  className="flex items-center justify-between gap-2 border-b border-border/60 px-3 py-2 text-sm last:border-0"
                >
                  <span className="truncate font-medium">{result.label}</span>
                  <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                    {result.type}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <span className="sr-only">
        Search scope: {role ?? "your role"}
      </span>
    </div>
  );
}
