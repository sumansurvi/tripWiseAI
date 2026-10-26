"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/api";
import { MarkdownAnswer } from "./MarkdownAnswer";
import {
  RecommendationBlock,
  TradeOffsBlock,
} from "@research/ResearchPanels";

type Props = {
  messages: ChatMessage[];
  busy: boolean;
};

/** Drop trailing Sources/References and leftover inline citation markers. */
function cleanAssistantContent(content: string): string {
  return content
    .replace(
      /\n{0,2}(?:#{1,3}\s*)?(?:\*\*)?Sources?(?:\*\*)?\s*:?\s*(?:\*\*)?\s*\n[\s\S]*$/i,
      ""
    )
    .replace(
      /\n{0,2}(?:#{1,3}\s*)?(?:\*\*)?References?(?:\*\*)?\s*:?\s*(?:\*\*)?\s*\n[\s\S]*$/i,
      ""
    )
    .replace(/【\d+】/g, "")
    .replace(/(?<=\S)\s*\[\d+\](?!\()/g, "")
    .replace(/ {2,}/g, " ")
    .replace(/ +([,.;:!?])/g, "$1")
    .trimEnd();
}

function answerAsText(m: ChatMessage): string {
  const body = cleanAssistantContent(m.content);
  if (!m.sources || m.sources.length === 0 || m.refused) return body;
  const src = m.sources.map((s) => `- ${s.title}: ${s.source_url}`).join("\n");
  return `${body}\n\nSources:\n${src}`;
}

function CopyIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function ShareIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-7M16 6l-4-4-4 4M12 2v13" />
    </svg>
  );
}

function AnswerActions({ message }: { message: ChatMessage }) {
  const [status, setStatus] = useState<"idle" | "copied" | "shared">("idle");

  const flash = (s: "copied" | "shared") => {
    setStatus(s);
    window.setTimeout(() => setStatus("idle"), 1800);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(answerAsText(message));
      flash("copied");
    } catch {
      /* clipboard unavailable */
    }
  };

  const share = async () => {
    const text = answerAsText(message);
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: "TripWise answer", text });
        flash("shared");
        return;
      } catch (e) {
        if ((e as DOMException)?.name === "AbortError") return;
      }
    }
    // Fallback: no native share sheet → copy to clipboard
    await copy();
  };

  const btn =
    "rounded-md p-1.5 text-[color:var(--muted)] transition hover:bg-trail-100 hover:text-trail-700 dark:hover:bg-white/10 dark:hover:text-trail-200";

  return (
    <div className="mt-1 flex items-center gap-0.5 pl-1">
      <button
        type="button"
        onClick={copy}
        className={btn}
        aria-label={status === "copied" ? "Copied" : "Copy answer"}
        title={status === "copied" ? "Copied" : "Copy"}
      >
        {status === "copied" ? <CheckIcon className="h-4 w-4" /> : <CopyIcon className="h-4 w-4" />}
      </button>
      <button
        type="button"
        onClick={share}
        className={btn}
        aria-label={status === "shared" ? "Shared" : "Share answer"}
        title={status === "shared" ? "Shared" : "Share"}
      >
        {status === "shared" ? <CheckIcon className="h-4 w-4" /> : <ShareIcon className="h-4 w-4" />}
      </button>
    </div>
  );
}

// Mirrors what the RAG pipeline does for each question. Purely cosmetic: the
// API is a single request, so these steps advance on a timer, not real progress.
const WORKING_STEPS = [
  "Retrieving relevant travel sources…",
  "Ranking the best evidence…",
  "Synthesizing a grounded response…",
  "Finalizing your answer…",
];

function WorkingIndicator() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const id = window.setInterval(
      () => setStep((s) => Math.min(s + 1, WORKING_STEPS.length - 1)),
      1800
    );
    return () => window.clearInterval(id);
  }, []);

  return (
    <div
      className="flex items-center gap-2 text-sm text-[color:var(--muted)]"
      role="status"
      aria-live="polite"
    >
      <span className="flex items-center gap-1" aria-hidden>
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-trail-500 [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-trail-500 [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-trail-500" />
      </span>
      {WORKING_STEPS[step]}
    </div>
  );
}


function JumpToLatestIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2.25}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

