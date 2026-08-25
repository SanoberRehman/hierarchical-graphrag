"use client";

import { useState } from "react";

import type { Citation } from "@/lib/types";
import { cn } from "@/lib/utils";

interface CitationCardProps {
  citation: Citation;
  index: number;
}

export function CitationCard({ citation, index }: CitationCardProps) {
  const [open, setOpen] = useState(false);
  const title = citation.title?.trim() || citation.doc_id;

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-surface"
      >
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-accent-soft font-mono text-xs font-semibold text-accent">
          {index + 1}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{title}</span>
          <span className="block truncate font-mono text-xs text-muted">
            {citation.parent_id}
          </span>
        </span>
        <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 font-mono text-xs tabular-nums text-muted">
          {citation.score.toFixed(3)}
        </span>
        <svg
          className={cn(
            "h-4 w-4 shrink-0 text-muted transition-transform",
            open && "rotate-180",
          )}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div className="animate-fade-in border-t border-border px-3 py-3 text-sm">
          {citation.matched_child_texts.length > 0 && (
            <div className="mb-3">
              <p className="mb-1 text-[0.65rem] font-medium uppercase tracking-wide text-accent">
                Matched snippet · child chunk (~200 tok)
              </p>
              <div className="space-y-1.5">
                {citation.matched_child_texts.map((snippet, i) => (
                  <p
                    key={`${citation.matched_child_ids[i] ?? i}`}
                    className="rounded-lg border-l-2 border-accent bg-accent-soft/40 px-3 py-2 leading-relaxed text-fg/90"
                  >
                    {snippet}
                  </p>
                ))}
              </div>
            </div>
          )}

          <p className="mb-1 text-[0.65rem] font-medium uppercase tracking-wide text-muted">
            Expanded parent context (~1000 tok · sent to the LLM)
          </p>
          <p className="whitespace-pre-wrap leading-relaxed text-fg/90">{citation.text}</p>

          <dl className="mt-3 space-y-1 text-xs text-muted">
            <div className="flex gap-2">
              <dt className="font-medium">Document</dt>
              <dd className="font-mono">{citation.doc_id}</dd>
            </div>
            {citation.matched_child_ids.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                <dt className="w-full font-medium">Child chunk ids</dt>
                {citation.matched_child_ids.map((id) => (
                  <dd
                    key={id}
                    className="rounded bg-surface px-1.5 py-0.5 font-mono text-[0.65rem]"
                  >
                    {id}
                  </dd>
                ))}
              </div>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}
