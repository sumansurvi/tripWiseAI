"use client";

import { useState } from "react";
import type { TripThread } from "@/lib/api";
import { SEED_PROMPTS } from "@/lib/api";
import { useTheme } from "./ThemeProvider";
import { SearchModal } from "./SearchModal";

type Props = {
  trips: TripThread[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSeed: (prompt: string) => void;
  onSearch: (query: string) => void;
};

function PencilIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125"
      />
    </svg>
  );
}

function ChevronDown({ className, open }: { className?: string; open: boolean }) {
  return (
    <svg
      aria-hidden
      className={`${className ?? ""} transition-transform ${open ? "" : "-rotate-90"}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      className={className}
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
  );
}

function SunIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"
      />
    </svg>
  );
}

function MoonIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M21.752 15.002A9.72 9.72 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"
      />
    </svg>
  );
}

export function TripSidebar({
  trips,
  activeId,
  onSelect,
  onNew,
  onSeed,
  onSearch,
}: Props) {
  const [tripsOpen, setTripsOpen] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const { theme, toggle } = useTheme();

  return (
    <aside className="flex h-full w-full max-w-[280px] shrink-0 flex-col overflow-hidden border-r border-[color:var(--divider)] bg-[color:var(--bg)]">
      <div className="flex h-14 shrink-0 items-center gap-1 px-3">
        <div className="min-w-0 flex-1 truncate">
          <span className="font-display text-xl tracking-tight text-trail-700 dark:text-trail-300">
            TripWise
          </span>
          <span className="ml-1.5 text-[10px] uppercase tracking-widest text-[color:var(--muted)]">
            Travel guide
          </span>
        </div>
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className="shrink-0 rounded-full p-2 text-[color:var(--muted)] transition hover:bg-trail-100 hover:text-trail-700 dark:hover:bg-white/5 dark:hover:text-trail-200"
          aria-label="Search trips"
        >
          <SearchIcon className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={toggle}
          className="shrink-0 rounded-full p-2 text-[color:var(--muted)] transition hover:bg-trail-100 hover:text-trail-700 dark:hover:bg-white/5 dark:hover:text-trail-200"
          aria-label={
            theme === "dark" ? "Switch to light mode" : "Switch to dark mode"
          }
        >
          {theme === "dark" ? (
            <SunIcon className="h-5 w-5" />
          ) : (
            <MoonIcon className="h-5 w-5" />
          )}
        </button>
      </div>

      <div className="shrink-0 px-3 pb-3">
        <button
          type="button"
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-lg border border-[color:var(--border)] bg-[color:var(--bg)] px-3 py-2.5 text-sm font-medium text-[color:var(--ink)] transition hover:border-trail-400 hover:bg-trail-50 dark:hover:bg-white/5"
        >
          <PencilIcon className="h-4 w-4 shrink-0 text-trail-600 dark:text-trail-300" />
          New chat
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-2">
        <button
          type="button"
          onClick={() => setTripsOpen((o) => !o)}
          className="flex w-full shrink-0 items-center gap-1.5 px-2 py-1.5 text-left text-sm font-semibold tracking-wide text-trail-800 dark:text-trail-200"
          aria-expanded={tripsOpen}
        >
          Trips
          <ChevronDown
            open={tripsOpen}
            className="h-4 w-4 text-[color:var(--muted)]"
          />
        </button>

        {tripsOpen && (
          <div className="mt-1 min-h-0 flex-1 space-y-1 overflow-y-auto pb-3">
            {trips.length === 0 && (
              <p className="px-2 py-3 text-xs text-[color:var(--muted)]">
                No chats yet. Start a new chat or tap a question under Try asking.
              </p>
            )}
            {trips.map((t) => {
              const preview =
                t.messages.filter((m) => m.role === "user").at(-1)?.content ??
                "Empty trip";
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => onSelect(t.id)}
                  className={`w-full rounded-lg px-3 py-2.5 text-left transition ${
                    activeId === t.id
                      ? "bg-trail-100 dark:bg-trail-800/60"
                      : "hover:bg-trail-50 dark:hover:bg-white/5"
                  }`}
                >
                  <div className="truncate text-sm font-medium">{t.title}</div>
                  <div className="mt-0.5 truncate text-xs text-[color:var(--muted)]">
                    {preview}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="mt-auto shrink-0 border-t border-[color:var(--border)] p-3">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[color:var(--muted)]">
          Try asking
        </p>
        <div className="flex flex-col gap-1.5">
          {SEED_PROMPTS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onSeed(p)}
              className="rounded-md border border-[color:var(--border)] px-2 py-1.5 text-left text-xs text-[color:var(--ink)] hover:border-trail-400 hover:bg-trail-50 dark:hover:bg-white/5"
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <SearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        trips={trips}
        onSelectTrip={onSelect}
        onSearch={onSearch}
      />
    </aside>
  );
}
