"use client";

export type SourceItem = {
  title: string;
  source_url: string;
};

export type TradeOff = {
  aspect: string;
  destination_a: string;
  destination_b: string;
  note: string;
};

type Msg = {
  content: string;
  sources?: SourceItem[];
  recommendation?: string | null;
  trade_offs?: TradeOff[];
  refused?: boolean;
};

export function RecommendationBlock({
  recommendation,
}: {
  recommendation?: string | null;
}) {
  if (!recommendation) return null;
  return (
    <div className="mt-3 rounded-lg border border-ember-500/40 bg-ember-500/10 p-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-ember-500">
        What I recommend
      </div>
      <p className="mt-1 text-xs leading-relaxed">{recommendation}</p>
    </div>
  );
}

export function TradeOffsBlock({ tradeOffs }: { tradeOffs?: TradeOff[] }) {
  if (!tradeOffs?.length) return null;
  return (
    <div className="mt-3 space-y-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-skyline-600 dark:text-skyline-400">
        Trade-offs
      </div>
      {tradeOffs.map((t, i) => (
        <div
          key={`${t.aspect}-${i}`}
          className="rounded-lg border border-[color:var(--border)] p-2 text-xs"
        >
          <div className="font-medium">{t.aspect}</div>
          <div className="mt-1 text-[color:var(--muted)]">
            <span className="text-trail-700 dark:text-trail-300">
              {t.destination_a}
            </span>
            {" vs "}
            <span className="text-skyline-600 dark:text-skyline-400">
              {t.destination_b}
            </span>
            : {t.note}
          </div>
        </div>
      ))}
    </div>
  );
}

export function DestinationCards({ sources }: { sources: SourceItem[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {sources.slice(0, 4).map((s) => (
        <a
          key={s.source_url}
          href={s.source_url}
          target="_blank"
          rel="noreferrer"
          className="rounded-xl border border-[color:var(--border)] bg-gradient-to-br from-trail-50 to-skyline-500/5 p-3 text-xs transition hover:border-trail-400 dark:from-trail-900/40 dark:to-skyline-500/10"
        >
          <div className="font-semibold text-trail-800 dark:text-trail-200">
            {s.title}
          </div>
          <div className="mt-1 text-[10px] text-[color:var(--muted)]">
            Open Wikivoyage
          </div>
        </a>
      ))}
    </div>
  );
}

export function SuggestedFollowUps({
  latest,
  onPick,
  className = "",
}: {
  latest: Msg | null;
  onPick: (prompt: string) => void;
  className?: string;
}) {
  // Top source title, e.g. "Delhi/Old Delhi" → "Old Delhi". Generic country/region
  // pages (or no answer yet) fall back to non-place-specific prompts.
  const raw = latest?.sources?.[0]?.title;
  const place = raw ? raw.split("/").pop()?.trim() : undefined;
  const prompts = place
    ? [
        `What should I eat in ${place}?`,
        `How do I get around ${place}?`,
        `Is ${place} good for a first-time visitor?`,
        `Where should I stay in ${place}?`,
      ]
    : [
        "What are the best things to do here?",
        "How do I get around?",
        "What should I know before visiting?",
        "Where should I stay?",
      ];

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {prompts.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onPick(p)}
          className="rounded-md border border-[color:var(--border)] px-2 py-1.5 text-left text-xs hover:border-trail-400 hover:bg-trail-50 dark:hover:bg-white/5"
        >
          {p}
        </button>
      ))}
    </div>
  );
}
