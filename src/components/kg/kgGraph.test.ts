import { describe, expect, it } from 'vitest';
import { NODE_HEIGHT, NODE_WIDTH, dedupeSubgraph, resolveOverlaps, sortByParentAngle } from './kgGraph';

describe('dedupeSubgraph', () => {
  it('merges same (type, normalised label) and redirects edges without loops', () => {
    const nodes = [
      { id: 'user:u', label: 'You', type: 'User' },
      { id: 'a', label: 'Calm', type: 'State' },
      { id: 'b', label: ' calm! ', type: 'State' },
      { id: 'c', label: 'Calm', type: 'Concept' },
    ];
    const edges = [
      { source: 'user:u', target: 'a', label: 'X' },
      { source: 'user:u', target: 'b', label: 'X' },
      { source: 'a', target: 'b', label: 'Y' },
    ];
    const out = dedupeSubgraph({ nodes, edges });
    expect(out.nodes.map((n) => n.id)).toEqual(['user:u', 'a', 'c']);
    expect((out.nodes[1] as { merged_count?: number }).merged_count).toBe(2);
    expect(out.edges).toEqual([{ source: 'user:u', target: 'a', label: 'X' }]);
  });
});

describe('resolveOverlaps', () => {
  it('leaves no overlapping node boxes', () => {
    const positions = new Map(
      Array.from({ length: 12 }, (_, i) => [`n${i}`, { x: (i % 3) * 40, y: Math.floor(i / 3) * 20 }] as const),
    );
    resolveOverlaps(positions, new Set(['n0']));
    expect(positions.get('n0')).toEqual({ x: 0, y: 0 });
    const list = [...positions.values()];
    for (let i = 0; i < list.length; i += 1) {
      for (let j = i + 1; j < list.length; j += 1) {
        const apart =
          Math.abs(list[i].x - list[j].x) >= NODE_WIDTH || Math.abs(list[i].y - list[j].y) >= NODE_HEIGHT;
        expect(apart).toBe(true);
      }
    }
  });
});

describe('sortByParentAngle', () => {
  it('orders children by parent angle', () => {
    const angles = new Map([['p1', 3], ['p2', -1]]);
    const adj = new Map([['c1', ['p1']], ['c2', ['p2']]]);
    expect(sortByParentAngle([{ id: 'c1' }, { id: 'c2' }], adj, angles).map((n) => n.id)).toEqual(['c2', 'c1']);
  });
});
