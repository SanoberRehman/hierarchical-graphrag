/** Join truthy class names. A tiny, dependency-free `clsx`. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * A curated, harmonious palette for graph node types. Hand-picked (rather than
 * hashing to a raw hue) so colors read as a considered set and stay legible on
 * both light and dark canvases.
 */
export const TYPE_PALETTE = [
  "#2b8fff", // neon blue
  "#14b8a6", // teal
  "#f59e0b", // amber
  "#ec4899", // pink
  "#10b981", // emerald
  "#8b5cf6", // violet
  "#0ea5e9", // sky
  "#f97316", // orange
  "#e11d48", // rose
  "#84cc16", // lime
] as const;

/**
 * Deterministic color for a graph node/edge type, so the legend is stable
 * across renders. Maps the type name onto the curated palette above.
 *
 * Prefer {@link colorMapForTypes} when rendering a set of types together — it
 * guarantees adjacent types get *distinct* colors, which a per-type hash cannot.
 */
export function colorForType(type: string): string {
  let hash = 0;
  for (let i = 0; i < type.length; i += 1) {
    hash = (hash * 31 + type.charCodeAt(i)) >>> 0;
  }
  return TYPE_PALETTE[hash % TYPE_PALETTE.length];
}

/**
 * Assign every distinct type a distinct palette color (by sorted order), so a
 * legend of N (<= palette size) types never shows two types in the same color.
 */
export function colorMapForTypes(types: Iterable<string>): Map<string, string> {
  const unique = Array.from(new Set(types)).sort();
  return new Map(unique.map((t, i) => [t, TYPE_PALETTE[i % TYPE_PALETTE.length]]));
}
