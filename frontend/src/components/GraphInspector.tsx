"use client";

import cytoscape, {
  type Core,
  type ElementDefinition,
  type EventObject,
} from "cytoscape";
import { useEffect, useMemo, useRef } from "react";

import type { Subgraph } from "@/lib/types";
import { colorMapForTypes } from "@/lib/utils";

interface GraphInspectorProps {
  subgraph: Subgraph | null;
}

// Small graphs otherwise fit() to maxZoom and blow node/label sizes up. Cap the
// zoom the graph settles at so nodes and labels stay at a readable size.
const FIT_PADDING = 30;
const MAX_FIT_ZOOM = 1.1;

// Above this many nodes, node labels are hidden at rest (revealed on hover /
// focus) so a large graph reads as a clean constellation rather than a wall of
// text.
const DENSE_NODE_THRESHOLD = 40;

const FONT_FAMILY = "Inter, system-ui, sans-serif";

// Fixed "deep space" palette — the canvas is always dark (see .graph-space-bg),
// so these don't track the page theme.
const SPACE = {
  label: "rgb(226, 232, 240)", // slate-200
  labelHalo: "rgba(3, 6, 18, 0.92)",
  edge: "rgba(148, 163, 184, 0.32)", // translucent slate — luminous thin lines
  accent: "rgb(129, 140, 248)", // indigo-400
  nodeBorder: "#0a0e1c",
};

function fitWithCap(cy: Core): void {
  cy.fit(undefined, FIT_PADDING);
  if (cy.zoom() > MAX_FIT_ZOOM) {
    cy.zoom(MAX_FIT_ZOOM);
    cy.center();
  }
}

function buildStylesheet(
  dense: boolean,
): (cytoscape.StylesheetStyle | cytoscape.StylesheetCSS)[] {
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        // Size scales with connectivity: hubs read larger, like a neural net.
        width: "mapData(deg, 0, 8, 16, 46)",
        height: "mapData(deg, 0, 8, 16, 46)",
        "border-width": 1.5,
        "border-color": SPACE.nodeBorder,
        "border-opacity": 0.9,
        // A soft halo behind each node in its own color = the "glow".
        "underlay-color": "data(color)",
        "underlay-padding": 7,
        "underlay-opacity": 0.35,
        label: "data(label)",
        color: SPACE.label,
        "font-family": FONT_FAMILY,
        "font-size": "11px",
        "font-weight": 600,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 6,
        "text-max-width": "90px",
        "text-wrap": "wrap",
        "text-outline-color": SPACE.labelHalo,
        "text-outline-width": 3,
        "text-outline-opacity": 1,
        "text-opacity": dense ? 0 : 1,
        "transition-property": "opacity, text-opacity, border-color, width, height",
        "transition-duration": 140,
      },
    },
    {
      selector: "edge",
      style: {
        width: 1.1,
        "line-color": SPACE.edge,
        "target-arrow-color": SPACE.edge,
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.7,
        "curve-style": "bezier",
        label: "data(label)",
        "font-family": FONT_FAMILY,
        "font-size": "9px",
        color: SPACE.label,
        "text-rotation": "autorotate",
        "text-outline-color": SPACE.labelHalo,
        "text-outline-width": 2,
        // Edge type revealed on hover / highlight to keep the resting graph clean.
        "text-opacity": 0,
        "transition-property": "line-color, target-arrow-color, text-opacity, opacity, width",
        "transition-duration": 140,
      },
    },
    // Reveal a node's label (used on hover / focus when labels are hidden).
    { selector: "node.lit", style: { "text-opacity": 1 } },
    {
      selector: "node:active",
      style: { "overlay-opacity": 0.12, "overlay-color": SPACE.accent },
    },
    { selector: ".faded", style: { opacity: 0.07 } },
    {
      selector: "node.highlighted",
      style: { "border-color": SPACE.accent, "border-width": 3, "underlay-opacity": 0.6 },
    },
    {
      selector: "edge.highlighted",
      style: {
        "line-color": SPACE.accent,
        "target-arrow-color": SPACE.accent,
        color: SPACE.label,
        "text-opacity": 1,
        width: 2,
      },
    },
    { selector: "edge.show-label", style: { color: SPACE.label, "text-opacity": 1 } },
  ];
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
 *
 * Each node also carries a `deg` (degree) datum so the stylesheet can size it by
 * connectivity.
 */
