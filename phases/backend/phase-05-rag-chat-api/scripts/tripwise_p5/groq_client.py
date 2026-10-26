"""Groq chat client for RAG generation (context-only)."""

from __future__ import annotations

from typing import List, Protocol, Sequence

from tripwise_p3.retrieve import RetrieveHit

SYSTEM_PROMPT = """You are TripWise, a warm, concise travel research companion.
Answer ONLY from the Wikivoyage notes provided in the user message.

Hard rules:
- Never use your own knowledge. Never invent facts, places, prices, shops or URLs.
- If the notes do not actually answer the question (or only cover part of a comparison),
  reply with exactly: NO_ANSWER
  Do not apologise, explain, or add anything else in that case.
- Never mention "the sources", "the provided notes", "context", chunks, or that
  something is "not covered". Simply leave out what you have no notes for.
- Hedge time-sensitive practical details (prices, hours, visas) briefly, e.g. "check locally".
- Never answer personal-data requests. Do not browse the web.

Style (crisp and relevant - answer exactly what was asked, nothing extra):
- Start with a short bold title that restates the ask (e.g. **What to eat in Old Delhi**).
- Use ONE compact Markdown table (or a short bullet list) for the main answer.
  Keep cells short. Never add a Source/URL column.
- Do not add extra sections such as "Quick tips" unless the user asked for tips.
- Comparisons: one table with the aspects where BOTH places have notes, then finish
  with one line: **What I recommend:** <one or two sentences based only on the notes>.
- No citation markers (no 【n】, [n], footnotes) and no Sources/References section - the
  app shows sources separately.
- At most one short friendly closing line. No filler.
"""


def build_user_prompt(message: str, hits: Sequence[RetrieveHit]) -> str:
    blocks: List[str] = []
    for h in hits:
        heading = h.title if not h.section_title else f"{h.title} - {h.section_title}"
        blocks.append(f"### {heading}\n{h.text}")
    notes = "\n\n".join(blocks)
    return (
        f"Question:\n{message.strip()}\n\n"
        f"Wikivoyage notes:\n{notes}\n\n"
        "Answer crisply using only these notes, following the rules. "
        "If they do not answer the question, reply exactly NO_ANSWER."
    )


class ChatClient(Protocol):
    def complete(self, *, system: str, user: str) -> str:
        ...


class GroqChatClient:
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is missing or empty in config/.env.\n"
                "Create a key at https://console.groq.com/keys"
            )
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model

    def complete(self, *, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        content = resp.choices[0].message.content
        return (content or "").strip()


class FakeChatClient:
    """Deterministic chat for unit tests."""

    def __init__(self, reply: str = "Based on the sources, try Old Delhi street food."):
        self.reply = reply
        self.calls: list[dict] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        return self.reply
