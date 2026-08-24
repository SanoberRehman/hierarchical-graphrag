"use client";

import { useEffect, useState } from "react";

import { getHealth } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

type Status = "loading" | "ok" | "down";

export function HealthIndicator() {
  const [status, setStatus] = useState<Status>("loading");
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    async function poll() {
      try {
        const data = await getHealth(controller.signal);
        if (!cancelled) {
          setHealth(data);
          setStatus("ok");
        }
      } catch {
        if (!cancelled) setStatus("down");
      }
    }

    void poll();
    const interval = setInterval(poll, 30_000);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(interval);
    };
  }, []);

  const dotColor =
    status === "ok"
      ? "bg-emerald-500"
      : status === "down"
        ? "bg-rose-500"
        : "bg-amber-400";

  const label =
    status === "loading"
      ? "Checking backend…"
      : status === "down"
        ? "Backend offline"
        : `${health?.llm_provider ?? "?"} · ${health?.embedding_provider ?? "?"}`;

  return (
    <div
      className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted"
      title={
        status === "ok"
          ? `LLM: ${health?.llm_provider} · Embeddings: ${health?.embedding_provider}`
          : label
      }
    >
      <span className="relative flex h-2 w-2">
        {status === "ok" && (
          <span
            className={cn(
              "absolute inline-flex h-full w-full animate-ping rounded-full opacity-60",
              dotColor,
            )}
          />
        )}
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", dotColor)} />
      </span>
      <span className="font-mono tabular-nums">{label}</span>
    </div>
  );
}
