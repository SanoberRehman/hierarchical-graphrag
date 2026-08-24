"use client";

import { useState } from "react";

import { ChatPanel } from "@/components/ChatPanel";
import { SidePanel } from "@/components/SidePanel";
import { useChat } from "@/hooks/useChat";
import { cn } from "@/lib/utils";

type MobileView = "chat" | "tools";

export function Workspace() {
  const { messages, isStreaming, latestSubgraph, sendMessage, stop } = useChat();
  const [mobileView, setMobileView] = useState<MobileView>("chat");

  return (
    <div className="mx-auto flex min-h-0 w-full max-w-[1600px] flex-1 flex-col px-0 lg:px-6 lg:py-4">
      {/* Mobile view switcher — hidden on large screens where both panes show. */}
      <div className="flex gap-1 border-b border-border px-3 py-2 lg:hidden">
        <MobileTab active={mobileView === "chat"} onClick={() => setMobileView("chat")}>
          Chat
        </MobileTab>
        <MobileTab active={mobileView === "tools"} onClick={() => setMobileView("tools")}>
          Graph &amp; Ingest
        </MobileTab>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-0 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:gap-4">
        <section
          className={cn(
            "min-h-0 lg:rounded-2xl lg:border lg:border-border lg:bg-surface",
            mobileView !== "chat" && "hidden lg:flex lg:flex-col",
          )}
        >
          <ChatPanel
            messages={messages}
            isStreaming={isStreaming}
            onSend={(v) => sendMessage(v)}
            onStop={stop}
          />
        </section>

        <aside
          className={cn(
            "min-h-0 border-t border-border lg:rounded-2xl lg:border lg:bg-card",
            mobileView !== "tools" && "hidden lg:block",
          )}
        >
          <SidePanel subgraph={latestSubgraph} />
        </aside>
      </div>
    </div>
  );
}

function MobileTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
        active ? "bg-accent text-accent-fg" : "text-muted hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}
