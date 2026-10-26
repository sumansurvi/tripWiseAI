export type EvidenceItem = {
  chunk_id: string;
  text: string;
  score: number;
};

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

export type ChatApiResponse = {
  request_id: string;
  answer: string;
  evidence: EvidenceItem[];
  sources: SourceItem[];
  refused: boolean;
  refusal_reason: string | null;
  conversation_id?: string | null;
  recommendation?: string | null;
  trade_offs?: TradeOff[];
  intent?: string | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  evidence?: EvidenceItem[];
  sources?: SourceItem[];
  refused?: boolean;
  refusal_reason?: string | null;
  recommendation?: string | null;
  trade_offs?: TradeOff[];
};

export type TripThread = {
  id: string;
  title: string;
  conversationId: string;
  updatedAt: string;
  messages: ChatMessage[];
};

/** Empty string = same-origin (Vercel routes /chat → api/chat.py). */
function resolveApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_TRIPWISE_API_URL;
  if (typeof fromEnv === "string") {
    return fromEnv.replace(/\/$/, "");
  }
  // Production builds (Vercel): same origin. Local `next dev`: FastAPI on :8000.
  if (process.env.NODE_ENV === "production") {
    return "";
  }
  return "http://127.0.0.1:8000";
}

export const API_BASE = resolveApiBase();

export const SEED_PROMPTS = [
  "What to eat in Old Delhi?",
  "What currency is used in India?",
  "Delhi vs Mumbai for a first-time visitor",
  "How do I get around Jaipur?",
];

export async function postChat(body: {
  message: string;
  conversation_id?: string;
  history?: { role: string; content: string }[];
}): Promise<ChatApiResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `API error ${res.status}`);
  }
  return res.json();
}
