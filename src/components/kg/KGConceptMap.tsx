import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Search, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';

import { getAIConfig } from '@/lib/chat/config';
import { getAccessToken } from '@/lib/chat/auth';

interface KGNode { id: string; label: string; type: string; teacher?: string | null; }
interface KGEdge { source: string; target: string; label?: string | null; }
interface Subgraph { nodes: KGNode[]; edges: KGEdge[]; }

interface SimNode extends KGNode { x: number; y: number; vx: number; vy: number; degree: number; fx?: number | null; fy?: number | null; }

const WIDTH = 900;
const HEIGHT = 620;

/** Deterministic hue from teacher — stable colors across renders. */
const teacherHue = (t: string | null | undefined): number => {
  if (!t) return 210;
  let h = 0;
  for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) % 360;
  return h;
};

/** Obsidian-style force simulation: repulsion + spring + centering. Pure velocity Verlet, no deps. */
function runForceSim(nodes: SimNode[], edges: KGEdge[], iters = 260) {
  const w = WIDTH, h = HEIGHT, cx = w / 2, cy = h / 2;
  const linkDist = 90;
  const linkStrength = 0.04;
  const repulsion = 1400;
  const centerPull = 0.008;
  const damping = 0.86;
  const byId = new Map(nodes.map((n) => [n.id, n]));

  for (let step = 0; step < iters; step++) {
    // repulsion (naive O(n^2) — fine for <200 nodes)
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = a.x - b.x, dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) { d2 = 1; dx = Math.random(); dy = Math.random(); }
        const f = repulsion / d2;
        const d = Math.sqrt(d2);
        const fx = (dx / d) * f, fy = (dy / d) * f;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      }
    }
    // link spring
    for (const e of edges) {
      const s = byId.get(e.source), t = byId.get(e.target);
      if (!s || !t) continue;
      const dx = t.x - s.x, dy = t.y - s.y;
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const diff = (d - linkDist) * linkStrength;
      const fx = (dx / d) * diff, fy = (dy / d) * diff;
      s.vx += fx; s.vy += fy;
      t.vx -= fx; t.vy -= fy;
    }
    // centering + integrate
    for (const n of nodes) {
      n.vx += (cx - n.x) * centerPull;
      n.vy += (cy - n.y) * centerPull;
      n.vx *= damping; n.vy *= damping;
      if (n.fx == null) n.x += n.vx;
      if (n.fy == null) n.y += n.vy;
    }
  }
}

const DEMO: Subgraph = {
  nodes: [
    { id: 'bs', label: 'Beautiful State', type: 'concept', teacher: 'Sri Preethaji' },
    { id: 'ss', label: 'Suffering State', type: 'concept', teacher: 'Sri Preethaji' },
    { id: 'sm', label: 'Serene Mind', type: 'practice', teacher: 'Sri Krishnaji' },
    { id: 'ui', label: 'Universal Intelligence', type: 'concept', teacher: 'Sri Preethaji' },
    { id: 'ct', label: 'Compassion', type: 'concept', teacher: 'Sri Krishnaji' },
    { id: 'in', label: 'Inner Truth', type: 'concept', teacher: 'Sri Preethaji' },
    { id: 'aw', label: 'Awakening', type: 'concept', teacher: 'Sri Krishnaji' },
    { id: 'st', label: 'Stillness', type: 'practice', teacher: 'Sri Preethaji' },
  ],
  edges: [
    { source: 'bs', target: 'sm', label: 'cultivated by' },
    { source: 'ss', target: 'bs', label: 'transformed into' },
    { source: 'sm', target: 'st', label: 'includes' },
    { source: 'bs', target: 'ui', label: 'connects to' },
    { source: 'ui', target: 'aw', label: 'leads to' },
    { source: 'ct', target: 'bs', label: 'arises in' },
    { source: 'in', target: 'aw', label: 'reveals' },
    { source: 'st', target: 'in', label: 'uncovers' },
  ],
};

