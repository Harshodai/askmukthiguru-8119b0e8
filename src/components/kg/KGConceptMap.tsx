import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CSSProperties, FormEvent, MouseEvent } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Loader2, Search, Sparkles, X } from 'lucide-react';
import { getAIConfig } from '@/lib/chat/config';
import { getAccessToken } from '@/lib/chat/auth';

export interface KGNode {
  id: string;
  label: string;
  type: string;
  teacher?: string | null;
  state_category?: string | null;
  content_preview?: string | null;
}

export interface KGEdge {
  source: string;
  target: string;
  label?: string | null;
}

export interface Subgraph {
  nodes: KGNode[];
  edges: KGEdge[];
  query?: string;
  count?: number;
}

export const DEMO_DATA: Subgraph = {
  nodes: [
    { id: '1', label: 'Beautiful State', type: 'State', teacher: 'Sri Preethaji' },
    { id: '2', label: 'Witnessing Awareness', type: 'Concept', teacher: 'Sri Preethaji' },
    { id: '3', label: 'Compassion', type: 'Practice', teacher: 'Sri Preethaji' },
    { id: '4', label: 'Stillness', type: 'Practice', teacher: 'Sri Preethaji' },
    { id: '5', label: 'Sri Krishnaji', type: 'Teacher', teacher: 'Sri Krishnaji' },
    { id: '6', label: 'Observation', type: 'Practice', teacher: 'Sri Krishnaji' },
  ],
  edges: [
    { source: '1', target: '2', label: 'cultivates' },
    { source: '2', target: '3', label: 'inspires' },
    { source: '1', target: '4', label: 'leads to' },
    { source: '5', target: '6', label: 'taught' },
    { source: '6', target: '2', label: 'deepens' },
  ],
};

const TYPE_STYLES: Record<string, { accent: string; soft: string; icon: string }> = {
  user: { accent: '#f59e0b', soft: 'rgba(245,158,11,.12)', icon: '✦' },
  memory: { accent: '#34d399', soft: 'rgba(52,211,153,.10)', icon: '✎' },
  concept: { accent: '#a78bfa', soft: 'rgba(167,139,250,.10)', icon: '◈' },
  practice: { accent: '#60a5fa', soft: 'rgba(96,165,250,.10)', icon: '◌' },
  state: { accent: '#fbbf24', soft: 'rgba(251,191,36,.10)', icon: '◉' },
  teacher: { accent: '#fb7185', soft: 'rgba(251,113,133,.10)', icon: '○' },
  notebookitem: { accent: '#22d3ee', soft: 'rgba(34,211,238,.10)', icon: '▤' },
};

const getNodeVisual = (type: string) =>
  TYPE_STYLES[type?.toLowerCase()] ?? { accent: '#a1a1aa', soft: 'rgba(161,161,170,.10)', icon: '•' };

const KNOWN_TEACHERS = new Set(['Sri Preethaji', 'Sri Krishnaji']);
const NODE_WIDTH = 220;
const NODE_HEIGHT = 104;

type WisdomNodeData = {
  label: string;
  nodeType: string;
  teacher?: string | null;
  stateCategory?: string | null;
  contentPreview?: string | null;
  degree: number;
};

type WisdomFlowNode = Node<WisdomNodeData, 'wisdom'>;

const nodeTypes = {
  wisdom: WisdomNode,
};

