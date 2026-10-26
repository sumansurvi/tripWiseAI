"use client";

import type { ChatMessage } from "@/lib/api";
import { SuggestedFollowUps } from "@research/ResearchPanels";

type Props = {
  latestAssistant: ChatMessage | null;
  onFollowUp: (prompt: string) => void;
};

export function RightRail({ latestAssistant, onFollowUp }: Props) {
  const sources = latestAssistant?.sources ?? [];

  return (
    <aside className="hidden h-full w-[280px] shrink-0 flex-col overflow-hidden border-l border-[color:var(--divider)] bg-[color:var(--bg)] lg:flex">
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <h2 className="text-sm font-semibold text-trail-800 dark:text-trail-200">
        Next stop
      </h2>
      <p className="mt-1 text-xs text-[color:var(--muted)]">
        Proof behind this reply, and where to go from here.
      </p>

      <section className="mt-4">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-[color:var(--muted)]">
          Sources
        </h3>
        {sources.length === 0 ? (
          <p className="mt-2 text-xs text-[color:var(--muted)]">
            Sources show up here after your first answer.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {sources.map((s) => (
              <li key={s.source_url}>
                <a
                  href={s.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-lg border border-[color:var(--border)] px-2 py-2 text-xs hover:border-skyline-500"
                >
                  <div className="font-medium">{s.title}</div>
                  <div className="mt-1 break-all text-[10px] text-skyline-600 dark:text-skyline-400">
                    {s.source_url}
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-6">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-[color:var(--muted)]">
          Ask next
        </h3>
        <SuggestedFollowUps
          latest={latestAssistant}
          onPick={onFollowUp}
          className="mt-2"
        />
      </section>
      </div>
    </aside>
  );
}
