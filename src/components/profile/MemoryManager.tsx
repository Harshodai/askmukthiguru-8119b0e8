import { useEffect, useRef, useState } from 'react';
import { List, Loader2, Plus, Trash2, Brain, Sparkles, AlertCircle, Save, BookText, MessagesSquare, ZoomIn, ZoomOut, RotateCcw, Network } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import {
  memoryApi,
  MemoryApiError,
  type CoreMemory,
  type GuruMemory,
  type SessionSummary,
  type ConversationContinuity,
  type KGNode,
  type KGEdge,
} from '@/lib/memoryApi';

const WIDTH = 760;
const HEIGHT = 500;
const CX = WIDTH / 2;
const CY = HEIGHT / 2;

/** Per-type visual config: color, ring, radius */
const NODE_CONFIG: Record<string, { color: string; stroke: string; r: number; ring: number }> = {
  User:     { color: 'hsl(35 90% 55%)',   stroke: 'hsl(35 90% 35%)',   r: 30, ring: 0 },
  Teacher:  { color: 'hsl(260 70% 60%)',  stroke: 'hsl(260 70% 40%)',  r: 22, ring: 1 },
  Practice: { color: 'hsl(170 60% 45%)',  stroke: 'hsl(170 60% 28%)',  r: 20, ring: 1 },
  Concept:  { color: 'hsl(210 65% 55%)',  stroke: 'hsl(210 65% 35%)',  r: 18, ring: 2 },
  Memory:   { color: 'hsl(340 55% 55%)',  stroke: 'hsl(340 55% 35%)',  r: 14, ring: 3 },
};

const DEFAULT_NODE = { color: 'hsl(220 40% 50%)', stroke: 'hsl(220 40% 30%)', r: 16, ring: 2 };

/** Multi-ring layout: User at center, type-grouped rings outward. */
const layoutNodes = (nodes: KGNode[]) => {
  const map = new Map<string, { x: number; y: number }>();

  // Sort nodes into rings by type
  const rings: Record<number, KGNode[]> = { 0: [], 1: [], 2: [], 3: [] };
  for (const node of nodes) {
    const ring = (NODE_CONFIG[node.type] ?? DEFAULT_NODE).ring;
    rings[ring].push(node);
  }

  // Ring radii — spaced so node circles don't touch
  const ringRadius = [0, 110, 195, 270];

  for (const [ringIdx, group] of Object.entries(rings)) {
    const r = ringRadius[Number(ringIdx)];
    const n = group.length;
    group.forEach((node, i) => {
      if (n === 1 && r === 0) {
        map.set(node.id, { x: CX, y: CY });
      } else {
        const angle = n > 1 ? (i / n) * Math.PI * 2 - Math.PI / 2 : 0;
        map.set(node.id, {
          x: CX + Math.cos(angle) * r,
          y: CY + Math.sin(angle) * r,
        });
      }
    });
  }

  return map;
};

const formatDate = (iso: string): string => {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
};

