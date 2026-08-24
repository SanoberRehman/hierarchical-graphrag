"use client";

import { useState } from "react";

import type { GraphTriple } from "@/lib/types";
import { cn } from "@/lib/utils";

interface TripleChipsProps {
  triples: GraphTriple[];
}

// Cap how many chips render at once — a dense query can return 1000+ triples,
// which would both flood the panel and lag the DOM.
const MAX_SHOWN = 60;

/**
 * Graph triples as readable (Source) —[TYPE]→ (Target) chips. Collapsed by
 * default to a "<n> relationships" toggle so a long list doesn't bury the answer.
 */
export function TripleChips({ triples }: TripleChipsProps) {
  const [open, setOpen] = useState(false);
  if (triples.length === 0) return null;

  const shown = triples.slice(0, MAX_SHOWN);
  const hidden = triples.length - shown.length;

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted transition-colors hover:text-fg"
      >
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          aria-hidden="true"
          className={cn("transition-transform", open && "rotate-90")}
        >
          <path d="M3 1 L7 5 L3 9" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
        {triples.length} relationship{triples.length > 1 ? "s" : ""}
      </button>

      {open && (
        <ul className="mt-1.5 flex flex-wrap gap-1.5">
          {shown.map((t, i) => (
            <li
              key={`${t.source}-${t.type}-${t.target}-${i}`}
              title={t.description ?? undefined}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1 text-xs"
            >
              <span className="font-medium">{t.source}</span>
              <span className="font-mono text-[0.65rem] text-accent">—[{t.type}]→</span>
              <span className="font-medium">{t.target}</span>
            </li>
          ))}
          {hidden > 0 && (
            <li className="inline-flex items-center rounded-full px-2.5 py-1 text-xs text-muted">
              +{hidden} more
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
