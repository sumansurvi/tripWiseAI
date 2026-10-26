"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { TripSidebar } from "./TripSidebar";
import { ChatThread } from "./ChatThread";
import { Composer } from "./Composer";
import { RightRail } from "./RightRail";
import { postChat, type ChatMessage, type TripThread } from "@/lib/api";
import { loadTrips, newConversationId, newId, saveTrips } from "@/lib/storage";

function titleFromMessage(msg: string): string {
  const t = msg.trim();
  return t.length > 42 ? `${t.slice(0, 42)}…` : t || "New trip";
}

export function ChatApp() {
  const [trips, setTrips] = useState<TripThread[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const loaded = loadTrips();
    setTrips(loaded);
    setActiveId(loaded[0]?.id ?? null);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) saveTrips(trips);
  }, [trips, hydrated]);

  const active = useMemo(
    () => trips.find((t) => t.id === activeId) ?? null,
    [trips, activeId]
  );

  const latestAssistant = useMemo(() => {
    if (!active) return null;
    return (
      [...active.messages].reverse().find((m) => m.role === "assistant") ?? null
    );
  }, [active]);

  const ensureTrip = useCallback((): TripThread => {
    if (active) return active;
    const trip: TripThread = {
      id: newId("trip"),
      title: "New trip",
      conversationId: newConversationId(),
      updatedAt: new Date().toISOString(),
      messages: [],
    };
    setTrips((prev) => [trip, ...prev]);
    setActiveId(trip.id);
    return trip;
  }, [active]);

  const onNew = useCallback(() => {
    const trip: TripThread = {
      id: newId("trip"),
      title: "New trip",
      conversationId: newConversationId(),
      updatedAt: new Date().toISOString(),
      messages: [],
    };
    setTrips((prev) => [trip, ...prev]);
    setActiveId(trip.id);
    setError(null);
  }, []);

  const send = useCallback(
    async (text: string, opts?: { newTrip?: boolean }) => {
      setError(null);
      let trip: TripThread;
      if (opts?.newTrip) {
        trip = {
          id: newId("trip"),
          title: titleFromMessage(text),
          conversationId: newConversationId(),
          updatedAt: new Date().toISOString(),
          messages: [],
        };
        setTrips((prev) => [trip, ...prev]);
        setActiveId(trip.id);
      } else {
        trip = ensureTrip();
      }
      const userMsg: ChatMessage = {
        id: newId("msg"),
        role: "user",
        content: text,
        createdAt: new Date().toISOString(),
      };

      setTrips((prev) =>
        prev.map((t) =>
          t.id === trip.id
            ? {
                ...t,
                title:
                  t.messages.length === 0 ? titleFromMessage(text) : t.title,
                updatedAt: new Date().toISOString(),
                messages: [...t.messages, userMsg],
              }
            : t
        )
      );

      setBusy(true);
      try {
        const history = [...trip.messages, userMsg].map((m) => ({
          role: m.role,
          content: m.content,
        }));
        const res = await postChat({
          message: text,
          conversation_id: trip.conversationId,
          history,
        });
        const assistant: ChatMessage = {
          id: newId("msg"),
          role: "assistant",
          content: res.answer,
          createdAt: new Date().toISOString(),
          sources: res.sources,
          refused: res.refused,
          refusal_reason: res.refusal_reason,
          recommendation: res.recommendation ?? null,
          trade_offs: res.trade_offs ?? [],
        };
        setTrips((prev) =>
          prev.map((t) =>
            t.id === trip.id
              ? {
                  ...t,
                  conversationId: res.conversation_id || t.conversationId,
                  updatedAt: new Date().toISOString(),
                  messages: [...t.messages, assistant],
                }
              : t
          )
        );
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Could not reach TripWise API. Is `python main.py` running?"
        );
      } finally {
        setBusy(false);
      }
    },
    [ensureTrip]
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-[color:var(--bg)]">
      <TripSidebar
        trips={trips}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={onNew}
        onSeed={send}
        onSearch={(q) => void send(q, { newTrip: true })}
      />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {error && (
          <div className="shrink-0 border-b border-red-300/50 bg-red-50 px-4 py-2 text-xs text-red-800 dark:bg-red-950/40 dark:text-red-200">
            {error}
          </div>
        )}
        <ChatThread messages={active?.messages ?? []} busy={busy} />
        <Composer disabled={busy} onSend={send} />
      </main>
      <RightRail latestAssistant={latestAssistant} onFollowUp={send} />
    </div>
  );
}