function WisdomNode({ data, selected }: NodeProps<WisdomFlowNode>) {
  const visual = getNodeVisual(data.nodeType);
  const isUser = data.nodeType.toLowerCase() === 'user';
  const showTeacher = Boolean(data.teacher && KNOWN_TEACHERS.has(data.teacher));

  return (
    <div
      data-testid="kg-node"
      aria-label={data.label}
      className="relative min-w-[168px] max-w-[220px] rounded-2xl border bg-background/95 px-3.5 py-3 shadow-lg backdrop-blur-md transition-all duration-150"
      style={{
        borderColor: selected ? visual.accent : 'rgba(255,255,255,.12)',
        boxShadow: selected
          ? `0 0 0 1px ${visual.accent}55, 0 14px 32px rgba(0,0,0,.28)`
          : '0 10px 24px rgba(0,0,0,.22)',
      }}
    >
      <Handle id="target-top" type="target" position={Position.Top} className="!h-1 !w-8 !border-0 !bg-transparent" />
      <Handle id="target-right" type="target" position={Position.Right} className="!h-8 !w-1 !border-0 !bg-transparent" />
      <Handle id="target-bottom" type="target" position={Position.Bottom} className="!h-1 !w-8 !border-0 !bg-transparent" />
      <Handle id="target-left" type="target" position={Position.Left} className="!h-8 !w-1 !border-0 !bg-transparent" />
      <Handle id="source-top" type="source" position={Position.Top} className="!h-1 !w-8 !border-0 !bg-transparent" />
      <Handle id="source-right" type="source" position={Position.Right} className="!h-8 !w-1 !border-0 !bg-transparent" />
      <Handle id="source-bottom" type="source" position={Position.Bottom} className="!h-1 !w-8 !border-0 !bg-transparent" />
      <Handle id="source-left" type="source" position={Position.Left} className="!h-8 !w-1 !border-0 !bg-transparent" />

      <div className="flex items-start gap-2.5">
        <span
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-xl text-sm"
          style={{ color: visual.accent, background: visual.soft }}
          aria-hidden="true"
        >
          {isUser ? '✦' : visual.icon}
        </span>
        <div className="min-w-0">
          <div className="text-[9px] font-semibold uppercase tracking-[0.18em] text-muted-foreground/75">
            {data.nodeType === 'NotebookItem' ? 'Notebook' : data.nodeType}
          </div>
          <div
            className="mt-0.5 line-clamp-2 text-[13px] font-semibold leading-5 text-foreground"
            title={data.label}
          >
            {data.label}
          </div>
        </div>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        {showTeacher && (
          <span className="rounded-full border px-2 py-0.5 text-[9px] text-muted-foreground" style={{ borderColor: `${visual.accent}44` }}>
            {data.teacher}
          </span>
        )}
        {data.stateCategory && (
          <span className="rounded-full border border-white/10 px-2 py-0.5 text-[9px] text-muted-foreground">
            {data.stateCategory}
          </span>
        )}
        {!isUser && data.degree > 0 && (
          <span className="ms-auto text-[9px] text-muted-foreground/65">
            {data.degree} {data.degree === 1 ? 'link' : 'links'}
          </span>
        )}
      </div>
    </div>
  );
}

function layoutGraph(data: Subgraph): WisdomFlowNode[] {
  const valid = data.nodes.filter((node) => node.id && node.label);
  const user = valid.find((node) => node.type.toLowerCase() === 'user');
  const conceptual = valid.filter((node) =>
    ['concept', 'state', 'practice', 'teacher'].includes(node.type.toLowerCase()),
  );
  const personal = valid.filter((node) =>
    ['memory', 'notebookitem'].includes(node.type.toLowerCase()),
  );

  const degree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();
  for (const node of valid) {
    degree.set(node.id, 0);
    adjacency.set(node.id, []);
  }
  for (const edge of data.edges) {
    if (!degree.has(edge.source) || !degree.has(edge.target)) continue;
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    adjacency.get(edge.source)?.push(edge.target);
    adjacency.get(edge.target)?.push(edge.source);
  }

  const positions = new Map<string, { x: number; y: number }>();
  const center = { x: 620, y: 380 };
  if (user) positions.set(user.id, { x: center.x - 100, y: center.y - 40 });

  const placeRing = (items: KGNode[], radius: number, startAngle: number, yScale = 0.82) => {
    if (!items.length) return;
    items.forEach((node, index) => {
      const angle = startAngle + (index / items.length) * Math.PI * 2;
      positions.set(node.id, {
        x: center.x + Math.cos(angle) * radius - 110,
        y: center.y + Math.sin(angle) * radius * yScale - 48,
      });
    });
  };

  placeRing(conceptual, conceptual.length <= 1 ? 0 : 245, -Math.PI / 2);
  placeRing(personal, personal.length <= 1 ? 250 : 410, -Math.PI / 2 + 0.25);

  return valid.map((node) => {
    let position = positions.get(node.id);
    if (!position) {
      const fallbackAngle = valid.indexOf(node) * 0.75;
      position = {
        x: center.x + Math.cos(fallbackAngle) * 320 - 105,
        y: center.y + Math.sin(fallbackAngle) * 260 - 43,
      };
    }

    return {
      id: node.id,
      type: 'wisdom',
      position,
      draggable: false,
      selectable: true,
      data: {
        label: node.label,
        nodeType: node.type,
        teacher: node.teacher,
        stateCategory: node.state_category,
        contentPreview: node.content_preview,
        degree: degree.get(node.id) ?? 0,
      },
      style: { width: NODE_WIDTH } satisfies CSSProperties,
    };
  });
}