function toElements(
  subgraph: Subgraph,
  colorByType: Map<string, string>,
): ElementDefinition[] {
  const nodeKeys = new Set(subgraph.nodes.map((n) => n.key));

  const degree = new Map<string, number>();
  const validEdges = subgraph.edges.filter(
    (e) => nodeKeys.has(e.source) && nodeKeys.has(e.target),
  );
  for (const e of validEdges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }

  const nodes: ElementDefinition[] = subgraph.nodes.map((n) => ({
    data: {
      id: n.key,
      label: n.name,
      type: n.type,
      color: colorByType.get(n.type) ?? "#6366f1",
      description: n.description ?? "",
      deg: degree.get(n.key) ?? 0,
    },
  }));

  const edges: ElementDefinition[] = validEdges.map((e, i) => ({
    data: {
      id: `e${i}-${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      label: e.type.replace(/_/g, " "),
    },
  }));

  return [...nodes, ...edges];
}

export function GraphInspector({ subgraph }: GraphInspectorProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  const colorByType = useMemo(
    () => colorMapForTypes(subgraph?.nodes.map((n) => n.type) ?? []),
    [subgraph],
  );

  const elements = useMemo(
    () => (subgraph ? toElements(subgraph, colorByType) : []),
    [subgraph, colorByType],
  );

  const legend = useMemo(() => Array.from(colorByType.entries()), [colorByType]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || elements.length === 0) return;

    const nodeCount = elements.filter(
      (el) => (el.data as { source?: string }).source === undefined,
    ).length;
    const dense = nodeCount > DENSE_NODE_THRESHOLD;

    const cy = cytoscape({
      container,
      elements,
      style: buildStylesheet(dense),
      layout: {
        name: "cose",
        animate: false,
        padding: FIT_PADDING,
        nodeDimensionsIncludeLabels: !dense,
        randomize: false,
        componentSpacing: dense ? 60 : 120,
        nodeRepulsion: () => (dense ? 6000 : 12000),
        idealEdgeLength: () => (dense ? 60 : 120),
        edgeElasticity: () => 100,
        gravity: 0.35,
      },
      wheelSensitivity: 0.2,
      minZoom: 0.1,
      maxZoom: 2.5,
    });

    cyRef.current = cy;

    cy.ready(() => fitWithCap(cy));

    const clearHighlight = () => cy.elements().removeClass("faded highlighted lit");

    cy.on("tap", "node", (evt: EventObject) => {
      const node = evt.target;
      const neighborhood = node.closedNeighborhood();
      cy.elements().addClass("faded");
      neighborhood.removeClass("faded").addClass("highlighted lit");
    });

    cy.on("tap", (evt: EventObject) => {
      if (evt.target === cy) clearHighlight();
    });

    // Reveal an edge's type on hover.
    cy.on("mouseover", "edge", (evt: EventObject) => evt.target.addClass("show-label"));
    cy.on("mouseout", "edge", (evt: EventObject) => evt.target.removeClass("show-label"));

    // When labels are hidden (dense graph), reveal the hovered node's label.
    if (dense) {
      cy.on("mouseover", "node", (evt: EventObject) => evt.target.addClass("lit"));
      cy.on("mouseout", "node", (evt: EventObject) => {
        if (!evt.target.hasClass("highlighted")) evt.target.removeClass("lit");
      });
    }

    // Keep the canvas sized to its container; re-fit (capped) on resize.
    const observer = new ResizeObserver(() => {
      cy.resize();
      fitWithCap(cy);
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
        <div>
          <h2 className="text-sm font-semibold">Graph Inspector</h2>
          {elements.length > 0 && (
            <p className="mt-0.5 text-xs text-muted">
              {subgraph?.nodes.length} entities · {subgraph?.edges.length} relationships
              <span className="hidden sm:inline"> · click a node to focus</span>
            </p>
          )}
        </div>
        {legend.length > 0 && (
          <button
            type="button"
            onClick={() => {
              const cy = cyRef.current;
              if (!cy) return;
              cy.elements().removeClass("faded highlighted lit");
              fitWithCap(cy);
            }}
            className="shrink-0 rounded-lg border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:bg-surface hover:text-fg"
          >
            Reset view
          </button>
        )}
      </div>

      <div className="relative min-h-0 flex-1">
        {elements.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
            <GraphGlyph />
            <p className="max-w-[15rem] text-sm text-muted">
              Ask a question — the knowledge subgraph that grounds the answer appears here.
            </p>
          </div>
        ) : (
          <div
            ref={containerRef}
            className="graph-space-bg absolute inset-2 overflow-hidden rounded-xl ring-1 ring-white/5"
            style={{ cursor: "grab" }}
          />
        )}
      </div>

      {legend.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-border px-4 py-2.5">
          {legend.map(([type, color]) => (
            <span key={type} className="inline-flex items-center gap-1.5 text-xs text-muted">
              <span
                className="h-2.5 w-2.5 rounded-full ring-2 ring-card"
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

function GraphGlyph() {
  return (
    <svg
      width="44"
      height="44"
      viewBox="0 0 44 44"
      fill="none"
      className="text-border"
      aria-hidden="true"
    >
      <line x1="12" y1="14" x2="30" y2="10" stroke="currentColor" strokeWidth="1.5" />
      <line x1="12" y1="14" x2="18" y2="32" stroke="currentColor" strokeWidth="1.5" />
      <line x1="30" y1="10" x2="34" y2="30" stroke="currentColor" strokeWidth="1.5" />
      <line x1="18" y1="32" x2="34" y2="30" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="12" cy="14" r="4" fill="rgb(var(--accent))" />
      <circle cx="30" cy="10" r="4" fill="currentColor" />
      <circle cx="18" cy="32" r="4" fill="currentColor" />
      <circle cx="34" cy="30" r="4" fill="currentColor" />
    </svg>
  );
}
