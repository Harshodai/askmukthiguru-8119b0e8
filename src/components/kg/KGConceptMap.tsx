import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Search, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';

import { getAIConfig } from '@/lib/chat/config';
import { getAccessToken } from '@/lib/chat/auth';

interface KGNode {
  id: string;
  label: string;
  type: string;
  teacher?: string | null;
}
interface KGEdge {
  source: string;
  target: string;
  label?: string | null;
}
interface Subgraph {
  nodes: KGNode[];
  edges: KGEdge[];
}

/** Deterministic hue (0-360) from a teacher string — keeps colors stable across renders. */
const teacherHue = (teacher: string | null | undefined): number => {
  if (!teacher) return 210; // slate
  let h = 0;
  for (let i = 0; i < teacher.length; i++) h = (h * 31 + teacher.charCodeAt(i)) % 360;
  return h;
};

/** Circular layout — deterministic, no deps. Nodes evenly spaced on a ring. */
const layout = (nodes: KGNode[], radius: number) => {
  const map = new Map<string, { x: number; y: number }>();
  const n = nodes.length;
  nodes.forEach((node, i) => {
    const angle = n > 1 ? (i / n) * Math.PI * 2 : 0;
    map.set(node.id, { x: radius + Math.cos(angle) * radius * 0.75, y: radius + Math.sin(angle) * radius * 0.75 });
  });
  return map;
};

const WIDTH = 760;
const HEIGHT = 560;

export const KGConceptMap = ({ initialQuery = '' }: { initialQuery?: string }) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState(initialQuery);
  const [submitted, setSubmitted] = useState(initialQuery);
  const [data, setData] = useState<Subgraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pan / zoom state
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const positions = useMemo(() => (data ? layout(data.nodes, Math.min(WIDTH, HEIGHT) / 2) : new Map()), [data]);

  const fetchSubgraph = useCallback(async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const { endpoint } = getAIConfig();
      const baseUrl = (endpoint ?? '').replace(/\/api\/chat\/?$/, '');
      const url = `${baseUrl}/api/kg/subgraph?query=${encodeURIComponent(q.trim())}&limit=20`;
      const token = await getAccessToken();
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as Subgraph;
      setData(json);
      setPan({ x: 0, y: 0 });
      setZoom(1);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load graph';
      setError(msg);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (submitted) fetchSubgraph(submitted);
  }, [submitted, fetchSubgraph]);

  const onWheel = useCallback((e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const delta = -e.deltaY * 0.0015;
    setZoom((z) => Math.min(3, Math.max(0.3, z + delta)));
  }, []);

  const onPointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragRef.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
  }, [pan]);

  const onPointerMove = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setPan({ x: dragRef.current.panX + dx, y: dragRef.current.panY + dy });
  }, []);

  const onPointerUp = useCallback(() => { dragRef.current = null; }, []);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(query);
  };

  return (
    <div className="flex flex-col gap-4 w-full max-w-4xl mx-auto p-4">
      <form onSubmit={submit} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('kg.searchPlaceholderDetailed')}
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ojas/40"
            aria-label="Knowledge graph query"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-ojas text-white text-sm font-medium disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          {t('kg.explore')}
        </button>
      </form>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <button onClick={() => setZoom((z) => Math.min(3, z + 0.2))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom in"><ZoomIn className="w-3.5 h-3.5" /></button>
        <button onClick={() => setZoom((z) => Math.max(0.3, z - 0.2))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom out"><ZoomOut className="w-3.5 h-3.5" /></button>
        <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="p-1.5 rounded border border-border hover:bg-muted" title="Reset view"><RotateCcw className="w-3.5 h-3.5" /></button>
        <span className="ml-1">{t('kg.dragToPan')}</span>
      </div>

      {error && <div className="text-sm text-destructive">{t('kg.errorLoading', { error })}</div>}

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <svg
          ref={svgRef}
          width="100%"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="block touch-none select-none"
          style={{ height: HEIGHT, cursor: dragRef.current ? 'grabbing' : 'grab' }}
          onWheel={onWheel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
        >
          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {data && data.edges.map((e, i) => {
              const s = positions.get(e.source);
              const t = positions.get(e.target);
              if (!s || !t) return null;
              return (
                <g key={`e-${i}`}>
                  <line x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke="hsl(var(--border))" strokeWidth={1} />
                  {e.label && (
                    <text
                      x={(s.x + t.x) / 2}
                      y={(s.y + t.y) / 2}
                      textAnchor="middle"
                      className="fill-muted-foreground"
                      style={{ fontSize: 9, pointerEvents: 'none' }}
                    >
                      {e.label.length > 20 ? e.label.slice(0, 20) + '…' : e.label}
                    </text>
                  )}
                </g>
              );
            })}
            {data && data.nodes.map((n) => {
              const pos = positions.get(n.id);
              if (!pos) return null;
              const hue = teacherHue(n.teacher);
              const r = 22;
              return (
                <g key={n.id} transform={`translate(${pos.x} ${pos.y})`}>
                  <circle r={r} fill={`hsl(${hue} 60% 45% / 0.85)`} stroke={`hsl(${hue} 60% 30%)`} strokeWidth={1.5} />
                  <text
                    textAnchor="middle"
                    dy="0.35em"
                    className="fill-foreground"
                    style={{ fontSize: 10, fontWeight: 500, pointerEvents: 'none' }}
                  >
                    {n.label.length > 18 ? n.label.slice(0, 18) + '…' : n.label}
                  </text>
                  {n.teacher && (
                    <text textAnchor="middle" dy={`${r + 12}px`} className="fill-muted-foreground" style={{ fontSize: 8, pointerEvents: 'none' }}>
                      {n.teacher}
                    </text>
                  )}
                </g>
              );
            })}
            {data && data.nodes.length === 0 && !loading && (
              <text x={WIDTH / 2} y={HEIGHT / 2} textAnchor="middle" className="fill-muted-foreground" style={{ fontSize: 13 }}>
                {t('kg.noConceptsFor', { query: submitted })}
              </text>
            )}
            {!data && !loading && (
              <text x={WIDTH / 2} y={HEIGHT / 2} textAnchor="middle" className="fill-muted-foreground" style={{ fontSize: 13 }}>
                {t('kg.searchToVisualise')}
              </text>
            )}
            {loading && (
              <text x={WIDTH / 2} y={HEIGHT / 2} textAnchor="middle" className="fill-muted-foreground" style={{ fontSize: 13 }}>
                {t('kg.loading')}
              </text>
            )}
          </g>
        </svg>
      </div>

      {data && data.nodes.length > 0 && (
        <p className="text-xs text-muted-foreground text-center">
          {t('kg.conceptRelationshipCount', { nodeCount: data.nodes.length, edgeCount: data.edges.length })}
        </p>
      )}
    </div>
  );
};

export default KGConceptMap;