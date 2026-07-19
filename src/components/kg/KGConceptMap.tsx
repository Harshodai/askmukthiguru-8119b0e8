import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Search, ZoomIn, ZoomOut, RotateCcw, ArrowUp } from 'lucide-react';

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

interface SimNode extends KGNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx: number;
  fy: number;
  pinned: boolean;
}

const DEMO_DATA: Subgraph = {
  nodes: [
    { id: '1', label: 'Beautiful State', type: 'State', teacher: 'Sri Preethaji' },
    { id: '2', label: 'Suffering State', type: 'State', teacher: 'Sri Preethaji' },
    { id: '3', label: 'Witnessing Awareness', type: 'Concept', teacher: 'Sri Preethaji' },
    { id: '4', label: 'Compassion', type: 'Practice', teacher: 'Sri Preethaji' },
    { id: '5', label: 'Stillness', type: 'Practice', teacher: 'Sri Preethaji' },
    { id: '6', label: 'Ekam', type: 'Concept', teacher: 'Sri Preethaji' },
    { id: '7', label: 'Krishnamurti', type: 'Teacher', teacher: 'J. Krishnamurti' },
    { id: '8', label: 'Freedom from Known', type: 'Concept', teacher: 'J. Krishnamurti' },
    { id: '9', label: 'Observation', type: 'Practice', teacher: 'J. Krishnamurti' },
    { id: '10', label: 'Serene Mind', type: 'Practice', teacher: 'Sri Preethaji' },
  ],
  edges: [
    { source: '1', target: '2', label: 'opposes' },
    { source: '1', target: '3', label: 'cultivates' },
    { source: '2', target: '3', label: 'dissolves' },
    { source: '1', target: '5', label: 'leads to' },
    { source: '3', target: '4', label: 'inspires' },
    { source: '5', target: '6', label: 'reveals' },
    { source: '7', target: '8', label: 'taught' },
    { source: '7', target: '9', label: 'taught' },
    { source: '8', target: '3', label: 'aligns with' },
    { source: '9', target: '3', label: 'deepens' },
    { source: '1', target: '10', label: 'is' },
  ],
};

const TYPE_COLORS: Record<string, string> = {
  teacher: '#f59e0b',
  concept: '#8b5cf6',
  practice: '#10b981',
  state: '#3b82f6',
};

const typeColor = (type: string): string =>
  TYPE_COLORS[type?.toLowerCase()] ?? '#6b7280';

