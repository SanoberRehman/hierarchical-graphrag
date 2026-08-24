"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getJobStatus, ingestDocuments } from "@/lib/api";
import type { JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const POLL_INTERVAL_MS = 1200;

// A small self-contained corpus so a reviewer can ingest with one click and
// immediately try the README's sample queries. It intentionally names every
// entity those queries reference (Acme, Beta, Gamma Ventures, Delta Systems).
const SAMPLE_TITLE = "Company Deals (sample)";
const SAMPLE_TEXT =
  "Acme Corporation acquired Beta Industries in a landmark deal. " +
  "Acme Corporation also partnered with Gamma Ventures. " +
  "Beta Industries invested in Delta Systems, a promising startup. " +
  "Gamma Ventures added Delta Systems to its portfolio.";

const LARGE_DEMO_TITLE = "Tech Ecosystem (large demo)";

// Generate a big, densely-connected corpus: a set of recurring "hub" companies
// (which accrue high connectivity) linked to many one-off startups. Ingested in
// zero-key mode this yields a few hundred entities — enough to fill the graph
// inspector's "Full graph" view like a neural network. Deterministic (no RNG).
function buildLargeDemo(): string {
  const hubs = [
    "Helios Group", "Orion Dynamics", "Vega Capital", "Nimbus Labs",
    "Aster Robotics", "Quasar Media", "Titan Foundry", "Lyra Networks",
    "Cobalt Systems", "Meridian Bank", "Polaris Energy", "Zephyr Mobility",
    "Onyx Semiconductors", "Halcyon Bio", "Vertex Analytics", "Solstice Retail",
    "Kestrel Aerospace", "Ferrum Steel", "Aurora Pharma", "Cirrus Cloud",
  ];
  const verbs = [
    "acquired", "partnered with", "invested in", "merged with", "supplies",
    "competes with", "spun off", "licensed technology to", "acquired a stake in",
    "formed a joint venture with",
  ];
  const lines: string[] = [];
  for (let i = 0; i < 300; i += 1) {
    const h1 = hubs[i % hubs.length];
    const h2 = hubs[(i * 3 + 5) % hubs.length];
    const startup = `Startup${i}`;
    const verb = verbs[i % verbs.length];
    lines.push(`${h1} ${verb} ${startup}, and later ${h2} backed ${startup}.`);
  }
  return lines.join(" ");
}

interface StatMap {
  label: string;
  value: number;
}

function stats(job: JobStatus): StatMap[] {
  return [
    { label: "Processed", value: job.processed_documents },
    { label: "Parents", value: job.parents_indexed },
    { label: "Children", value: job.children_indexed },
    { label: "Entities", value: job.entities_upserted },
    { label: "Relationships", value: job.relationships_upserted },
  ];
}

export function IngestPanel() {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      stopPolling();
      abortRef.current?.abort();
    };
  }, [stopPolling]);

  const poll = useCallback(
    (jobId: string) => {
      const controller = new AbortController();
      abortRef.current = controller;

      const tick = async () => {
        try {
          const status = await getJobStatus(jobId, controller.signal);
          setJob(status);
          if (status.state === "completed" || status.state === "failed") {
            if (status.state === "failed") {
              setError(status.error ?? "Ingestion failed.");
            }
            return;
          }
          pollRef.current = setTimeout(tick, POLL_INTERVAL_MS);
        } catch (err) {
          if (!controller.signal.aborted) {
            setError(err instanceof Error ? err.message : "Failed to poll job status.");
          }
        }
      };

      void tick();
    },
    [],
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || submitting) return;

    stopPolling();
    setError(null);
    setJob(null);
    setSubmitting(true);

    try {
      const res = await ingestDocuments({
        documents: [
          {
            text: trimmed,
            ...(title.trim() ? { title: title.trim() } : {}),
          },
        ],
      });
      setJob({
        job_id: res.job_id,
        state: res.state,
        accepted_documents: res.accepted_documents,
        processed_documents: 0,
        parents_indexed: 0,
        children_indexed: 0,
        entities_upserted: 0,
        relationships_upserted: 0,
      });
      poll(res.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit documents.");
    } finally {
      setSubmitting(false);
    }
  }

  const isRunning =
    job?.state === "queued" || job?.state === "running" || submitting;

  const loadSample = useCallback(() => {
    if (isRunning) return;
    setTitle(SAMPLE_TITLE);
    setText(SAMPLE_TEXT);
    setError(null);
  }, [isRunning]);

  const loadLargeDemo = useCallback(() => {
    if (isRunning) return;
    setTitle(LARGE_DEMO_TITLE);
    setText(buildLargeDemo());
    setError(null);
  }, [isRunning]);

  return (
    <div className="flex h-full flex-col">
      <div className="px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Ingest Documents</h2>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={loadSample}
              disabled={isRunning}
              className="text-xs font-medium text-accent transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Load sample
            </button>
            <button
              type="button"
              onClick={loadLargeDemo}
              disabled={isRunning}
              title="Load a large, densely-connected corpus (~300 relations)"
              className="text-xs font-medium text-accent transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Load large demo
            </button>
          </div>
        </div>
        <p className="mt-0.5 text-xs text-muted">
          Add text to the knowledge base, then watch it get chunked and indexed.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col gap-3 px-4 pb-4">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title (optional)"
          disabled={isRunning}
          className="rounded-xl border border-border bg-card px-3 py-2 text-sm outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/30 disabled:opacity-50"
        />
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste document text to ingest…"
          disabled={isRunning}
          className="min-h-[8rem] flex-1 resize-none rounded-xl border border-border bg-card px-3 py-2 text-sm leading-relaxed outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/30 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!text.trim() || isRunning}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-fg transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isRunning ? "Ingesting…" : "Ingest"}
        </button>
      </form>

      {(job || error) && (
        <div className="animate-fade-in border-t border-border px-4 py-3">
          {job && (
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-xs text-muted">{job.job_id}</span>
              <StateBadge state={job.state} />
            </div>
          )}
          {job && (
            <dl className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {stats(job).map((s) => (
                <div
                  key={s.label}
                  className="rounded-lg border border-border bg-card px-2 py-1.5 text-center"
                >
                  <dt className="text-[0.65rem] uppercase tracking-wide text-muted">
                    {s.label}
                  </dt>
                  <dd className="font-mono text-sm font-semibold tabular-nums">
                    {s.value}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {error && (
            <p className="mt-2 rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-500">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function StateBadge({ state }: { state: JobStatus["state"] }) {
  const styles: Record<JobStatus["state"], string> = {
    queued: "bg-amber-400/15 text-amber-500",
    running: "bg-accent-soft text-accent",
    completed: "bg-emerald-500/15 text-emerald-500",
    failed: "bg-rose-500/15 text-rose-500",
  };
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium capitalize",
        styles[state],
      )}
    >
      {state}
    </span>
  );
}