export function ChatThread({ messages, busy }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastThreadKey = useRef<string | undefined>(undefined);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  const updateJumpVisibility = useCallback(() => {
    const node = scrollRef.current;
    if (!node) return;
    // Only show when this pane itself is scrollable and not at the bottom.
    const canScroll = node.scrollHeight > node.clientHeight + 1;
    const distanceFromBottom =
      node.scrollHeight - node.scrollTop - node.clientHeight;
    setShowJumpToLatest(canScroll && distanceFromBottom > 48);
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const node = scrollRef.current;
    if (!node) return;
    // Scroll the chat pane itself (not a parent page scroll).
    node.scrollTo({ top: node.scrollHeight, behavior });
    window.requestAnimationFrame(updateJumpVisibility);
  }, [updateJumpVisibility]);

  // Keep the newest activity in view (like WhatsApp / ChatGPT): on every new
  // message and while the assistant is working. Switching to another trip jumps
  // straight to the bottom instead of animating through the whole history.
  const threadKey = messages[0]?.id;
  const lastId = messages[messages.length - 1]?.id;
  useEffect(() => {
    const switched = lastThreadKey.current !== threadKey;
    lastThreadKey.current = threadKey;
    const raf = requestAnimationFrame(() => {
      scrollToBottom(switched ? "auto" : "smooth");
    });
    return () => cancelAnimationFrame(raf);
  }, [threadKey, lastId, messages.length, busy, scrollToBottom]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;

    const raf = window.requestAnimationFrame(updateJumpVisibility);
    const ro = new ResizeObserver(() => updateJumpVisibility());
    ro.observe(node);

    return () => {
      window.cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [updateJumpVisibility, threadKey, messages.length, busy]);

  return (
    // min-h-0 is required in a flex column so this pane gets a fixed height and
    // scrolls internally. Without it, content grows the page and the jump button
    // never sees a scroll event on scrollRef.
    <div className="relative min-h-0 flex-1">
      <div
        ref={scrollRef}
        onScroll={updateJumpVisibility}
        className="absolute inset-0 space-y-4 overflow-y-auto px-4 py-4 pb-14 md:px-6"
      >
      {messages.length === 0 && (
        <div className="mx-auto mt-16 max-w-md text-center">
          <h1 className="font-display text-3xl text-trail-800 dark:text-trail-200">
            Where are you headed?
          </h1>
          <p className="mt-2 text-sm text-[color:var(--muted)]">
            Ask about destinations, food, transport, or compare two cities.
            Every answer is grounded in Wikivoyage. No guesswork, no invented facts.
          </p>
        </div>
      )}

      {messages.map((m) => (
        <div
          key={m.id}
          className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
        >
          <div
            className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
              m.role === "user"
                ? "max-w-[min(560px,92%)] bg-[color:var(--user-bubble)] text-white"
                : "max-w-[min(760px,96%)] border border-[color:var(--border)] bg-[color:var(--assistant-bubble)]"
            }`}
          >
            {m.role === "assistant" && m.refused && (
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-skyline-600 dark:text-skyline-400">
                Scoped reply
              </div>
            )}
            <MarkdownAnswer
              content={
                m.role === "assistant"
                  ? cleanAssistantContent(m.content)
                  : m.content
              }
              isUser={m.role === "user"}
            />

            {m.role === "assistant" && !m.refused && (
              <>
                <RecommendationBlock recommendation={m.recommendation} />
                <TradeOffsBlock tradeOffs={m.trade_offs} />
                {m.sources && m.sources.length > 0 && (
                  <div className="mt-3 border-t border-[color:var(--border)] pt-2">
                    <div className="text-xs font-semibold text-trail-700 dark:text-trail-300">
                      Sources
                    </div>
                    <div className="mt-1 space-y-2">
                      {m.sources.map((s) => (
                        <div key={s.source_url} className="text-xs">
                          <div className="font-medium text-trail-800 dark:text-trail-200">
                            {s.title}
                          </div>
                          <a
                            href={s.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="break-all text-skyline-600 underline-offset-2 hover:underline dark:text-skyline-400"
                          >
                            {s.source_url}
                          </a>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

          </div>
          {m.role === "assistant" && <AnswerActions message={m} />}
        </div>
      ))}

      {busy && <WorkingIndicator />}

      <div ref={bottomRef} aria-hidden />
      </div>

      {showJumpToLatest && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 z-30 flex justify-center">
          <button
            type="button"
            onClick={() => scrollToBottom("smooth")}
            aria-label="Jump to latest message"
            title="Jump to latest message"
            className="pointer-events-auto inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--border)] bg-[color:var(--panel)] text-trail-700 shadow-md transition hover:bg-trail-50 hover:text-trail-800 dark:text-trail-200 dark:hover:bg-trail-800/70"
          >
            <JumpToLatestIcon className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
