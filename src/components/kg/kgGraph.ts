// Pure helpers for the personal wisdom map: duplicate collapse and overlap-free layout.

export interface GNode {
  id: string;
  label: string;
  type: string;
  merged_count?: number;
}
export interface GEdge {
  source: string;
  target: string;
  label?: string | null;
}

export const NODE_WIDTH = 230;
export const NODE_HEIGHT = 110;
const GAP = 16;

export const normalizeLabel = (label: string): string =>
  label
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[\p{P}\p{S}]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();

/** Safety net for the backend dedupe: merge nodes sharing (type, normalised label). */
export function dedupeSubgraph<N extends GNode, E extends GEdge>(data: {
  nodes: N[];
  edges: E[];
}): { nodes: N[]; edges: E[] } {
  const canon = new Map<string, N>();
  const remap = new Map<string, string>();
  const nodes: N[] = [];
  for (const node of data.nodes) {
    const norm = normalizeLabel(node.label ?? '');
    const key = `${node.type.toLowerCase()}|${norm}`;
    const first = node.type.toLowerCase() === 'user' || !norm ? undefined : canon.get(key);
    if (first) {
      first.merged_count = (first.merged_count ?? 1) + (node.merged_count ?? 1);
      remap.set(node.id, first.id);
      continue;
    }
    const copy = { ...node, merged_count: node.merged_count ?? 1 };
    if (norm && node.type.toLowerCase() !== 'user') canon.set(key, copy);
    remap.set(node.id, node.id);
    nodes.push(copy);
  }
  const seen = new Set<string>();
  const edges: E[] = [];
  for (const edge of data.edges) {
    const source = remap.get(edge.source);
    const target = remap.get(edge.target);
    if (!source || !target || source === target) continue;
    const k = `${source}|${target}|${edge.label ?? ''}`;
    if (seen.has(k)) continue;
    seen.add(k);
    edges.push({ ...edge, source, target });
  }
  return { nodes, edges };
}

type Pos = { x: number; y: number };

/** Push overlapping node boxes apart (minimum-translation axis); `fixed` ids stay put. */
export function resolveOverlaps(positions: Map<string, Pos>, fixed: Set<string>): void {
  const ids = [...positions.keys()];
  const w = NODE_WIDTH + GAP;
  const h = NODE_HEIGHT + GAP;
  for (let pass = 0; pass < 600; pass += 1) {
    let moved = false;
    for (let i = 0; i < ids.length; i += 1) {
      for (let j = i + 1; j < ids.length; j += 1) {
        const a = positions.get(ids[i])!;
        const b = positions.get(ids[j])!;
        const ox = w - Math.abs(a.x - b.x);
        const oy = h - Math.abs(a.y - b.y);
        if (ox <= 0 || oy <= 0) continue;
        moved = true;
        const aFixed = fixed.has(ids[i]);
        const bFixed = fixed.has(ids[j]);
        const shareA = aFixed ? 0 : bFixed ? 1 : 0.5;
        const shareB = bFixed ? 0 : aFixed ? 1 : 0.5;
        if (ox < oy) {
          const dir = a.x <= b.x ? -1 : 1;
          a.x += dir * ox * shareA + (ox * shareA ? 0.5 * dir : 0);
          b.x -= dir * ox * shareB + (ox * shareB ? 0.5 * dir : 0);
        } else {
          const dir = a.y <= b.y ? -1 : 1;
          a.y += dir * oy * shareA + (oy * shareA ? 0.5 * dir : 0);
          b.y -= dir * oy * shareB + (oy * shareB ? 0.5 * dir : 0);
        }
      }
    }
    if (!moved) return;
  }
}

/** Order ring members by the mean angle of their already-placed neighbours (children sit by parents). */
export function sortByParentAngle<T extends { id: string }>(
  items: T[],
  neighbours: Map<string, string[]>,
  angleOf: Map<string, number>,
): T[] {
  const key = (item: T): number => {
    const angles = (neighbours.get(item.id) ?? [])
      .map((id) => angleOf.get(id))
      .filter((a): a is number => a !== undefined);
    if (!angles.length) return Number.POSITIVE_INFINITY;
    const sx = angles.reduce((s, a) => s + Math.cos(a), 0);
    const sy = angles.reduce((s, a) => s + Math.sin(a), 0);
    return Math.atan2(sy, sx);
  };
  return items
    .map((item, index) => ({ item, index, k: key(item) }))
    .sort((p, q) => (p.k === q.k ? p.index - q.index : p.k - q.k))
    .map((p) => p.item);
}
