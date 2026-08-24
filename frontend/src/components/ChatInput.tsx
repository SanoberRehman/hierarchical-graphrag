"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";

const MAX_TEXTAREA_PX = 160; // matches max-h-40

interface ChatInputProps {
  onSend: (value: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, onStop, isStreaming, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-grow with content, capped at MAX_TEXTAREA_PX (then it scrolls).
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_PX)}px`;
  }, [value]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    submit();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2 rounded-2xl border border-border bg-card p-2 shadow-sm focus-within:border-accent/60 focus-within:ring-1 focus-within:ring-accent/30"
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        aria-label="Ask about your knowledge base"
        placeholder="Ask about your knowledge base…"
        disabled={disabled}
        className="max-h-40 min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-relaxed outline-none placeholder:text-muted disabled:opacity-50"
      />
      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          className="shrink-0 rounded-xl border border-border px-4 py-2 text-sm font-medium text-fg transition-colors hover:bg-surface"
        >
          Stop
        </button>
      ) : (
        <button
          type="submit"
          disabled={!value.trim() || disabled}
          className={cn(
            "shrink-0 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-fg transition-opacity",
            "disabled:cursor-not-allowed disabled:opacity-40",
          )}
        >
          Send
        </button>
      )}
    </form>
  );
}
