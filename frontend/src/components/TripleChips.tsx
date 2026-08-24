import type { GraphTriple } from "@/lib/types";

interface TripleChipsProps {
  triples: GraphTriple[];
}

/**
 * Renders graph triples as readable (Source) —[TYPE]→ (Target) chips.
 * Triple endpoints are entity *names* (not node keys), so they are shown as-is.
 */
export function TripleChips({ triples }: TripleChipsProps) {
  if (triples.length === 0) return null;

  return (
    <div className="mt-3">
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">
        Relationships
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {triples.map((t, i) => (
          <li
            key={`${t.source}-${t.type}-${t.target}-${i}`}
            title={t.description ?? undefined}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1 text-xs"
          >
            <span className="font-medium">{t.source}</span>
            <span className="font-mono text-[0.65rem] text-accent">
              —[{t.type}]→
            </span>
            <span className="font-medium">{t.target}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
