import { CitationCard } from "@/components/CitationCard";
import { TripleChips } from "@/components/TripleChips";
import type { ChatMessage as ChatMessageType } from "@/hooks/useChat";
import { cn } from "@/lib/utils";

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] animate-fade-in rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm leading-relaxed text-accent-fg">
          {message.content}
        </div>
      </div>
    );
  }

  const { content, status, error, citations, triples } = message;
  const showCursor = status === "streaming";
  const isThinking = status === "streaming" && content.length === 0;

  return (
    <div className="animate-fade-in space-y-3">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-border bg-card px-4 py-3">
        {isThinking ? (
          <ThinkingDots />
        ) : (
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg/95">
            {content}
            {showCursor && (
              <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-blink bg-accent align-middle" />
            )}
          </p>
        )}

        {status === "error" && error && (
          <p className="mt-2 rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-500">
            {error}
          </p>
        )}
      </div>

      {citations.length > 0 && (
        <div className="max-w-[95%] space-y-1.5">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            Citations
          </p>
          {citations.map((c, i) => (
            <CitationCard key={`${c.parent_id}-${i}`} citation={c} index={i} />
          ))}
        </div>
      )}

      <div className={cn(triples.length > 0 && "max-w-[95%]")}>
        <TripleChips triples={triples} />
      </div>
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="flex items-center gap-1 py-0.5" aria-label="Retrieving">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-blink rounded-full bg-muted"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}
