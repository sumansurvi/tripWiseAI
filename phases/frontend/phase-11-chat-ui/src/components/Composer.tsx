"use client";

import { FormEvent, useState } from "react";

type Props = {
  disabled?: boolean;
  onSend: (text: string) => void;
};

export function Composer({ disabled, onSend }: Props) {
  const [text, setText] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  }

  return (
    <form
      onSubmit={submit}
      className="shrink-0 bg-[color:var(--bg)] px-3 pb-3 pt-1"
    >
      <div className="flex items-center gap-2 rounded-2xl border border-[color:var(--border)] bg-[color:var(--bg)] px-2 py-1.5">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={1}
          placeholder="Ask about a destination, food, transit…"
          className="max-h-32 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-5 outline-none"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(e);
            }
          }}
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          className="shrink-0 rounded-full bg-trail-600 px-4 py-2 text-sm font-medium leading-5 text-white disabled:opacity-40 hover:bg-trail-700"
        >
          Send
        </button>
      </div>
    </form>
  );
}
