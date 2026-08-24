import { HealthIndicator } from "@/components/HealthIndicator";

export function Header() {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-2.5">
          {/* Small pixel/mono accent mark in the wordmark — subtle, not busy. */}
          <span
            aria-hidden
            className="grid h-7 w-7 place-items-center rounded-md bg-accent font-mono text-sm font-bold text-accent-fg shadow-sm"
          >
            G
          </span>
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono text-sm font-semibold tracking-tight">
              graph<span className="text-accent">RAG</span>
            </span>
            <span className="hidden text-xs text-muted sm:inline">console</span>
          </div>
        </div>
        <HealthIndicator />
      </div>
    </header>
  );
}