export const MemoryManager = () => {
  const { toast } = useToast();
  const [memories, setMemories] = useState<GuruMemory[]>([]);
  const [core, setCore] = useState<CoreMemory | null>(null);
  const [coreText, setCoreText] = useState('');
  const [coreSaving, setCoreSaving] = useState(false);
  const [summaries, setSummaries] = useState<SessionSummary[]>([]);
  const [conversations, setConversations] = useState<ConversationContinuity[]>([]);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [newText, setNewText] = useState('');
  const [adding, setAdding] = useState(false);
  const [forgettingId, setForgettingId] = useState<string | null>(null);

  // Personal KG state
  const [viewMode, setViewMode] = useState<'list' | 'graph'>('list');
  const [kgNodes, setKgNodes] = useState<KGNode[]>([]);
  const [kgEdges, setKgEdges] = useState<KGEdge[]>([]);
  const [kgLoading, setKgLoading] = useState(false);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const [hoveredNode, setHoveredNode] = useState<KGNode | null>(null);
  const positions = layoutNodes(kgNodes);

  const refresh = async () => {
    setLoading(true);
    setUnavailable(null);
    try {
      const [list, coreData, summariesData, conversationsData] = await Promise.all([
        memoryApi.list(1, 100),
        memoryApi.getCore(),
        memoryApi.getSummaries(10),
        memoryApi.getConversations(5),
      ]);
      setMemories(list.memories);
      setCore(coreData);
      setCoreText(coreData?.content ?? '');
      setSummaries(summariesData);
      setConversations(conversationsData);
    } catch (err) {
      if (err instanceof MemoryApiError) {
        if (err.code === 'unauthorized') {
          setUnavailable('Sign in to view your memories.');
        } else {
          setUnavailable(err.message);
        }
      } else {
        setUnavailable('Could not load memories.');
      }
    } finally {
      setLoading(false);
    }
  };

  const loadKg = async () => {
    setKgLoading(true);
    try {
      const kg = await memoryApi.getKnowledgeGraph();
      setKgNodes(kg.nodes);
      setKgEdges(kg.edges);
    } catch {
      // silently degrade
    } finally {
      setKgLoading(false);
    }
  };

  useEffect(() => {
    if (viewMode === 'graph' && kgNodes.length === 0 && !kgLoading) {
      loadKg();
    }
  }, [viewMode]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSaveCore = async () => {
    if (coreSaving) return;
    setCoreSaving(true);
    try {
      const saved = await memoryApi.setCore(coreText);
      setCore(saved);
      toast({ title: 'Core memory saved', description: 'The guru will always carry this with you.' });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not save core memory.';
      toast({ title: 'Could not save', description: msg, variant: 'destructive' });
    } finally {
      setCoreSaving(false);
    }
  };

  const handleAdd = async () => {
    if (!newText.trim() || adding) return;
    setAdding(true);
    try {
      const created = await memoryApi.add(newText);
      setMemories((prev) => [created, ...prev]);
      setNewText('');
      toast({ title: 'Memory saved', description: 'The guru will remember this.' });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not save memory.';
      toast({ title: 'Could not save', description: msg, variant: 'destructive' });
    } finally {
      setAdding(false);
    }
  };

  const handleForget = async (id: string) => {
    setForgettingId(id);
    try {
      await memoryApi.forget(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      toast({ title: 'Forgotten', description: 'This memory has been released.' });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not forget memory.';
      toast({ title: 'Could not forget', description: msg, variant: 'destructive' });
    } finally {
      setForgettingId(null);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="py-12 flex justify-center">
          <Loader2 className="w-6 h-6 text-ojas animate-spin" />
        </CardContent>
      </Card>
    );
  }

  if (unavailable) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Brain className="w-5 h-5 text-ojas" /> Memory
          </CardTitle>
          <CardDescription>What the guru remembers about you.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-3 p-4 rounded-lg bg-muted/40 border border-border">
            <AlertCircle className="w-5 h-5 text-muted-foreground shrink-0" />
            <p className="text-sm text-muted-foreground">{unavailable}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Core Memory Editor ─────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-ojas" /> Core memory
          </CardTitle>
          <CardDescription>
            Stable facts about you — always present in the guru's awareness.
            Use this for your name, practice level, life context, key themes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={coreText}
            onChange={(e) => setCoreText(e.target.value)}
            placeholder="e.g. I'm a software engineer in Bengaluru, daily meditator for 3 years, exploring Oneness teachings…"
            rows={4}
            maxLength={2048}
            disabled={coreSaving}
          />
          <div className="flex justify-between items-center">
            <span className="text-xs text-muted-foreground">{coreText.length}/2048</span>
            <Button
              size="sm"
              onClick={handleSaveCore}
              disabled={coreSaving}
            >
              {coreSaving ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Save className="w-4 h-4 mr-2" />
              )}
              Save
            </Button>
          </div>
          {core?.updated_at && (
            <p className="text-xs text-muted-foreground">Last saved {formatDate(core.updated_at)}</p>
          )}
        </CardContent>
      </Card>

      {/* ── Episodic Memories ──────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <Brain className="w-5 h-5 text-ojas" /> Memories
              <Badge variant="secondary" className="ml-2">
                {memories.length}
              </Badge>
            </CardTitle>
            <div className="flex gap-1">
              <Button
                variant={viewMode === 'list' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('list')}
                className="h-8 px-2"
                title="List view"
              >
                <List className="w-4 h-4" />
              </Button>
              <Button
                variant={viewMode === 'graph' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('graph')}
                className="h-8 px-2"
                title="Graph view"
              >
                <Network className="w-4 h-4" />
              </Button>
            </div>
          </div>
          <CardDescription>
            Add a fact you'd like remembered, or release one that no longer fits.
            The guru also auto-extracts memories from your conversations.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Textarea
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              placeholder="e.g. I practice every morning before sunrise."
              rows={2}
              maxLength={500}
              disabled={adding}
            />
            <div className="flex justify-between items-center">
              <span className="text-xs text-muted-foreground">
                {newText.length}/500
              </span>
              <Button
                size="sm"
                onClick={handleAdd}
                disabled={!newText.trim() || adding}
              >
                {adding ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Plus className="w-4 h-4 mr-2" />
                )}
                Save memory
              </Button>
            </div>
          </div>

          {viewMode === 'graph' ? (
            <div className="space-y-3">
              {/* Graph controls */}
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <button onClick={() => setZoom((z) => Math.min(3, z + 0.25))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom in"><ZoomIn className="w-3.5 h-3.5" /></button>
                <button onClick={() => setZoom((z) => Math.max(0.3, z - 0.25))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom out"><ZoomOut className="w-3.5 h-3.5" /></button>
                <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="p-1.5 rounded border border-border hover:bg-muted" title="Reset view"><RotateCcw className="w-3.5 h-3.5" /></button>
                <span className="ml-1">Drag to pan · scroll to zoom</span>
                {kgNodes.length > 0 && (
                  <span className="ml-auto">{kgNodes.length} items · {kgEdges.length} connections</span>
                )}
              </div>

              {/* Graph SVG */}
              <div className="rounded-xl border border-border bg-card overflow-hidden relative">
                {kgLoading ? (
                  <div className="flex items-center justify-center" style={{ height: HEIGHT }}>
                    <Loader2 className="w-6 h-6 text-ojas animate-spin" />
                  </div>
                ) : kgNodes.length === 0 ? (
                  <div className="flex flex-col items-center justify-center gap-3" style={{ height: HEIGHT }}>
                    <Network className="w-10 h-10 text-muted-foreground/30" />
                    <p className="text-sm text-muted-foreground text-center max-w-xs">
                      No knowledge graph yet. Chat with the guru to build your personal ontology.
                    </p>
                  </div>
                ) : (
                  <>
                    <svg
                      ref={svgRef}
                      width="100%"
                      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                      className="block touch-none select-none"
                      style={{ height: HEIGHT, cursor: dragRef.current ? 'grabbing' : 'grab' }}
                      onWheel={(e) => { e.preventDefault(); setZoom((z) => Math.min(3, Math.max(0.3, z - e.deltaY * 0.001))); }}
                      onPointerDown={(e) => {
                        (e.target as Element).setPointerCapture?.(e.pointerId);
                        dragRef.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
                      }}
                      onPointerMove={(e) => {
                        if (!dragRef.current) return;
                        setPan({ x: dragRef.current.panX + e.clientX - dragRef.current.startX, y: dragRef.current.panY + e.clientY - dragRef.current.startY });
                      }}
                      onPointerUp={() => { dragRef.current = null; }}
                      onPointerLeave={() => { dragRef.current = null; }}
                    >
                      <defs>
                        {/* Subtle radial gradient background */}
                        <radialGradient id="kg-bg" cx="50%" cy="50%" r="50%">
                          <stop offset="0%" stopColor="hsl(var(--card))" stopOpacity="0" />
                          <stop offset="100%" stopColor="hsl(var(--border))" stopOpacity="0.15" />
                        </radialGradient>
                        <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                          <path d="M0,0 L0,6 L6,3 z" fill="hsl(var(--border))" />
                        </marker>
                      </defs>

                      <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
                        {/* Background ring guides */}
                        {[110, 195, 270].map((r) => (
                          <circle key={r} cx={CX} cy={CY} r={r}
                            fill="none"
                            stroke="hsl(var(--border))"
                            strokeWidth={0.5}
                            strokeDasharray="4 6"
                            opacity={0.4}
                          />
                        ))}

                        {/* Edges — quadratic bezier for a cleaner arc */}
                        {kgEdges.map((edge, i) => {
                          const s = positions.get(edge.source);
                          const t = positions.get(edge.target);
                          if (!s || !t) return null;
                          // Slight curve via midpoint offset
                          const mx = (s.x + t.x) / 2 + (t.y - s.y) * 0.12;
                          const my = (s.y + t.y) / 2 - (t.x - s.x) * 0.12;
                          return (
                            <g key={`e-${i}`}>
                              <path
                                d={`M${s.x},${s.y} Q${mx},${my} ${t.x},${t.y}`}
                                fill="none"
                                stroke="hsl(var(--border))"
                                strokeWidth={1.2}
                                strokeOpacity={0.6}
                                markerEnd="url(#arrow)"
                              />
                              {edge.label && (
                                <text
                                  x={mx} y={my}
                                  textAnchor="middle"
                                  className="fill-muted-foreground"
                                  style={{ fontSize: 7, pointerEvents: 'none', opacity: 0.7 }}
                                >
                                  {edge.label}
                                </text>
                              )}
                            </g>
                          );
                        })}

                        {/* Nodes */}
                        {kgNodes.map((node) => {
                          const pos = positions.get(node.id);
                          if (!pos) return null;
                          const cfg = NODE_CONFIG[node.type] ?? DEFAULT_NODE;
                          const isUser = node.type === 'User';
                          const isHovered = hoveredNode?.id === node.id;
                          const displayLabel = node.label.length > 13
                            ? node.label.slice(0, 13) + '…'
                            : node.label;

                          return (
                            <g
                              key={node.id}
                              transform={`translate(${pos.x} ${pos.y})`}
                              style={{ cursor: 'pointer' }}
                              onPointerEnter={() => setHoveredNode(node)}
                              onPointerLeave={() => setHoveredNode(null)}
                            >
                              {/* Glow ring on hover */}
                              {isHovered && (
                                <circle
                                  r={cfg.r + 5}
                                  fill={cfg.color}
                                  opacity={0.2}
                                />
                              )}
                              <circle
                                r={cfg.r}
                                fill={cfg.color}
                                stroke={isHovered ? cfg.color : cfg.stroke}
                                strokeWidth={isHovered ? 2.5 : 1.5}
                              />
                              {/* Label inside node for larger nodes */}
                              {cfg.r >= 18 && (
                                <text
                                  textAnchor="middle"
                                  dy="0.35em"
                                  style={{
                                    fontSize: isUser ? 10 : 8,
                                    fontWeight: isUser ? 700 : 600,
                                    pointerEvents: 'none',
                                    fill: 'white',
                                  }}
                                >
                                  {isUser ? 'You' : displayLabel}
                                </text>
                              )}
                              {/* Label OUTSIDE circle for smaller nodes */}
                              {cfg.r < 18 && (
                                <text
                                  textAnchor="middle"
                                  y={cfg.r + 11}
                                  style={{
                                    fontSize: 7.5,
                                    fontWeight: 500,
                                    pointerEvents: 'none',
                                    fill: 'hsl(var(--foreground))',
                                    opacity: 0.85,
                                  }}
                                >
                                  {displayLabel}
                                </text>
                              )}
                              {/* Type badge below label for larger nodes */}
                              {cfg.r >= 18 && !isUser && (
                                <text
                                  textAnchor="middle"
                                  y={cfg.r + 11}
                                  style={{
                                    fontSize: 6.5,
                                    pointerEvents: 'none',
                                    fill: 'hsl(var(--muted-foreground))',
                                    opacity: 0.75,
                                  }}
                                >
                                  {node.type}
                                </text>
                              )}
                            </g>
                          );
                        })}
                      </g>
                    </svg>

                    {/* Hover tooltip */}
                    {hoveredNode && (
                      <div className="absolute bottom-3 left-3 bg-popover border border-border rounded-lg px-3 py-2 shadow-lg pointer-events-none z-10 max-w-[220px]">
                        <p className="text-xs font-semibold text-foreground truncate">{hoveredNode.label}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">{hoveredNode.type}</p>
                      </div>
                    )}

                    {/* Legend */}
                    <div className="absolute bottom-3 right-3 flex gap-3 flex-wrap justify-end">
                      {Object.entries(NODE_CONFIG).filter(([k]) => k !== 'User').map(([type, cfg]) => (
                        <div key={type} className="flex items-center gap-1.5">
                          <div
                            className="rounded-full"
                            style={{ width: 8, height: 8, background: cfg.color }}
                          />
                          <span className="text-[10px] text-muted-foreground">{type}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          ) : memories.length === 0 ? (
            <div className="text-center py-8 space-y-2">
              <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                <Brain className="w-6 h-6" />
              </div>
              <p className="text-sm text-muted-foreground">
                No memories yet. Continue your conversations and the guru will
                gradually learn what matters to you.
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              <AnimatePresence initial={false}>
                {memories.map((m) => (
                  <motion.li
                    key={m.id}
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex gap-3 p-3 rounded-lg bg-ojas/5 border border-ojas/10 items-start"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground/90 leading-relaxed">
                        {m.content}
                      </p>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <span className="text-xs text-muted-foreground">
                          {formatDate(m.created_at)}
                        </span>
                        {m.source === 'explicit' ? (
                          <Badge variant="outline" className="text-xs">
                            You added
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-xs">
                            Auto-extracted
                          </Badge>
                        )}
                      </div>
                    </div>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="shrink-0 text-muted-foreground hover:text-destructive"
                          disabled={forgettingId === m.id}
                          aria-label="Forget this memory"
                        >
                          {forgettingId === m.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Trash2 className="w-4 h-4" />
                          )}
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Forget this memory?</AlertDialogTitle>
                          <AlertDialogDescription>
                            "{m.content}"
                            <br />
                            <br />
                            The guru will no longer reference this in future
                            conversations. This cannot be undone.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Keep</AlertDialogCancel>
                          <AlertDialogAction onClick={() => handleForget(m.id)}>
                            Forget
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ── Session Summaries ──────────────────────────────────────────── */}
      {summaries.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <BookText className="w-5 h-5 text-ojas" /> Session reflections
              <Badge variant="secondary" className="ml-2">{summaries.length}</Badge>
            </CardTitle>
            <CardDescription>
              Distilled summaries the guru keeps from your past sessions.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {summaries.map((s) => (
                <li
                  key={s.id}
                  className="p-3 rounded-lg bg-prana/5 border border-prana/10"
                >
                  <p className="text-sm text-foreground/90 leading-relaxed italic">
                    "{s.summary}"
                  </p>
                  <p className="text-xs text-muted-foreground mt-2">
                    {formatDate(s.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
