/** Join truthy class names. A tiny, dependency-free `clsx`. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Deterministic color for a graph node/edge type, so the legend is stable.
 * Uses comma-separated hsl() — Cytoscape's canvas color parser does not accept
 * the space-separated CSS Color 4 syntax, and browsers accept both.
 */
export function colorForType(type: string): string {
  let hash = 0;
  for (let i = 0; i < type.length; i += 1) {
    hash = (hash * 31 + type.charCodeAt(i)) % 360;
  }
  return `hsl(${hash}, 62%, 52%)`;
}
