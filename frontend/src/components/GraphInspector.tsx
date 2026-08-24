"use client";

import cytoscape, {
  type Core,
  type ElementDefinition,
  type EventObject,
} from "cytoscape";
import { useEffect, useMemo, useRef } from "react";

import type { Subgraph } from "@/lib/types";
import { colorForType } from "@/lib/utils";

interface GraphInspectorProps {
  subgraph: Subgraph | null;
}

/**
 * Build Cytoscape elements from a subgraph.
 *
 * Guards against two backend realities:
 *  - dangling edges: edges whose source/target node is absent would make
 *    `cy.add` throw, so we drop them;
 *  - node keys contain ":" (e.g. "COMPANY:acme"), which are valid element ids
 *    but invalid selectors — we never build selectors from keys, only use
 *    getElementById / neighborhood traversal.
 */
function toElements(subgraph: Subgraph): ElementDefinition[] {
  const nodeKeys = new Set(subgraph.nodes.map((n) => n.key));

  const nodes: ElementDefinition[] = subgraph.nodes.map((n) => ({
    data: {
      id: n.key,
      label: n.name,
      type: n.type,
      color: colorForType(n.type),
      description: n.description ?? "",
    },
  }));

  const edges: ElementDefinition[] = subgraph.edges
    .filter((e) => nodeKeys.has(e.source) && nodeKeys.has(e.target))
    .map((e, i) => ({
      data: {
        id: `e${i}-${e.source}->${e.target}`,
        source: e.source,
        target: e.target,
        label: e.type,
      },
    }));

  return [...nodes, ...edges];
}

export function GraphInspector({ subgraph }: GraphInspectorProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  const elements = useMemo(
    () => (subgraph ? toElements(subgraph) : []),
    [subgraph],
  );

  const legend = useMemo(() => {
    if (!subgraph) return [];
    const types = new Map<string, string>();
    for (const n of subgraph.nodes) {
      if (!types.has(n.type)) types.set(n.type, colorForType(n.type));
    }
    return Array.from(types.entries());
  }, [subgraph]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || elements.length === 0) return;

    // Cytoscape renders to a canvas and cannot resolve CSS custom properties,
    // so read the active theme's tokens and hand it concrete rgb() colors.
    const rootStyle = getComputedStyle(document.documentElement);
    const token = (name: string, fallback: string): string => {
      const raw = rootStyle.getPropertyValue(name).trim();
      if (!raw) return fallback;
      return `rgb(${raw.split(/\s+/).join(", ")})`;
    };
    const c = {
      fg: token("--fg", "rgb(17, 20, 27)"),
      card: token("--card", "rgb(255, 255, 255)"),
      border: token("--border", "rgb(226, 229, 235)"),
      muted: token("--muted", "rgb(107, 114, 128)"),
      surface: token("--surface", "rgb(248, 249, 251)"),
      accent: token("--accent", "rgb(88, 80, 236)"),
    };

    const cy = cytoscape({
      container,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: c.fg,
            "font-size": "11px",
            "text-valign": "bottom",
            "text-margin-y": 4,
            "text-max-width": "120px",
            "text-wrap": "ellipsis",
            width: 26,
            height: 26,
            "border-width": 2,
            "border-color": c.card,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": c.border,
            "target-arrow-color": c.border,
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.8,
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": "9px",
            color: c.muted,
            "text-rotation": "autorotate",
            "text-background-color": c.surface,
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
          },
        },
        {
          selector: ".faded",
          style: { opacity: 0.15 },
        },
        {
          selector: ".highlighted",
          style: {
            "border-color": c.accent,
            "border-width": 3,
            "line-color": c.accent,
            "target-arrow-color": c.accent,
            color: c.fg,
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        padding: 24,
        nodeRepulsion: () => 8000,
        idealEdgeLength: () => 90,
      },
      wheelSensitivity: 0.2,
      minZoom: 0.2,
      maxZoom: 3,
    });

    cyRef.current = cy;

    const clearHighlight = () => {
      cy.elements().removeClass("faded highlighted");
    };

    cy.on("tap", "node", (evt: EventObject) => {
      const node = evt.target;
      const neighborhood = node.closedNeighborhood();
      cy.elements().addClass("faded");
      neighborhood.removeClass("faded").addClass("highlighted");
    });

    cy.on("tap", (evt: EventObject) => {
      if (evt.target === cy) clearHighlight();
    });

    // Keep the canvas sized to its container on layout changes.
    const observer = new ResizeObserver(() => {
      cy.resize();
      cy.fit(undefined, 24);
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
  }, [elements]);

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="text-sm font-semibold">Graph Inspector</h2>
        {legend.length > 0 && (
          <button
            type="button"
            onClick={() => {
              cyRef.current?.elements().removeClass("faded highlighted");
              cyRef.current?.fit(undefined, 24);
            }}
            className="rounded-lg border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:bg-surface"
          >
            Reset view
          </button>
        )}
      </div>

      <div className="relative min-h-0 flex-1">
        {elements.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted">
            The knowledge subgraph for your latest answer will appear here.
          </div>
        ) : (
          <div ref={containerRef} className="absolute inset-0" />
        )}
      </div>

      {legend.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1.5 border-t border-border px-4 py-2.5">
          {legend.map(([type, color]) => (
            <span key={type} className="inline-flex items-center gap-1.5 text-xs text-muted">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: color }}
              />
              {type}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
