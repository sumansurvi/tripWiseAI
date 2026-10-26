"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { TripThread } from "@/lib/api";

type Props = {
  open: boolean;
  onClose: () => void;
  trips: TripThread[];
  onSelectTrip: (id: string) => void;
  onSearch: (query: string) => void;
};

function matchTrips(trips: TripThread[], q: string): TripThread[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return trips.slice(0, 8);
  return trips
    .filter(
      (t) =>
        t.title.toLowerCase().includes(needle) ||
        t.messages.some((m) => m.content.toLowerCase().includes(needle))
    )
    .slice(0, 8);
}

export function SearchModal({
  open,
  onClose,
  trips,
  onSelectTrip,
  onSearch,
}: Props) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    const t = window.setTimeout(() => inputRef.current?.focus(), 30);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const suggestions = useMemo(() => matchTrips(trips, query), [trips, query]);

  if (!open) return null;

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    onSearch(q);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[12vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Search trips"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-[color:var(--border)] bg-[color:var(--bg)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <form onSubmit={submit} className="border-b border-[color:var(--border)] p-4">
          <div className="flex items-center gap-3 rounded-xl border border-[color:var(--border)] px-4 py-3">
            <svg
              aria-hidden
              className="h-5 w-5 shrink-0 text-[color:var(--muted)]"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 21l-4.35-4.35M11 18a7 7 0 100-14 7 7 0 000 14z"
              />
            </svg>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search trip history or ask a new research question…"
              className="w-full bg-transparent text-base outline-none placeholder:text-[color:var(--muted)]"
            />
            <kbd className="hidden shrink-0 rounded border border-[color:var(--border)] px-1.5 py-0.5 text-[10px] text-[color:var(--muted)] sm:inline">
              Esc
            </kbd>
          </div>
          <p className="mt-2 text-xs text-[color:var(--muted)]">
            Pick a past trip below, or press Enter to research this question.
          </p>
        </form>

        <div className="max-h-[50vh] overflow-y-auto p-2">
          <p className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[color:var(--muted)]">
            {query.trim() ? "Matching history" : "Recent history"}
          </p>
          {suggestions.length === 0 ? (
            <p className="px-3 py-6 text-sm text-[color:var(--muted)]">
              No matching trips. Press Enter to start research on this query.
            </p>
          ) : (
            <ul className="space-y-0.5">
              {suggestions.map((t) => {
                const preview =
                  t.messages.filter((m) => m.role === "user").at(-1)?.content ??
                  "Empty trip";
                return (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onSelectTrip(t.id);
                        onClose();
                      }}
                      className="w-full rounded-lg px-3 py-2.5 text-left hover:bg-trail-50 dark:hover:bg-white/5"
                    >
                      <div className="truncate text-sm font-medium">{t.title}</div>
                      <div className="mt-0.5 truncate text-xs text-[color:var(--muted)]">
                        {preview}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
