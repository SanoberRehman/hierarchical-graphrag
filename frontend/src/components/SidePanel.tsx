"use client";

import { useState } from "react";

import { GraphInspector } from "@/components/GraphInspector";
import { IngestPanel } from "@/components/IngestPanel";
import type { Subgraph } from "@/lib/types";
import { cn } from "@/lib/utils";

type Tab = "graph" | "ingest";

interface SidePanelProps {
  subgraph: Subgraph | null;
}

export function SidePanel({ subgraph }: SidePanelProps) {
  const [tab, setTab] = useState<Tab>("graph");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex gap-1 border-b border-border px-3 pt-3">
        <TabButton active={tab === "graph"} onClick={() => setTab("graph")}>
          Graph
        </TabButton>
        <TabButton active={tab === "ingest"} onClick={() => setTab("ingest")}>
          Ingest
        </TabButton>
      </div>
      <div className="min-h-0 flex-1">
        {/* Keep the graph mounted so Cytoscape state survives tab switches. */}
        <div className={cn("h-full", tab !== "graph" && "hidden")}>
          <GraphInspector subgraph={subgraph} />
        </div>
        <div className={cn("h-full", tab !== "ingest" && "hidden")}>
          <IngestPanel />
        </div>
      </div>
    </div>
  );
}

function TabButton({
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
      className={cn(
        "rounded-t-lg px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "border-b-2 border-accent text-fg"
          : "border-b-2 border-transparent text-muted hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}
