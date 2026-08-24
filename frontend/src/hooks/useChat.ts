"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { streamChat } from "@/lib/api";
import type { Citation, GraphTriple, Subgraph } from "@/lib/types";

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  content: string;
  citations: Citation[];
  triples: GraphTriple[];
  subgraph: Subgraph | null;
  queryId: string | null;
  status: "streaming" | "done" | "error";
  error: string | null;
}

export type ChatMessage = UserMessage | AssistantMessage;

let idCounter = 0;
function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${idCounter}`;
}

export interface UseChatResult {
  messages: ChatMessage[];
  isStreaming: boolean;
  /** Subgraph of the most recent assistant answer that produced one. */
  latestSubgraph: Subgraph | null;
  sendMessage: (query: string, options?: { topK?: number; maxHops?: number }) => void;
  stop: () => void;
  sessionId: string;
}

export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [latestSubgraph, setLatestSubgraph] = useState<Subgraph | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string>(nextId("session"));

  const patchAssistant = useCallback(
    (id: string, patch: Partial<AssistantMessage>) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id && m.role === "assistant" ? { ...m, ...patch } : m,
        ),
      );
    },
    [],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
  }, []);

  const sendMessage = useCallback(
    (query: string, options?: { topK?: number; maxHops?: number }) => {
      const trimmed = query.trim();
      if (!trimmed || abortRef.current) return;

      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);

      const userMsg: UserMessage = {
        id: nextId("user"),
        role: "user",
        content: trimmed,
      };
      const assistantId = nextId("assistant");
      const assistantMsg: AssistantMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        citations: [],
        triples: [],
        subgraph: null,
        queryId: null,
        status: "streaming",
        error: null,
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);

      void (async () => {
        let streamedText = "";
        try {
          for await (const event of streamChat(
            {
              query: trimmed,
              session_id: sessionIdRef.current,
              top_k: options?.topK,
              max_hops: options?.maxHops,
            },
            controller.signal,
          )) {
            switch (event.type) {
              case "metadata":
                patchAssistant(assistantId, { queryId: event.query_id });
                break;
              case "citations":
                patchAssistant(assistantId, { citations: event.citations });
                break;
              case "graph":
                patchAssistant(assistantId, { subgraph: event.subgraph, triples: event.triples });
                setLatestSubgraph(event.subgraph);
                break;
              case "token":
                streamedText += event.text;
                patchAssistant(assistantId, { content: streamedText });
                break;
              case "done":
                patchAssistant(assistantId, { status: "done" });
                break;
              case "error":
                patchAssistant(assistantId, { status: "error", error: event.message });
                break;
            }
          }
          // Stream ended without an explicit done/error event.
          patchAssistant(assistantId, {
            status: streamedText ? "done" : "error",
            error: streamedText ? null : "Stream closed before any response.",
          });
        } catch (err) {
          if (controller.signal.aborted) {
            patchAssistant(assistantId, {
              status: streamedText ? "done" : "error",
              error: streamedText ? null : "Cancelled.",
            });
          } else {
            patchAssistant(assistantId, {
              status: "error",
              error: err instanceof Error ? err.message : "Unknown error.",
            });
          }
        } finally {
          if (abortRef.current === controller) abortRef.current = null;
          setIsStreaming(false);
        }
      })();
    },
    [patchAssistant],
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);

  return {
    messages,
    isStreaming,
    latestSubgraph,
    sendMessage,
    stop,
    sessionId: sessionIdRef.current,
  };
}
