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

const WIDTH = 700;
const HEIGHT = 420;

/** Deterministic hue from a label string. */
const labelHue = (label: string): number => {
  let h = 0;
  for (let i = 0; i < label.length; i++) h = (h * 31 + label.charCodeAt(i)) % 360;
  return h || 210;
};

/** Simple circular layout. */
const layoutNodes = (nodes: KGNode[]) => {
  const map = new Map<string, { x: number; y: number }>();
  const n = nodes.length;
  const radius = Math.min(WIDTH, HEIGHT) / 2 - 50;
  nodes.forEach((node, i) => {
    const angle = n > 1 ? (i / n) * Math.PI * 2 - Math.PI / 2 : 0;
    map.set(node.id, {
      x: WIDTH / 2 + Math.cos(angle) * radius * 0.7,
      y: HEIGHT / 2 + Math.sin(angle) * radius * 0.7,
    });
  });
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
                <button onClick={() => setZoom((z) => Math.min(3, z + 0.2))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom in"><ZoomIn className="w-3.5 h-3.5" /></button>
                <button onClick={() => setZoom((z) => Math.max(0.3, z - 0.2))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom out"><ZoomOut className="w-3.5 h-3.5" /></button>
                <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="p-1.5 rounded border border-border hover:bg-muted" title="Reset view"><RotateCcw className="w-3.5 h-3.5" /></button>
                <span className="ml-1">Drag to pan · scroll to zoom</span>
                {kgNodes.length > 0 && (
                  <span className="ml-auto">{kgNodes.length} items · {kgEdges.length} connections</span>
                )}
              </div>

              {/* Graph SVG */}
              <div className="rounded-xl border border-border bg-card overflow-hidden">
                {kgLoading ? (
                  <div className="flex items-center justify-center" style={{ height: HEIGHT }}>
                    <Loader2 className="w-6 h-6 text-ojas animate-spin" />
                  </div>
                ) : kgNodes.length === 0 ? (
                  <div className="flex items-center justify-center" style={{ height: HEIGHT }}>
                    <p className="text-sm text-muted-foreground">No knowledge graph data available. Chat with the guru to build your personal knowledge graph.</p>
                  </div>
                ) : (
                  <svg
                    ref={svgRef}
                    width="100%"
                    viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                    className="block touch-none select-none"
                    style={{ height: HEIGHT, cursor: dragRef.current ? 'grabbing' : 'grab' }}
                    onWheel={(e) => { e.preventDefault(); setZoom((z) => Math.min(3, Math.max(0.3, z - e.deltaY * 0.0015))); }}
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
                    <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
                      {/* Edges */}
                      {kgEdges.map((e, i) => {
                        const s = positions.get(e.source);
                        const t = positions.get(e.target);
                        if (!s || !t) return null;
                        return (
                          <g key={`e-${i}`}>
                            <line x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke="hsl(var(--border))" strokeWidth={1} />
                            {e.label && (
                              <text x={(s.x + t.x) / 2} y={(s.y + t.y) / 2} textAnchor="middle" className="fill-muted-foreground" style={{ fontSize: 8, pointerEvents: 'none' }}>
                                {e.label}
                              </text>
                            )}
                          </g>
                        );
                      })}
                      {/* Nodes */}
                      {kgNodes.map((n) => {
                        const pos = positions.get(n.id);
                        if (!pos) return null;
                        const hue = labelHue(n.type);
                        const r = n.type === 'User' ? 28 : n.type === 'Memory' ? 20 : 24;
                        return (
                          <g key={n.id} transform={`translate(${pos.x} ${pos.y})`}>
                            {n.type === 'User' ? (
                              <>
                                <circle r={r} fill="hsl(35 85% 50% / 0.9)" stroke="hsl(35 85% 35%)" strokeWidth={2} />
                                <text textAnchor="middle" dy="0.35em" className="fill-background" style={{ fontSize: 11, fontWeight: 700, pointerEvents: 'none' }}>
                                  You
                                </text>
                              </>
                            ) : (
                              <>
                                <circle r={r} fill={`hsl(${hue} 55% 45% / 0.85)`} stroke={`hsl(${hue} 55% 30%)`} strokeWidth={1.5} />
                                {n.type === 'Memory' ? (
                                  <text textAnchor="middle" dy="0.35em" className="fill-foreground" style={{ fontSize: 7, pointerEvents: 'none' }}>
                                    {n.label.length > 16 ? n.label.slice(0, 16) + '…' : n.label}
                                  </text>
                                ) : (
                                  <text textAnchor="middle" dy="0.35em" className="fill-foreground" style={{ fontSize: 9, fontWeight: 500, pointerEvents: 'none' }}>
                                    {n.label.length > 14 ? n.label.slice(0, 14) + '…' : n.label}
                                  </text>
                                )}
                              </>
                            )}
                            <text textAnchor="middle" dy={`${r + 12}px`} className="fill-muted-foreground" style={{ fontSize: 7, pointerEvents: 'none' }}>
                              {n.type === 'Memory' ? 'Memory' : n.type}
                            </text>
                          </g>
                        );
                      })}
                    </g>
                  </svg>
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
