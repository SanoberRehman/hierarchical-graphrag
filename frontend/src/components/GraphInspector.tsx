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

const FONT_FAMILY = "Inter, system-ui, sans-serif";

function fitWithCap(cy: Core): void {
  cy.fit(undefined, FIT_PADDING);
  if (cy.zoom() > MAX_FIT_ZOOM) {
    cy.zoom(MAX_FIT_ZOOM);
    cy.center();
  }
}

interface ThemeColors {
  fg: string;
  card: string;
  border: string;
  muted: string;
  surface: string;
  accent: string;
}

/**
 * Cytoscape renders to a canvas and can't resolve CSS custom properties, so read
 * the active theme's tokens off :root and hand it concrete rgb() colors. Called
 * again on theme change so the canvas recolors live.
 */
function readThemeColors(): ThemeColors {
  const rootStyle = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string): string => {
    const raw = rootStyle.getPropertyValue(name).trim();
    return raw ? `rgb(${raw.split(/\s+/).join(", ")})` : fallback;
  };
  return {
    fg: token("--fg", "rgb(17, 20, 27)"),
    card: token("--card", "rgb(255, 255, 255)"),
    border: token("--border", "rgb(226, 229, 235)"),
    muted: token("--muted", "rgb(107, 114, 128)"),
    surface: token("--surface", "rgb(248, 249, 251)"),
    accent: token("--accent", "rgb(88, 80, 236)"),
  };
}

function buildStylesheet(
  c: ThemeColors,
): (cytoscape.StylesheetStyle | cytoscape.StylesheetCSS)[] {
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        width: 30,
        height: 30,
        "border-width": 3,
        "border-color": c.card,
        "border-opacity": 1,
        label: "data(label)",
        color: c.fg,
        "font-family": FONT_FAMILY,
        "font-size": "12px",
        "font-weight": 600,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 7,
        "text-max-width": "96px",
        "text-wrap": "wrap",
        // A halo in the canvas color keeps labels legible over edges/nodes.
        "text-outline-color": c.surface,
        "text-outline-width": 3,
        "text-outline-opacity": 1,
        "transition-property": "border-color, border-width, opacity",
        "transition-duration": 120,
      },
    },
    {
      selector: "edge",
      style: {
        width: 1.5,
        "line-color": c.border,
        "target-arrow-color": c.border,
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.9,
        "curve-style": "bezier",
        label: "data(label)",
        "font-family": FONT_FAMILY,
        "font-size": "10px",
        color: c.muted,
        "text-rotation": "autorotate",
        "text-outline-color": c.surface,
        "text-outline-width": 3,
        // Edge type is revealed on hover / highlight to keep the resting graph
        // uncluttered (the full triples are also listed in the chat).
        "text-opacity": 0,
        "transition-property": "line-color, target-arrow-color, text-opacity, opacity",
        "transition-duration": 120,
      },
    },
    {
      selector: "node:active",
      style: { "overlay-opacity": 0.1, "overlay-color": c.accent },
    },
    {
      selector: ".faded",
      style: { opacity: 0.12 },
    },
    {
      selector: "node.highlighted",
      style: { "border-color": c.accent, "border-width": 4 },
    },
    {
      selector: "edge.highlighted",
      style: {
        "line-color": c.accent,
        "target-arrow-color": c.accent,
        color: c.fg,
        "text-opacity": 1,
        width: 2,
      },
    },
    {
      selector: "edge.show-label",
      style: { color: c.fg, "text-opacity": 1 },
    },
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
 */
function toElements(
  subgraph: Subgraph,
  colorByType: Map<string, string>,
): ElementDefinition[] {
  const nodeKeys = new Set(subgraph.nodes.map((n) => n.key));

  const nodes: ElementDefinition[] = subgraph.nodes.map((n) => ({
    data: {
      id: n.key,
      label: n.name,
      type: n.type,
      color: colorByType.get(n.type) ?? "#6366f1",
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

    const cy = cytoscape({
      container,
      elements,
      style: buildStylesheet(readThemeColors()),
      layout: {
        name: "cose",
        animate: false,
        padding: FIT_PADDING,
        nodeDimensionsIncludeLabels: true,
        randomize: false,
        componentSpacing: 120,
        nodeRepulsion: () => 12000,
        idealEdgeLength: () => 120,
        edgeElasticity: () => 100,
        gravity: 0.3,
      },
      wheelSensitivity: 0.2,
      minZoom: 0.25,
      maxZoom: 2,
    });

    cyRef.current = cy;

    cy.ready(() => fitWithCap(cy));

    const clearHighlight = () => cy.elements().removeClass("faded highlighted");

    cy.on("tap", "node", (evt: EventObject) => {
      const node = evt.target;
      const neighborhood = node.closedNeighborhood();
      cy.elements().addClass("faded");
      neighborhood.removeClass("faded").addClass("highlighted");
    });

    cy.on("tap", (evt: EventObject) => {
      if (evt.target === cy) clearHighlight();
    });

    // Reveal a single edge's type label on hover.
    cy.on("mouseover", "edge", (evt: EventObject) => evt.target.addClass("show-label"));
    cy.on("mouseout", "edge", (evt: EventObject) => evt.target.removeClass("show-label"));

    // Keep the canvas sized to its container; re-fit (capped) on resize.
    const observer = new ResizeObserver(() => {
      cy.resize();
      fitWithCap(cy);
    });
    observer.observe(container);

    // Recolor the canvas live when the theme changes — either the OS scheme
    // (prefers-color-scheme) or an explicit data-theme toggle on :root.
    const applyTheme = () => cy.style(buildStylesheet(readThemeColors()));
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", applyTheme);
    const themeObserver = new MutationObserver(applyTheme);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    });

    return () => {
      observer.disconnect();
      media.removeEventListener("change", applyTheme);
      themeObserver.disconnect();
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
              cy.elements().removeClass("faded highlighted");
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
            className="absolute inset-2 rounded-xl bg-surface"
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