export const KGConceptMap = ({ initialQuery = '' }: { initialQuery?: string }) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState(initialQuery);
  const [submitted, setSubmitted] = useState(initialQuery);
  const [data, setData] = useState<Subgraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);

  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null);

  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [pulsingNodeId, setPulsingNodeId] = useState<string | null>(null);
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [containerWidth, setContainerWidth] = useState(800);
  const demoTimerRef = useRef<number | null>(null);

  const viewBoxHeight = Math.max(400, Math.round(containerWidth * 0.55));
  const simRef = useRef<{
    nodes: SimNode[];
    edges: KGEdge[];
    tick: number;
    running: boolean;
  }>({ nodes: [], edges: [], tick: 0, running: false });
  const [simHeat, setSimHeat] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = entry.contentRect.width;
        if (w > 0) setContainerWidth(Math.round(w));
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const neighborSet = useMemo(() => {
    if (!hoveredNodeId || !data) return null;
    const set = new Set<string>();
    set.add(hoveredNodeId);
    data.edges.forEach((e) => {
      if (e.source === hoveredNodeId) set.add(e.target);
      if (e.target === hoveredNodeId) set.add(e.source);
    });
    return set;
  }, [hoveredNodeId, data]);

  const uniqueTypes = useMemo(() => {
    if (!data) return [] as string[];
    const types = new Set(data.nodes.map((n) => n.type));
    return Array.from(types);
  }, [data]);

  const fetchSubgraph = useCallback(async (q: string) => {
    if (!q.trim()) return;
    if (demoTimerRef.current) {
      clearTimeout(demoTimerRef.current);
      demoTimerRef.current = null;
    }
    setIsDemo(false);
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const { endpoint } = getAIConfig();
      const baseUrl = (endpoint ?? '').replace(/\/api\/chat\/?$/, '');
      const url = `${baseUrl}/api/kg/subgraph?query=${encodeURIComponent(q.trim())}&limit=20`;
      const token = await getAccessToken();
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as Subgraph;
      setData(json);
      setError(null);
      setIsDemo(false);
      setPan({ x: 0, y: 0 });
      setZoom(1);
    } catch {
      setError(t('kg.apiUnreachable', 'Backend unreachable'));
      demoTimerRef.current = window.setTimeout(() => {
        setData(DEMO_DATA);
        setIsDemo(true);
        setError(null);
        setPan({ x: 0, y: 0 });
        setZoom(1);
      }, 4000);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (submitted) fetchSubgraph(submitted);
  }, [submitted, fetchSubgraph]);

  useEffect(() => {
    return () => {
      if (demoTimerRef.current) clearTimeout(demoTimerRef.current);
    };
  }, []);

  const centerX = containerWidth / 2;
  const centerY = viewBoxHeight / 2;

  const prevDataRef = useRef<typeof data>(null);

  useEffect(() => {
    if (!data || !data.nodes.length) {
      simRef.current = { nodes: [], edges: [], tick: 0, running: false };
      return;
    }
    const isNewData = prevDataRef.current !== data;
    prevDataRef.current = data;
    if (isNewData) {
      const spread = Math.min(containerWidth, viewBoxHeight) * 0.35;
      const simNodes: SimNode[] = data.nodes.map((n) => ({
        ...n,
        x: centerX + (Math.random() - 0.5) * spread * 2,
        y: centerY + (Math.random() - 0.5) * spread * 1.4,
        vx: 0,
        vy: 0,
        fx: 0,
        fy: 0,
        pinned: false,
      }));
      simRef.current.nodes = simNodes;
      simRef.current.edges = data.edges;
    } else {
      simRef.current.edges = data.edges;
    }
    simRef.current.tick = 0;
    simRef.current.running = true;

    let animId: number;
    const loop = () => {
      if (!simRef.current.running) return;
      const { nodes } = simRef.current;
      const edges = simRef.current.edges;

      for (const n of nodes) {
        n.fx = 0;
        n.fy = 0;
      }

      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 220) {
            const force = 800 / (dist * dist);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            a.fx -= fx;
            a.fy -= fy;
            b.fx += fx;
            b.fy += fy;
          }
        }
      }

      for (const edge of edges) {
        const s = nodes.find((n) => n.id === edge.source);
        const t = nodes.find((n) => n.id === edge.target);
        if (!s || !t) continue;
        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const disp = dist - 95;
        const force = disp * 0.005;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        s.fx += fx;
        s.fy += fy;
        t.fx -= fx;
        t.fy -= fy;
      }

      for (const n of nodes) {
        if (n.pinned) continue;
        n.fx -= (n.x - centerX) * 0.008;
        n.fy -= (n.y - centerY) * 0.008;
      }

      for (const n of nodes) {
        if (n.pinned) continue;
        n.vx += n.fx;
        n.vy += n.fy;
        n.vx *= 0.82;
        n.vy *= 0.82;
        n.x += n.vx;
        n.y += n.vy;
      }

      simRef.current.tick++;
      if (simRef.current.tick >= 300) {
        simRef.current.running = false;
      }
      setSimHeat((h) => h + 1);
      if (simRef.current.running) {
        animId = requestAnimationFrame(loop);
      }
    };
    animId = requestAnimationFrame(loop);
    return () => {
      simRef.current.running = false;
      cancelAnimationFrame(animId);
    };
  }, [data, containerWidth, viewBoxHeight, centerX, centerY]);

  const nodeDegree = useMemo(() => {
    if (!data) return new Map<string, number>();
    const deg = new Map<string, number>();
    for (const n of data.nodes) deg.set(n.id, 0);
    for (const e of data.edges) {
      deg.set(e.source, (deg.get(e.source) || 0) + 1);
      deg.set(e.target, (deg.get(e.target) || 0) + 1);
    }
    return deg;
  }, [data]);

  const onWheel = useCallback((e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const delta = -e.deltaY * 0.0015;
    setZoom((z) => Math.min(3, Math.max(0.3, z + delta)));
  }, []);

  const backgroundPointerDown = useCallback(
    (e: React.PointerEvent<SVGSVGElement>) => {
      const target = e.target as Element;
      if (target.tagName !== 'svg' && target.tagName !== 'SVG') return;
      target.setPointerCapture?.(e.pointerId);
      dragRef.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
    },
    [pan],
  );

  const pointerMove = useCallback(
    (e: React.PointerEvent<SVGSVGElement>) => {
      if (draggedNodeId) {
        const rect = svgRef.current?.getBoundingClientRect();
        if (!rect) return;
        const svgX = (e.clientX - rect.left) * (containerWidth / rect.width);
        const svgY = (e.clientY - rect.top) * (viewBoxHeight / rect.height);
        const x = (svgX - pan.x) / zoom;
        const y = (svgY - pan.y) / zoom;
        const node = simRef.current.nodes.find((n) => n.id === draggedNodeId);
        if (node) {
          node.x = x;
          node.y = y;
          setSimHeat((h) => h + 1);
        }
        return;
      }
      if (!dragRef.current) return;
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      setPan({ x: dragRef.current.panX + dx, y: dragRef.current.panY + dy });
    },
    [draggedNodeId, pan, zoom, containerWidth, viewBoxHeight],
  );

  const pointerUp = useCallback(() => {
    if (draggedNodeId) {
      const node = simRef.current.nodes.find((n) => n.id === draggedNodeId);
      if (node) node.pinned = false;
      setDraggedNodeId(null);
      simRef.current.tick = 0;
      simRef.current.running = true;
      setSimHeat((h) => h + 1);
    }
    dragRef.current = null;
  }, [draggedNodeId]);

  const handleNodePointerDown = useCallback(
    (e: React.PointerEvent, nodeId: string) => {
      e.stopPropagation();
      (e.target as Element).setPointerCapture?.(e.pointerId);
      const node = simRef.current.nodes.find((n) => n.id === nodeId);
      if (node) node.pinned = true;
      setDraggedNodeId(nodeId);
    },
    [],
  );

  const handleNodeClick = useCallback(
    (e: React.MouseEvent, nodeId: string) => {
      e.stopPropagation();
      setPulsingNodeId(nodeId);
      setTimeout(() => setPulsingNodeId(null), 300);
    },
    [],
  );

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(query);
  };

  const activeNodes = useMemo(
    () => (data && data.nodes.length > 0 ? simRef.current.nodes : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, simHeat],
  );

  const activeEdges = useMemo(
    () => (data && data.nodes.length > 0 ? simRef.current.edges : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, simHeat],
  );

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
        <button
          onClick={() => setZoom((z) => Math.min(3, z + 0.2))}
          className="p-1.5 rounded border border-border hover:bg-muted"
          title="Zoom in"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.3, z - 0.2))}
          className="p-1.5 rounded border border-border hover:bg-muted"
          title="Zoom out"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => {
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
          className="p-1.5 rounded border border-border hover:bg-muted"
          title="Reset view"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
        <span className="ml-1">{t('kg.dragToPan')}</span>
      </div>

      {error && (
        <div className="text-sm text-destructive">
          {t('kg.errorLoading', { error })}
        </div>
      )}

      {isDemo && data && (
        <div className="text-sm text-muted-foreground text-center">
          {t('kg.showingDemo', 'Showing demo data instead')}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-sm">{t('kg.loading')}</span>
        </div>
      )}

      {!data && !loading && !error && (
        <div className="flex flex-col items-center justify-center py-24 text-muted-foreground gap-4">
          <div className="animate-bounce">
            <ArrowUp className="w-8 h-8 text-ojas/60" />
          </div>
          <p className="text-sm text-center max-w-xs">
            {t('kg.emptyPrompt', 'Explore the wisdom map \u2014 search above')}
          </p>
        </div>
      )}

      {data && data.nodes.length === 0 && !loading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <p className="text-sm">{t('kg.noConceptsFor', { query: submitted })}</p>
        </div>
      )}

      <div
        ref={containerRef}
        className="relative rounded-xl border border-border overflow-hidden bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950"
      >
        <svg
          ref={svgRef}
          width="100%"
          viewBox={`0 0 ${containerWidth} ${viewBoxHeight}`}
          className="block touch-none select-none"
          style={{ minHeight: viewBoxHeight, cursor: draggedNodeId ? 'grabbing' : dragRef.current ? 'grabbing' : hoveredNodeId ? 'pointer' : 'grab' }}
          onWheel={onWheel}
          onPointerDown={backgroundPointerDown}
          onPointerMove={pointerMove}
          onPointerUp={pointerUp}
          onPointerLeave={pointerUp}
        >
          <defs>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="glow-strong">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {activeEdges.map((e, i) => {
              const s = simRef.current.nodes.find((n) => n.id === e.source);
              const t = simRef.current.nodes.find((n) => n.id === e.target);
              if (!s || !t) return null;
              const faded = neighborSet !== null && (!neighborSet.has(e.source) || !neighborSet.has(e.target));
              return (
                <line
                  key={`e-${i}`}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={hoveredNodeId ? '#a1a1aa' : '#52525b'}
                  strokeWidth={faded ? 0.3 : 0.5 + ((i * 7) % 5) * 0.25}
                  opacity={faded ? 0.05 : 0.3}
                />
              );
            })}

            {activeNodes.map((n) => {
              const deg = nodeDegree.get(n.id) || 0;
              const r = Math.max(8, Math.min(28, deg * 3 + 8));
              const color = typeColor(n.type);
              const isHovered = hoveredNodeId === n.id;
              const faded = neighborSet !== null && !neighborSet.has(n.id);
              const pulsing = pulsingNodeId === n.id;
              const displayR = pulsing ? r * 1.4 : r;

              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x} ${n.y})`}
                  opacity={faded ? 0.15 : 1}
                  style={{ transition: 'opacity 0.15s ease-out' }}
                  onPointerEnter={() => setHoveredNodeId(n.id)}
                  onPointerLeave={() => setHoveredNodeId(null)}
                  onPointerDown={(e) => handleNodePointerDown(e, n.id)}
                  onClick={(e) => handleNodeClick(e, n.id)}
                >
                  <circle
                    r={isHovered ? displayR + 4 : displayR + 2}
                    fill={`${color}15`}
                    filter="url(#glow)"
                  />
                  <circle
                    r={displayR}
                    fill={`${color}90`}
                    stroke={color}
                    strokeWidth={isHovered ? 2.5 : 1.5}
                    filter={isHovered ? 'url(#glow-strong)' : undefined}
                  />
                  {n.teacher && (
                    <text
                      textAnchor="middle"
                      dy={`-${r + 10}px`}
                      fill="#a1a1aa"
                      style={{ fontSize: 8, pointerEvents: 'none', textShadow: '0 1px 3px rgba(0,0,0,0.8)' }}
                    >
                      {n.teacher.length > 16 ? n.teacher.slice(0, 16) + '\u2026' : n.teacher}
                    </text>
                  )}
                  <text
                    textAnchor="middle"
                    dy="0.35em"
                    fill="#f4f4f5"
                    style={{
                      fontSize: Math.max(8, Math.min(11, r * 0.55)),
                      fontWeight: 500,
                      pointerEvents: 'none',
                      textShadow: '0 1px 4px rgba(0,0,0,0.9)',
                    }}
                  >
                    {n.label.length > 16 ? n.label.slice(0, 16) + '\u2026' : n.label}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>

        {uniqueTypes.length > 0 && (
          <div className="absolute bottom-2 left-2 flex flex-wrap gap-3 pointer-events-none">
            {uniqueTypes.map((type) => (
              <div key={type} className="flex items-center gap-1.5">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: typeColor(type) }}
                />
                <span className="text-[10px] text-muted-foreground capitalize">{type}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {data && data.nodes.length > 0 && (
        <p className="text-xs text-muted-foreground text-center mt-3">
          {t('kg.conceptRelationshipCount', {
            nodeCount: data.nodes.length,
            edgeCount: data.edges.length,
          })}
        </p>
      )}
    </div>
  );
};

export default KGConceptMap;