function directionalHandles(
  source: { x: number; y: number },
  target: { x: number; y: number },
) {
  const dx = (target.x + NODE_WIDTH / 2) - (source.x + NODE_WIDTH / 2);
  const dy = (target.y + NODE_HEIGHT / 2) - (source.y + NODE_HEIGHT / 2);
  const horizontal = Math.abs(dx) >= Math.abs(dy);

  if (horizontal) {
    return {
      sourceHandle: dx >= 0 ? 'source-right' : 'source-left',
      targetHandle: dx >= 0 ? 'target-left' : 'target-right',
    };
  }

  return {
    sourceHandle: dy >= 0 ? 'source-bottom' : 'source-top',
    targetHandle: dy >= 0 ? 'target-top' : 'target-bottom',
  };
}

function edgeStyle(label?: string | null, active = false) {
  const semantic = Boolean(label && !['HAS_MEMORY', 'SAVED_NOTE'].includes(label));
  return {
    stroke: active ? '#f59e0b' : semantic ? '#8a8274' : '#4b463f',
    strokeWidth: active ? 2.2 : semantic ? 1.45 : 1.1,
    opacity: active ? 0.95 : semantic ? 0.68 : 0.42,
  };
}

export const KGConceptMap = ({ initialQuery = '' }: { initialQuery?: string }) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState(initialQuery);
  const [submitted, setSubmitted] = useState(initialQuery);
  const [data, setData] = useState<Subgraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const [isPersonal, setIsPersonal] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const fetchSubgraph = useCallback(
    async (q: string) => {
      setLoading(true);
      setError(null);
      setIsDemo(false);
      let personal = false;

      try {
        const { endpoint } = getAIConfig();
        const baseUrl = (endpoint ?? '').replace(/\/api\/chat\/?$/, '');
        const token = await getAccessToken();
        personal = Boolean(token);
        setIsPersonal(personal);

        const effectiveQuery = q.trim();
        const url = personal
          ? `${baseUrl}/api/kg/personal-subgraph?limit=50&query=${encodeURIComponent(effectiveQuery)}`
          : `${baseUrl}/api/kg/subgraph?query=${encodeURIComponent(effectiveQuery || 'beautiful state')}&limit=24`;

        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 8000);
        const res = await fetch(url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });
        window.clearTimeout(timeoutId);

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as Subgraph;

        if (!json.nodes || json.nodes.length === 0) {
          setData(null);
          setSelectedNodeId(null);
          setError(
            personal
              ? t(
                  'kg.noPersonalConcepts',
                  'Your personal wisdom map is empty for now. Save a reflection, memory, or study note to build it.',
                )
              : t('kg.noConceptsFor', 'No teachings found for this search.'),
          );
          return;
        }

        setData(json);
        setSelectedNodeId(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.warn('[Wisdom Map] live graph unavailable', message);
        setData(null);
        setSelectedNodeId(null);

        if (personal) {
          setError(
            t('kg.personalMapUnavailable', 'Your personal wisdom map is unavailable right now. Please try again.'),
          );
        } else {
          setError(t('kg.errorLoading', "Couldn't load graph: {{error}}", { error: 'live data unavailable' }));
        }
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void fetchSubgraph(submitted);
    // One request per submitted query.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submitted]);

  const flowNodes = useMemo(() => (data ? layoutGraph(data) : []), [data]);

  const flowEdges = useMemo<Edge[]>(() => {
    if (!data) return [];
    const selected = selectedNodeId;
    const positions = new Map(flowNodes.map((node) => [node.id, node.position]));

    return data.edges
      .filter((edge) => edge.source && edge.target)
      .map((edge, index) => {
        const sourcePosition = positions.get(edge.source) ?? { x: 0, y: 0 };
        const targetPosition = positions.get(edge.target) ?? { x: 0, y: 0 };
        const handles = directionalHandles(sourcePosition, targetPosition);

        return {
          id: `edge-${index}-${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          sourceHandle: handles.sourceHandle,
          targetHandle: handles.targetHandle,
          type: 'smoothstep',
          pathOptions: { borderRadius: 14, offset: 18 },
          label: edge.label && !['HAS_MEMORY', 'SAVED_NOTE'].includes(edge.label) ? edge.label : undefined,
          labelStyle: { fill: '#d6d3d1', fontSize: 9, fontWeight: 600 },
          labelBgStyle: { fill: '#15120e', fillOpacity: 0.92 },
          labelBgPadding: [5, 3] as [number, number],
          style: edgeStyle(edge.label, Boolean(selected && (edge.source === selected || edge.target === selected))),
        };
      });
  }, [data, flowNodes, selectedNodeId]);

  const selectedNode = useMemo(
    () => flowNodes.find((node) => node.id === selectedNodeId) ?? null,
    [flowNodes, selectedNodeId],
  );

  const selectedConnections = useMemo(() => {
    if (!selectedNodeId || !data) return [];
    return data.edges
      .filter((edge) => edge.source === selectedNodeId || edge.target === selectedNodeId)
      .map((edge) => {
        const otherId = edge.source === selectedNodeId ? edge.target : edge.source;
        const other = data.nodes.find((node) => node.id === otherId);
        return {
          id: `${edge.source}-${edge.target}-${edge.label ?? ''}`,
          label: other?.label ?? otherId,
          relation: edge.label ?? 'connected',
        };
      })
      .slice(0, 10);
  }, [data, selectedNodeId]);

  const typeCounts = useMemo(() => {
    if (!data) return [];
    const counts = new Map<string, number>();
    for (const node of data.nodes) counts.set(node.type, (counts.get(node.type) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [data]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(query.trim());
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-4 md:p-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-ojas/20 bg-ojas/5 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-ojas">
              <Sparkles className="h-3 w-3" />
              {isPersonal ? t('kg.title') : isDemo ? t('kg.showingDemo') : t('kg.title')}
            </span>
            {isPersonal && (
              <span className="text-[11px] text-muted-foreground">
                {t('kg.subtitle')}
              </span>
            )}
          </div>
          <h2 className="font-serif text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
            {isPersonal ? t('profile.journey.wisdomMap') : t('kg.title')}
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            {t('kg.help')}
          </p>
        </div>

        {data && (
          <div className="grid grid-cols-3 gap-2 md:grid-cols-4">
            <Metric value={data.nodes.length} label={t('kg.relatedConcepts')} />
            <Metric value={data.edges.length} label={t('kg.relationships')} />
            <Metric
              value={data.nodes.filter((node) => node.type.toLowerCase() === 'memory').length}
              label={t('profile.tabs.memory')}
            />
            <Metric
              value={data.nodes.filter((node) =>
                ['concept', 'practice', 'state', 'teacher'].includes(node.type.toLowerCase()),
              ).length}
              label={t('chat.teaching')}
              hideOnMobile
            />
          </div>
        )}
      </div>

      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute start-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={
              isPersonal
                ? 'Focus your map: meditation, stillness, a reflection, a practice…'
                : 'Search a concept, teaching, or practice…'
            }
            aria-label="Knowledge graph query"
            className="w-full rounded-2xl border border-border/50 bg-card/60 py-3.5 ps-11 pe-4 text-sm text-foreground shadow-sm outline-none backdrop-blur focus:border-ojas/50 focus:ring-2 focus:ring-ojas/10"
          />
        </div>
        <button
          type="submit"
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-ojas px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-lg shadow-ojas/15 transition hover:-translate-y-0.5 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Explore
        </button>
        {submitted && !loading && (
          <button
            type="button"
            onClick={() => {
              setQuery('');
              setSubmitted('');
            }}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-border/50 bg-card/60 px-4 py-3.5 text-sm text-muted-foreground hover:bg-card"
          >
            <X className="h-4 w-4" />
            {t('common.clear')}
          </button>
        )}
      </form>

      {error && !isDemo && (
        <div role="alert" className="rounded-2xl border border-border/50 bg-card/50 px-4 py-3 text-sm text-muted-foreground">
          {error}
        </div>
      )}

      {isDemo && data && (
        <div className="flex flex-wrap items-center justify-center gap-3 rounded-2xl border border-ojas/10 bg-ojas/5 px-4 py-3 text-center text-xs text-muted-foreground">
          <span>{t('kg.showingDemo')}</span>
          <button
            type="button"
            onClick={() => void fetchSubgraph(submitted)}
            className="rounded-lg border border-border/50 bg-background/50 px-3 py-1.5 font-medium text-foreground hover:bg-background"
          >
            {t('common.retry')}
          </button>
        </div>
      )}

      {/* Screen reader accessible live summary */}
      <div className="sr-only" aria-live="polite" role="region" aria-label={t('kg.title', 'Wisdom Map')}>
        <h3>{t('kg.title', 'Wisdom Map')}</h3>
        {loading && <p>{t('kg.loading', 'Loading teachings…')}</p>}
        {data && data.nodes.length > 0 && (
          <p>
            {t('kg.graphSummary', 'Wisdom graph containing {{nodeCount}} concepts and {{edgeCount}} connections.', {
              nodeCount: data.nodes.length,
              edgeCount: data.edges.length,
            })}
          </p>
        )}
      </div>

      <div className="grid min-h-[520px] gap-4 xl:grid-cols-[minmax(0,1fr)_310px]">
        <div className="relative overflow-hidden rounded-[28px] border border-border/50 bg-[#0f0c08] shadow-2xl shadow-black/20 min-h-[520px]">
          {loading ? (
            <div className="flex h-[650px] items-center justify-center">
              <div className="flex flex-col items-center gap-3 text-sm text-muted-foreground">
                <div className="rounded-full border border-ojas/20 bg-ojas/5 p-3">
                  <Loader2 className="h-5 w-5 animate-spin text-ojas" />
                </div>
                <span>{t('kg.loading')}</span>
              </div>
            </div>
          ) : data && data.nodes.length ? (
            <>
              <div className="absolute start-4 top-4 z-10 rounded-2xl border border-white/10 bg-black/45 px-3 py-2 backdrop-blur">
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-white/50">{t('kg.title')}</div>
                <div className="mt-0.5 text-xs text-white/80">
                  {data.query ? t('kg.noConceptsFor', { query: data.query }) : t('kg.help')}
                </div>
              </div>

              <ReactFlow
                nodes={flowNodes}
                edges={flowEdges}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.22, maxZoom: 1.15 }}
                minZoom={0.3}
                maxZoom={2}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable
                panOnDrag
                zoomOnScroll
                onNodeClick={(_event: MouseEvent, node) => setSelectedNodeId(node.id)}
                onPaneClick={() => setSelectedNodeId(null)}
                className="bg-[#0f0c08]"
              >
                <Background gap={28} size={1} color="#342c22" />
                <Controls
                  showInteractive={false}
                  className="!m-4 !rounded-xl !border !border-white/10 !bg-black/45 !shadow-lg"
                />
                <MiniMap
                  pannable
                  zoomable
                  nodeStrokeColor={(node) => getNodeVisual(String(node.data?.nodeType ?? '')).accent}
                  nodeColor={(node) => getNodeVisual(String(node.data?.nodeType ?? '')).soft}
                  nodeBorderRadius={8}
                  maskColor="rgba(0,0,0,0.72)"
                  className="!m-4 !overflow-hidden !rounded-xl !border !border-white/10 !bg-black/45"
                />
              </ReactFlow>

              <div className="absolute bottom-4 inset-x-4 z-10 flex flex-wrap items-center gap-2">
                {typeCounts.map(([type, count]) => {
                  const visual = getNodeVisual(type);
                  return (
                    <div
                      key={type}
                      className="flex items-center gap-1.5 rounded-full border border-white/10 bg-black/45 px-2.5 py-1.5 text-[10px] text-white/70 backdrop-blur"
                    >
                      <span className="h-2 w-2 rounded-full" style={{ background: visual.accent }} />
                      {type === 'NotebookItem' ? t('nav.notebooks') : type}
                      <span className="text-white/40">{count}</span>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="flex h-[650px] flex-col items-center justify-center px-6 text-center">
              <div className="mb-4 rounded-2xl border border-ojas/15 bg-ojas/5 p-4">
                <Sparkles className="h-6 w-6 text-ojas" />
              </div>
              <h3 className="font-serif text-xl font-semibold text-white">{t('kg.title')}</h3>
              <p className="mt-2 max-w-md text-sm leading-6 text-white/75">
                {t('kg.searchToVisualise')}
              </p>
            </div>
          )}
        </div>

        <aside className="rounded-[28px] border border-border/50 bg-card/50 p-4 shadow-sm backdrop-blur">
          {selectedNode ? (
            <div className="flex h-full flex-col">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className="rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em]"
                      style={{
                        color: getNodeVisual(selectedNode.data.nodeType).accent,
                        background: getNodeVisual(selectedNode.data.nodeType).soft,
                      }}
                    >
                      {selectedNode.data.nodeType}
                    </span>
                  </div>
                  <h3 className="mt-3 font-serif text-xl font-semibold leading-7 text-foreground">
                    {selectedNode.data.label}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedNodeId(null)}
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="Close node details"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {selectedNode.data.teacher && KNOWN_TEACHERS.has(selectedNode.data.teacher) && (
                <DetailRow label="Teacher" value={selectedNode.data.teacher} />
              )}
              {selectedNode.data.stateCategory && (
                <DetailRow label="State" value={selectedNode.data.stateCategory} />
              )}
              {selectedNode.data.contentPreview && (
                <div className="mt-5 rounded-2xl border border-border/50 bg-background/50 p-3.5">
                  <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/70">
                    {t('chat.personalization.header')}
                  </div>
                  <p className="mt-2 text-sm leading-6 text-foreground/85">
                    {selectedNode.data.contentPreview}
                  </p>
                </div>
              )}

              <div className="mt-5">
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/70">
                  {t('kg.relationships')}
                </div>
                {selectedConnections.length ? (
                  <div className="mt-2 divide-y divide-border/40 overflow-hidden rounded-2xl border border-border/50">
                    {selectedConnections.map((connection) => (
                      <div key={connection.id} className="px-3.5 py-3">
                        <div className="text-sm font-medium text-foreground">{connection.label}</div>
                        <div className="mt-0.5 text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                          {connection.relation}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-muted-foreground">{t('kg.noResults')}</p>
                )}
              </div>

              <div className="mt-auto pt-5 text-[10px] leading-5 text-muted-foreground">
                {t('kg.relationships')}
              </div>
            </div>
          ) : (
            <div className="flex h-full min-h-[300px] flex-col justify-between">
              <div>
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/70">{t('kg.help')}</div>
                <div className="mt-3 space-y-3 text-sm leading-6 text-foreground/85">
                  <GuideStep number="01" title={t('kg.title')} text={t('kg.searchToVisualise')} />
                  <GuideStep number="02" title={t('kg.searchPlaceholderDetailed')} text={t('kg.help')} />
                  <GuideStep number="03" title={t('kg.conceptDetail')} text={t('kg.relationships')} />
                </div>
              </div>

              <div className="rounded-2xl border border-ojas/15 bg-ojas/5 p-3.5">
                <div className="text-xs font-semibold text-foreground">{t('profile.journey.personalized')}</div>
                <p className="mt-1.5 text-[11px] leading-5 text-muted-foreground">
                  {t('profile.journey.savedContextDesc')}
                </p>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
};

function Metric({
  value,
  label,
  hideOnMobile = false,
}: {
  value: number;
  label: string;
  hideOnMobile?: boolean;
}) {
  return (
    <div className={`rounded-2xl border border-border/50 bg-card/50 px-3 py-2 text-center ${hideOnMobile ? 'hidden md:block' : ''}`}>
      <div className="text-base font-semibold text-foreground">{value}</div>
      <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-4 flex items-center justify-between gap-3 border-b border-border/40 pb-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-end font-medium text-foreground">{value}</span>
    </div>
  );
}

function GuideStep({ number, title, text }: { number: string; title: string; text: string }) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 text-[10px] font-semibold tracking-[0.12em] text-ojas">{number}</div>
      <div>
        <div className="font-medium text-foreground">{title}</div>
        <div className="text-xs text-muted-foreground">{text}</div>
      </div>
    </div>
  );
}

export default KGConceptMap;
