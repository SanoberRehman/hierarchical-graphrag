"use client";

import { useEffect, useRef } from "react";

import { ChatInput } from "@/components/ChatInput";
import { ChatMessage } from "@/components/ChatMessage";
import type { ChatMessage as ChatMessageType } from "@/hooks/useChat";

const SUGGESTIONS = [
  "Summarize the key entities in the knowledge base.",
  "How are the main organizations related?",
  "What claims are supported by multiple sources?",
];

interface ChatPanelProps {
  messages: ChatMessageType[];
  isStreaming: boolean;
  onSend: (value: string) => void;
  onStop: () => void;
}

export function ChatPanel({ messages, isStreaming, onSend, onStop }: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Stick to the bottom only while the user is already there — so scrolling up
  // to read earlier messages mid-stream doesn't get yanked back down.
  const stickToBottom = useRef(true);

  function handleScroll() {
    const el = scrollRef.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-6 sm:px-6"
      >
        {isEmpty ? (
          <EmptyState onPick={onSend} />
        ) : (
          messages.map((m) => <ChatMessage key={m.id} message={m} />)
        )}
      </div>

      <div className="border-t border-border bg-surface/60 px-4 py-3 sm:px-6">
        <ChatInput onSend={onSend} onStop={onStop} isStreaming={isStreaming} />
        <p className="mt-1.5 px-1 text-[0.7rem] text-muted">
          Enter to send · Shift+Enter for a new line
        </p>
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (value: string) => void }) {
  return (
    <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center text-center">
      <div className="grid h-12 w-12 place-items-center rounded-2xl bg-accent font-mono text-lg font-bold text-accent-fg shadow-sm">
        G
      </div>
      <h1 className="mt-4 text-lg font-semibold">Ask your knowledge graph</h1>
      <p className="mt-1 text-sm text-muted">
        Answers stream live with citations and an interactive subgraph for every
        query.
      </p>
      <div className="mt-6 w-full space-y-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="w-full rounded-xl border border-border bg-card px-3.5 py-2.5 text-left text-sm text-fg/90 transition-colors hover:border-accent/50 hover:bg-surface"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