export const KGConceptMap = ({ initialQuery = '' }: { initialQuery?: string }) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState(initialQuery);
  const [submitted, setSubmitted] = useState(initialQuery);
  const [data, setData] = useState<Subgraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const dragViewRef = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);
  const dragNodeRef = useRef<{ id: string } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Force-simulated positions
  const simNodes = useMemo<SimNode[]>(() => {
    if (!data) return [];
    const degree = new Map<string, number>();
    for (const e of data.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }
    const nodes: SimNode[] = data.nodes.map((n, i) => {
      const a = (i / Math.max(data.nodes.length, 1)) * Math.PI * 2;
      return {
        ...n, x: WIDTH / 2 + Math.cos(a) * 180, y: HEIGHT / 2 + Math.sin(a) * 180,
        vx: 0, vy: 0, degree: degree.get(n.id) ?? 0,
      };
    });
    runForceSim(nodes, data.edges);
    return nodes;
  }, [data]);

  const [tick, setTick] = useState(0); // to re-render when dragging a node
  const nodePos = useRef(new Map<string, { x: number; y: number }>());
  useEffect(() => {
    nodePos.current = new Map(simNodes.map((n) => [n.id, { x: n.x, y: n.y }]));
    setTick((t) => t + 1);
  }, [simNodes]);

  const fetchSubgraph = useCallback(async (q: string) => {
    setLoading(true); setError(null);
    try {
      const { endpoint } = getAIConfig();
      const baseUrl = (endpoint ?? '').replace(/\/api\/chat\/?$/, '');
      const url = `${baseUrl}/api/kg/subgraph?query=${encodeURIComponent(q.trim() || 'beautiful state')}&limit=24`;
      const token = await getAccessToken();
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as Subgraph;
      if (!json.nodes || json.nodes.length === 0) {
        setData(DEMO);
        setError('No matching concepts — showing the core teaching map.');
      } else {
        setData(json);
      }
      setPan({ x: 0, y: 0 }); setZoom(1);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load graph';
      setError(`${msg} — showing offline teaching map.`);
      setData(DEMO);
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-load on mount so the page never looks empty.
  useEffect(() => {
    fetchSubgraph(submitted || 'beautiful state');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (submitted) fetchSubgraph(submitted);
  }, [submitted, fetchSubgraph]);

  const onWheel = useCallback((e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    setZoom((z) => Math.min(3, Math.max(0.3, z + -e.deltaY * 0.0015)));
  }, []);

  const svgPoint = (e: React.PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    const scaleX = WIDTH / rect.width;
    const scaleY = HEIGHT / rect.height;
    return {
      x: ((e.clientX - rect.left) * scaleX - pan.x) / zoom,
      y: ((e.clientY - rect.top) * scaleY - pan.y) / zoom,
    };
  };

  const onPointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    const targetId = (e.target as SVGElement).getAttribute('data-node-id');
    if (targetId) {
      dragNodeRef.current = { id: targetId };
    } else {
      dragViewRef.current = { sx: e.clientX, sy: e.clientY, px: pan.x, py: pan.y };
    }
  }, [pan]);

  const onPointerMove = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (dragNodeRef.current) {
      const p = svgPoint(e);
      const pos = nodePos.current.get(dragNodeRef.current.id);
      if (pos) { pos.x = p.x; pos.y = p.y; setTick((t) => t + 1); }
      return;
    }
    if (dragViewRef.current) {
      setPan({
        x: dragViewRef.current.px + (e.clientX - dragViewRef.current.sx),
        y: dragViewRef.current.py + (e.clientY - dragViewRef.current.sy),
      });
    }
  }, [pan, zoom]);

  const onPointerUp = useCallback(() => {
    dragViewRef.current = null;
    dragNodeRef.current = null;
  }, []);

  const submit = (e: React.FormEvent) => { e.preventDefault(); setSubmitted(query); };

  const nodeRadius = (deg: number) => 8 + Math.min(deg * 2.5, 18);

  return (
    <div className="flex flex-col gap-4 w-full max-w-5xl mx-auto p-4">
      <form onSubmit={submit} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('kg.searchPlaceholderDetailed', 'Search a concept, teaching, or practice…')}
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ojas/40"
            aria-label="Knowledge graph query"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-ojas text-white text-sm font-medium disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          {t('kg.explore', 'Explore')}
        </button>
      </form>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <button onClick={() => setZoom((z) => Math.min(3, z + 0.2))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom in"><ZoomIn className="w-3.5 h-3.5" /></button>
        <button onClick={() => setZoom((z) => Math.max(0.3, z - 0.2))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom out"><ZoomOut className="w-3.5 h-3.5" /></button>
        <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="p-1.5 rounded border border-border hover:bg-muted" title="Reset view"><RotateCcw className="w-3.5 h-3.5" /></button>
        <span className="ml-1">Drag to pan · scroll to zoom · drag nodes to reposition</span>
      </div>

      {error && <div className="text-xs text-muted-foreground/80 italic">{error}</div>}

      <div className="rounded-xl border border-border overflow-hidden" style={{ background: 'radial-gradient(ellipse at center, hsl(220 30% 8%) 0%, hsl(220 40% 4%) 100%)' }}>
        <svg
          ref={svgRef}
          width="100%"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="block touch-none select-none"
          style={{ height: HEIGHT, cursor: dragViewRef.current ? 'grabbing' : dragNodeRef.current ? 'grabbing' : 'grab' }}
          onWheel={onWheel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
        >
          <defs>
            <radialGradient id="node-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(255,255,255,0.35)" />
              <stop offset="70%" stopColor="rgba(255,255,255,0)" />
            </radialGradient>
          </defs>
          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {/* edges */}
            {data && data.edges.map((e, i) => {
              const s = nodePos.current.get(e.source);
              const tp = nodePos.current.get(e.target);
              if (!s || !tp) return null;
              const isHot = hoverId && (hoverId === e.source || hoverId === e.target);
              return (
                <line
                  key={`e-${i}`}
                  x1={s.x} y1={s.y} x2={tp.x} y2={tp.y}
                  stroke={isHot ? 'rgba(255,214,140,0.7)' : 'rgba(255,255,255,0.15)'}
                  strokeWidth={isHot ? 1.4 : 0.8}
                />
              );
            })}
            {/* nodes */}
            {data && simNodes.map((n) => {
              const pos = nodePos.current.get(n.id) ?? { x: n.x, y: n.y };
              const hue = teacherHue(n.teacher);
              const r = nodeRadius(n.degree);
              const isHover = hoverId === n.id;
              const showLabel = isHover || zoom > 1.2 || n.degree >= 3;
              return (
                <g
                  key={n.id}
                  transform={`translate(${pos.x} ${pos.y})`}
                  onPointerEnter={() => setHoverId(n.id)}
                  onPointerLeave={() => setHoverId((v) => (v === n.id ? null : v))}
                  style={{ cursor: 'pointer' }}
                >
                  <circle r={r + 8} fill="url(#node-glow)" opacity={isHover ? 0.9 : 0.5} data-node-id={n.id} />
                  <circle
                    r={r}
                    fill={`hsl(${hue} 70% 60%)`}
                    stroke={isHover ? 'rgba(255,255,255,0.9)' : `hsl(${hue} 70% 40%)`}
                    strokeWidth={isHover ? 2 : 1}
                    data-node-id={n.id}
                  />
                  {showLabel && (
                    <text
                      textAnchor="middle"
                      dy={r + 14}
                      style={{ fontSize: 11, fontWeight: 500, fill: 'rgba(255,255,255,0.92)', pointerEvents: 'none', textShadow: '0 1px 2px rgba(0,0,0,0.8)' }}
                    >
                      {n.label.length > 22 ? n.label.slice(0, 22) + '…' : n.label}
                    </text>
                  )}
                </g>
              );
            })}
            {loading && (
              <text x={WIDTH / 2} y={HEIGHT / 2} textAnchor="middle" style={{ fontSize: 13, fill: 'rgba(255,255,255,0.6)' }}>
                Loading the wisdom map…
              </text>
            )}
          </g>
        </svg>
      </div>

      {data && (
        <p className="text-xs text-muted-foreground text-center">
          {data.nodes.length} concepts · {data.edges.length} connections
        </p>
      )}
    </div>
  );
};

export default KGConceptMap;
