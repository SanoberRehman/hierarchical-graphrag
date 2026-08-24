/**
 * Typed client for the GraphRAG backend.
 *
 * Base URL comes from NEXT_PUBLIC_API_BASE_URL (inlined at build time),
 * defaulting to http://localhost:8000.
 */

import { readSSE } from "@/lib/sse";
import type {
  ChatRequest,
  ChatStreamEvent,
  HealthResponse,
  IngestRequest,
  IngestResponse,
  JobStatus,
  SubgraphResponse,
} from "@/lib/types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(
      `${res.status} ${res.statusText}${body ? ` — ${body}` : ""}`.trim(),
    );
  }
  return (await res.json()) as T;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch(apiUrl("/api/v1/health"), { signal });
  return asJson<HealthResponse>(res);
}

export async function ingestDocuments(
  body: IngestRequest,
  signal?: AbortSignal,
): Promise<IngestResponse> {
  const res = await fetch(apiUrl("/api/v1/ingest"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  return asJson<IngestResponse>(res);
}

export async function getJobStatus(
  jobId: string,
  signal?: AbortSignal,
): Promise<JobStatus> {
  const res = await fetch(
    apiUrl(`/api/v1/ingest/jobs/${encodeURIComponent(jobId)}`),
    { signal },
  );
  return asJson<JobStatus>(res);
}

/**
 * Fetch a subgraph: the one used for a specific chat answer (`queryId`), or a
 * whole-knowledge-graph sample (default) bounded by `limit`.
 */
export async function getSubgraph(
  opts: { queryId?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<SubgraphResponse> {
  const qs = new URLSearchParams();
  if (opts.queryId) qs.set("query_id", opts.queryId);
  if (opts.limit) qs.set("limit", String(opts.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const res = await fetch(apiUrl(`/api/v1/graph/subgraph${suffix}`), { signal });
  return asJson<SubgraphResponse>(res);
}

/**
 * Open the chat SSE stream and yield each decoded event.
 * The stream is a POST, so we cannot use EventSource — see lib/sse.ts.
 */
export async function* streamChat(
  body: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const res = await fetch(apiUrl("/api/v1/chat"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      `Chat request failed: ${res.status} ${res.statusText}${
        detail ? ` — ${detail}` : ""
      }`,
    );
  }

  yield* readSSE<ChatStreamEvent>(res, signal);
}
