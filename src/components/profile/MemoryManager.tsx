import { useTranslation } from 'react-i18next';
import { useEffect, useRef, useState } from 'react';
import { List, Loader2, Mic, MicOff, Plus, Trash2, Brain, Sparkles, AlertCircle, Save, BookText, ZoomIn, ZoomOut, RotateCcw, Network, Maximize2, Minimize2, Search, X, Info } from 'lucide-react';
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
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';

interface SimNode extends KGNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

/** Per-type visual config: color, ring, radius */
const NODE_CONFIG: Record<string, { color: string; stroke: string; r: number; ring: number }> = {
  User:     { color: 'hsl(35 90% 55%)',   stroke: 'hsl(35 90% 35%)',   r: 28, ring: 0 },
  Teacher:  { color: 'hsl(260 70% 60%)',  stroke: 'hsl(260 70% 40%)',  r: 22, ring: 1 },
  Practice: { color: 'hsl(170 60% 45%)',  stroke: 'hsl(170 60% 28%)',  r: 20, ring: 1 },
  Concept:  { color: 'hsl(210 65% 55%)',  stroke: 'hsl(210 65% 35%)',  r: 16, ring: 2 },
  Memory:   { color: 'hsl(340 55% 55%)',  stroke: 'hsl(340 55% 35%)',  r: 13, ring: 3 },
};

const DEFAULT_NODE = { color: 'hsl(220 40% 50%)', stroke: 'hsl(220 40% 30%)', r: 15, ring: 2 };

const getCfgForNode = (node: KGNode) => {
  if (node.type === 'Memory' && node.state_category) {
    const cat = node.state_category;
    if (cat === 'Beautiful State') return { color: 'hsl(142 65% 45%)', stroke: 'hsl(142 65% 28%)', r: 14, ring: 3 };
    if (cat === 'Suffering State' || cat === 'Suffering') return { color: 'hsl(350 70% 55%)', stroke: 'hsl(350 70% 35%)', r: 14, ring: 3 };
    if (cat === 'Shrinking Self') return { color: 'hsl(25 80% 55%)', stroke: 'hsl(25 80% 35%)', r: 14, ring: 3 };
    if (cat === 'Destructive Self') return { color: 'hsl(0 75% 50%)', stroke: 'hsl(0 75% 30%)', r: 14, ring: 3 };
    if (cat === 'Inert Self') return { color: 'hsl(275 60% 55%)', stroke: 'hsl(275 60% 35%)', r: 14, ring: 3 };
  }
  return (NODE_CONFIG[node.type] ?? DEFAULT_NODE) as { color: string; stroke: string; r: number; ring: number };
};

/** Initial ring layout for coordinate seeding */
const getInitialCoords = (nodes: KGNode[], width: number, height: number) => {
  const coords = new Map<string, { x: number; y: number }>();
  const rings: Record<number, KGNode[]> = { 0: [], 1: [], 2: [], 3: [] };
  const CX = width / 2;
  const CY = height / 2;

  for (const node of nodes) {
    const ring = getCfgForNode(node).ring;
    rings[ring].push(node);
  }

  const ringRadius = [0, 95, 175, 245];

  for (const [ringIdx, group] of Object.entries(rings)) {
    const r = ringRadius[Number(ringIdx)];
    const n = group.length;
    group.forEach((node, i) => {
      if (n === 1 && r === 0) {
        coords.set(node.id, { x: CX, y: CY });
      } else {
        const angle = n > 1 ? (i / n) * Math.PI * 2 - Math.PI / 2 : 0;
        coords.set(node.id, {
          x: CX + Math.cos(angle) * r + (Math.random() - 0.5) * 10,
          y: CY + Math.sin(angle) * r + (Math.random() - 0.5) * 10,
        });
      }
    });
  }
  return coords;
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
  const { t } = useTranslation();
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

  // Voice-to-text for reflection and core memory textareas
  const reflectVoice = useSpeechRecognition({
    useSarvam: true,
    onTranscript: (text, isFinal) => {
      if (isFinal) setNewText((prev) => (prev ? `${prev} ${text}` : text).slice(0, 500));
    },
  });
  const coreVoice = useSpeechRecognition({
    useSarvam: true,
    onTranscript: (text, isFinal) => {
      if (isFinal) setCoreText((prev) => (prev ? `${prev} ${text}` : text).slice(0, 2048));
    },
  });

  // Layout & Resizability
  const [viewMode, setViewMode] = useState<'list' | 'graph'>('list');
  const [containerHeight, setContainerHeight] = useState(500);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 760, height: 500 });
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Search & Filtering
  const [searchQuery, setSearchQuery] = useState('');
  const [listSearchQuery, setListSearchQuery] = useState('');

  // Personal KG raw state
  const [kgNodes, setKgNodes] = useState<KGNode[]>([]);
  const [kgEdges, setKgEdges] = useState<KGEdge[]>([]);
  const [kgLoading, setKgLoading] = useState(false);
  const [graphView, setGraphView] = useState<'personal'>('personal');
  const [showInsightsPanel, setShowInsightsPanel] = useState(false);

  // UI Interactive States
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [hoveredNode, setHoveredNode] = useState<KGNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<KGNode | null>(null);

  // Dragging refs
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Live Force Directed Simulation
  const simNodesRef = useRef<SimNode[]>([]);
  const activeDraggedNodeRef = useRef<string | null>(null);
  const pointerStartRef = useRef<{ x: number; y: number; nodeX: number; nodeY: number } | null>(null);
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map());

  const activeHeight = isFullscreen ? (typeof window !== 'undefined' ? window.innerHeight - 150 : 700) : containerHeight;
  const CX = dimensions.width / 2;
  const CY = dimensions.height / 2;

  // Escape key handler to close fullscreen
  useEffect(() => {
    if (!isFullscreen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen]);

  // ResizeObserver for dynamic canvas sizing
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0) return;
      const { width } = entries[0].contentRect;
      setDimensions({
        width: Math.max(300, width),
        height: activeHeight,
      });
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, [containerRef.current, activeHeight]);

  // Initialize and update simulation nodes
  useEffect(() => {
    if (kgNodes.length === 0) return;

    const initialCoords = getInitialCoords(kgNodes, dimensions.width, dimensions.height);
    const existing = new Map(simNodesRef.current.map(n => [n.id, n]));

    simNodesRef.current = kgNodes.map(node => {
      const prev = existing.get(node.id);
      if (prev) {
        return { ...prev, label: node.label, type: node.type };
      }
      const coords = initialCoords.get(node.id) || { x: CX, y: CY };
      return {
        ...node,
        x: coords.x,
        y: coords.y,
        vx: 0,
        vy: 0,
      };
    });
  }, [kgNodes, dimensions.width, dimensions.height]);

  // Main Force Simulation Loop
  useEffect(() => {
    if (viewMode !== 'graph' || kgNodes.length === 0) return;

    let animationFrameId: number;

    const tick = () => {
      const nodes = simNodesRef.current;
      if (nodes.length === 0) {
        animationFrameId = requestAnimationFrame(tick);
        return;
      }

      // 1. Charge Repulsion (push nodes apart)
      for (let i = 0; i < nodes.length; i++) {
        const n1 = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const n2 = nodes[j];
          const dx = n2.x - n1.x;
          const dy = n2.y - n1.y;
          const distSq = dx * dx + dy * dy + 0.1;
          const dist = Math.sqrt(distSq);
          if (dist < 220) {
            // Stronger repulsion closer together
            const force = 180 / distSq;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            n1.vx -= fx;
            n1.vy -= fy;
            n2.vx += fx;
            n2.vy += fy;
          }
        }
      }

      // 2. Edge Link Attraction (pull connected nodes)
      for (const edge of kgEdges) {
        const s = nodes.find(n => n.id === edge.source);
        const t = nodes.find(n => n.id === edge.target);
        if (s && t) {
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.1;
          const targetDist = 95;
          const force = (dist - targetDist) * 0.025;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          s.vx += fx;
          s.vy += fy;
          t.vx -= fx;
          t.vy -= fy;
        }
      }

      // 3. Center Gravity (pull nodes back to center frame)
      for (const n of nodes) {
        const dx = CX - n.x;
        const dy = CY - n.y;
        n.vx += dx * 0.008;
        n.vy += dy * 0.008;
      }

      // 4. Update Coordinates with Friction
      const draggedId = activeDraggedNodeRef.current;
      const posMap = new Map<string, { x: number; y: number }>();

      for (const n of nodes) {
        if (n.id === draggedId) {
          n.vx = 0;
          n.vy = 0;
        } else {
          n.vx *= 0.82;
          n.vy *= 0.82;
          n.x += n.vx;
          n.y += n.vy;
        }
        posMap.set(n.id, { x: n.x, y: n.y });
      }

      setPositions(posMap);
      animationFrameId = requestAnimationFrame(tick);
    };

    animationFrameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animationFrameId);
  }, [viewMode, kgNodes, kgEdges, dimensions.width, dimensions.height]);

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
          setUnavailable(t('memory.signInToView'));
        } else {
          setUnavailable(err.message);
        }
      } else {
        setUnavailable(t('memory.couldNotLoad'));
      }
    } finally {
      setLoading(false);
    }
  };

  const loadKg = async (view: 'personal' = 'personal') => {
    setKgLoading(true);
    try {
      const kg = await memoryApi.getKnowledgeGraph(view);
      setKgNodes(kg?.nodes || []);
      setKgEdges(kg?.edges || []);
    } catch {
      // silently degrade
    } finally {
      setKgLoading(false);
    }
  };

  useEffect(() => {
    if (viewMode === 'graph') {
      loadKg(graphView);
    }
  }, [viewMode, graphView]);

  const focusNode = (node: KGNode) => {
    setSelectedNode(node);
    const pos = positions.get(node.id);
    if (pos && dimensions.width && dimensions.height) {
      setPan({
        x: dimensions.width / 2 - pos.x * zoom,
        y: dimensions.height / 2 - pos.y * zoom
      });
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Native wheel listener with passive:false so preventDefault() actually works
  // and suppresses page scroll while zooming the graph.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || viewMode !== 'graph' || kgNodes.length === 0) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      setZoom((z) => Math.min(4, Math.max(0.2, z - e.deltaY * 0.001)));
    };
    svg.addEventListener('wheel', handleWheel, { passive: false });
    return () => svg.removeEventListener('wheel', handleWheel);
  }, [viewMode, kgNodes.length]);

  const handleSaveCore = async () => {
    if (coreSaving) return;
    setCoreSaving(true);
    try {
      const saved = await memoryApi.setCore(coreText);
      setCore(saved);
      toast({ title: t('memory.coreSaved'), description: t('memory.coreSavedDesc') });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not save core memory.';
      toast({ title: t('memory.couldNotSave'), description: msg, variant: 'destructive' });
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
      toast({ title: t('memory.memorySaved'), description: t('memory.memorySavedDesc') });
      loadKg(); // Refresh KG layout to include the new memory node
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not save memory.';
      toast({ title: t('memory.couldNotSave'), description: msg, variant: 'destructive' });
    } finally {
      setAdding(false);
    }
  };

  const handleForget = async (id: string) => {
    setForgettingId(id);
    try {
      await memoryApi.forget(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      setKgNodes((prev) => prev.filter((n) => n.id !== id));
      setKgEdges((prev) => prev.filter((e) => e.source !== id && e.target !== id));
      if (selectedNode?.id === id) {
        setSelectedNode(null);
      }
      toast({ title: t('memory.forgotten'), description: t('memory.forgottenDesc') });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not forget memory.';
      toast({ title: t('memory.couldNotForget'), description: msg, variant: 'destructive' });
    } finally {
      setForgettingId(null);
    }
  };

  // Neighborhood and Connection highlighting calculations
  const connectedNodeIds = new Set<string>();
  if (hoveredNode) {
    connectedNodeIds.add(hoveredNode.id);
    kgEdges.forEach(edge => {
      if (edge.source === hoveredNode.id) connectedNodeIds.add(edge.target);
      if (edge.target === hoveredNode.id) connectedNodeIds.add(edge.source);
    });
  }

  // Matching nodes based on query
  const matchesQuery = (node: KGNode) => {
    if (!searchQuery) return true;
    return node.label.toLowerCase().includes(searchQuery.toLowerCase()) || node.type.toLowerCase().includes(searchQuery.toLowerCase());
  };

  const getRadiusForNode = (node?: KGNode) => {
    return node ? getCfgForNode(node).r : 15;
  };

  const getPathData = (
    sourceId: string,
    targetId: string,
    s: { x: number; y: number },
    t: { x: number; y: number }
  ) => {
    const sourceNode = kgNodes.find(n => n.id === sourceId);
    const targetNode = kgNodes.find(n => n.id === targetId);
    const rSource = getRadiusForNode(sourceNode);
    const rTarget = getRadiusForNode(targetNode);

    const mx = (s.x + t.x) / 2 + (t.y - s.y) * 0.08;
    const my = (s.y + t.y) / 2 - (t.x - s.x) * 0.08;

    // Vector from S to M
    const dx1 = mx - s.x;
    const dy1 = my - s.y;
    const dist1 = Math.sqrt(dx1 * dx1 + dy1 * dy1) || 0.1;
    const x1 = s.x + (dx1 / dist1) * rSource;
    const y1 = s.y + (dy1 / dist1) * rSource;

    // Vector from T to M
    const dx2 = mx - t.x;
    const dy2 = my - t.y;
    const dist2 = Math.sqrt(dx2 * dx2 + dy2 * dy2) || 0.1;
    // Offset by rTarget + 2 to align marker arrowhead touching the node border
    const x2 = t.x + (dx2 / dist2) * (rTarget + 2);
    const y2 = t.y + (dy2 / dist2) * (rTarget + 2);

    return `M${x1},${y1} Q${mx},${my} ${x2},${y2}`;
  };

  const renderGraph = () => {
    return (
      <div className="space-y-3">
        {/* Graph controls & Search bar */}
        <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5 flex-wrap">
            {/* Title Badge */}
            <div className="flex items-center gap-2 mr-3 px-3 py-1 bg-zinc-900/50 border border-zinc-800/80 rounded-full select-none pointer-events-none">
              <div className="w-1.5 h-1.5 rounded-full bg-ojas animate-pulse" />
              <span className="text-[10px] font-display font-semibold tracking-wider uppercase text-ojas-light">Consciousness Map</span>
            </div>

            {kgNodes.length > 0 && (
              <button
                onClick={() => setShowInsightsPanel(!showInsightsPanel)}
                className={`p-1.5 px-3 rounded-lg border flex items-center gap-1.5 transition-all text-[11px] font-display font-medium shadow-sm ${
                  showInsightsPanel
                    ? 'bg-ojas/20 border-ojas text-white'
                    : 'border-border bg-background text-muted-foreground hover:text-white hover:bg-muted'
                }`}
                title="Toggle Consciousness Insights"
              >
                <Sparkles className="w-3.5 h-3.5 text-ojas" />
                <span>State Insights</span>
              </button>
            )}

            <button onClick={() => setZoom((z) => Math.min(4, z + 0.25))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom in"><ZoomIn className="w-3.5 h-3.5" /></button>
            <button onClick={() => setZoom((z) => Math.max(0.2, z - 0.25))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom out"><ZoomOut className="w-3.5 h-3.5" /></button>
            <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="p-1.5 rounded border border-border hover:bg-muted" title="Reset view"><RotateCcw className="w-3.5 h-3.5" /></button>
            <button onClick={() => setIsFullscreen(!isFullscreen)} className="p-1.5 rounded border border-border hover:bg-muted" title="Toggle Fullscreen">
              {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            </button>
            <span className="ml-2 hidden lg:inline">Drag to pan · Scroll to zoom</span>
          </div>

          <div className="relative flex-1 max-w-[280px]">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search concepts or memories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-7 py-1 rounded-md border border-border bg-background text-foreground text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ojas"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* Graph SVG canvas with absolute panels overlay */}
        <div
          ref={containerRef}
          className="rounded-xl border border-border bg-zinc-950 overflow-hidden relative"
          style={{ height: activeHeight }}
        >
          {kgLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-6 h-6 text-ojas animate-spin" />
            </div>
          ) : kgNodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 text-center h-full max-w-lg mx-auto space-y-6 relative z-10 select-none">
              {/* Background ambient glowing gradient */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-ojas/10 rounded-full blur-3xl pointer-events-none" />

              <div className="relative p-6 rounded-2xl border border-zinc-800/80 bg-zinc-950/70 backdrop-blur-xl shadow-2xl space-y-5">
                <div className="mx-auto w-12 h-12 rounded-full bg-ojas/10 flex items-center justify-center border border-ojas/30">
                  <Brain className="w-6 h-6 text-ojas animate-pulse" />
                </div>
                
                <div className="space-y-2">
                  <h4 className="text-xl font-serif italic text-white tracking-tight">Your Consciousness Map</h4>
                  <p className="text-xs font-sans text-muted-foreground leading-relaxed">
                    Every dialogue, reflection, and question you share with Mukthi Guru is processed to map your states of consciousness. Start chatting to see your feelings of connection (<span className="text-emerald-400 font-medium font-display">Beautiful State</span>) and expressions of inner conflict (<span className="text-rose-400 font-medium font-display">Shrinking, Destructive, or Inert Self</span>) visualised dynamically.
                  </p>
                </div>

                <div className="space-y-3 pt-2 text-left border-t border-zinc-900/60">
                  <label className="text-[10px] font-display text-muted-foreground uppercase font-semibold tracking-wider">Share your first reflection to seed your map</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="e.g. I feel overwhelmed by comparison at work and lose focus..."
                      value={newText}
                      onChange={(e) => setNewText(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') handleAdd(); }}
                      className="flex-1 px-3 py-1.5 rounded-lg border border-zinc-800 bg-zinc-950 text-foreground text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ojas font-sans"
                    />
                    <Button
                      onClick={handleAdd}
                      disabled={adding || !newText.trim()}
                      className="px-3.5 bg-ojas text-white hover:bg-ojas/90 text-xs font-display font-semibold rounded-lg h-auto flex items-center justify-center"
                    >
                      {adding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Seed Map'}
                    </Button>
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] font-sans text-muted-foreground mt-1">
                    <Sparkles className="w-3 h-3 text-ojas" />
                    <span>Try typing a moment of gratitude or a mental challenge.</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <>
              <svg
                ref={svgRef}
                width="100%"
                height="100%"
                viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
                className="block touch-none select-none"
                style={{ cursor: dragRef.current ? 'grabbing' : activeDraggedNodeRef.current ? 'grabbing' : 'grab' }}
                onPointerDown={(e) => {
                  // Pan start
                  if (activeDraggedNodeRef.current) return;
                  (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
                  dragRef.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
                }}
                onPointerMove={(e) => {
                  // Drag node
                  if (activeDraggedNodeRef.current && pointerStartRef.current) {
                    const node = simNodesRef.current.find(n => n.id === activeDraggedNodeRef.current);
                    if (node) {
                      const dx = (e.clientX - pointerStartRef.current.x) / zoom;
                      const dy = (e.clientY - pointerStartRef.current.y) / zoom;
                      node.x = pointerStartRef.current.nodeX + dx;
                      node.y = pointerStartRef.current.nodeY + dy;
                      node.vx = 0;
                      node.vy = 0;
                    }
                    return;
                  }
                  // Pan move
                  if (!dragRef.current) return;
                  setPan({
                    x: dragRef.current.panX + e.clientX - dragRef.current.startX,
                    y: dragRef.current.panY + e.clientY - dragRef.current.startY,
                  });
                }}
                onPointerUp={() => {
                  dragRef.current = null;
                  activeDraggedNodeRef.current = null;
                  pointerStartRef.current = null;
                }}
                onPointerLeave={() => {
                  dragRef.current = null;
                  activeDraggedNodeRef.current = null;
                  pointerStartRef.current = null;
                }}
              >
                <defs>
                  <marker
                    id="arrow"
                    markerWidth="8"
                    markerHeight="8"
                    refX="6"
                    refY="3"
                    orient="auto"
                    markerUnits="userSpaceOnUse"
                  >
                    <path d="M0,0 L0,6 L6,3 z" fill="currentColor" />
                  </marker>
                </defs>

                <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
                  {/* Background grid representation */}
                  {[95, 175, 245].map((r) => (
                    <circle key={r} cx={CX} cy={CY} r={r}
                      fill="none"
                      stroke="hsl(var(--border))"
                      strokeWidth={0.5}
                      strokeDasharray="3 8"
                      opacity={0.2}
                    />
                  ))}

                  {/* Edges */}
                  {kgEdges.map((edge, i) => {
                    const s = positions.get(edge.source);
                    const t = positions.get(edge.target);
                    if (!s || !t) return null;

                    // Hover path highlighting logic
                    let isDimmed = hoveredNode !== null &&
                      hoveredNode.id !== edge.source &&
                      hoveredNode.id !== edge.target;

                    if (selectedNode) {
                      isDimmed = selectedNode.id !== edge.source &&
                        selectedNode.id !== edge.target;
                    }

                    const pathString = getPathData(edge.source, edge.target, s, t);
                    const mx = (s.x + t.x) / 2 + (t.y - s.y) * 0.08;
                    const my = (s.y + t.y) / 2 - (t.x - s.x) * 0.08;

                    return (
                      <g
                        key={`e-${i}`}
                        style={{ transition: 'opacity 0.2s, color 0.2s' }}
                        color={isDimmed ? 'hsl(var(--border) / 0.15)' : 'hsl(var(--ojas) / 0.7)'}
                      >
                        <path
                          d={pathString}
                          fill="none"
                          stroke="currentColor"
                          strokeWidth={isDimmed ? 1.0 : 1.75}
                          markerEnd="url(#arrow)"
                        />
                        {edge.label && !isDimmed && (
                          <text
                            x={mx} y={my}
                            textAnchor="middle"
                            className="fill-muted-foreground font-semibold"
                            style={{ fontSize: 7.5, pointerEvents: 'none' }}
                          >
                            {edge.label}
                          </text>
                        )}
                      </g>
                    );
                  })}

                  {/* Nodes */}
                  {simNodesRef.current.map((node) => {
                    const pos = positions.get(node.id);
                    if (!pos) return null;

                    const cfg = getCfgForNode(node);
                    const isUser = node.type === 'User';
                    const isHovered = hoveredNode?.id === node.id;
                    const isSelected = selectedNode?.id === node.id;

                    // Fade out nodes not in focused neighbor set
                    let opacity = 1.0;
                    if (hoveredNode && !connectedNodeIds.has(node.id)) {
                      opacity = 0.15;
                    } else if (selectedNode && selectedNode.id !== node.id) {
                      // Check if it's connected to selectedNode
                      const isConnected = kgEdges.some(e =>
                        (e.source === selectedNode.id && e.target === node.id) ||
                        (e.target === selectedNode.id && e.source === node.id)
                      );
                      if (!isConnected) opacity = 0.15;
                    }

                    // Search matched filter highlight
                    const searchMatch = matchesQuery(node);
                    if (!searchMatch) {
                      opacity = 0.1;
                    }

                    const displayLabel = node.label.length > 13
                      ? node.label.slice(0, 13) + '…'
                      : node.label;

                    return (
                      <g
                        key={node.id}
                        transform={`translate(${pos.x} ${pos.y})`}
                        style={{ opacity, transition: 'opacity 0.2s' }}
                        onPointerEnter={() => setHoveredNode(node)}
                        onPointerLeave={() => setHoveredNode(null)}
                        onPointerDown={(e) => {
                          e.stopPropagation();
                          e.preventDefault();
                          // Initialize node dragging
                          activeDraggedNodeRef.current = node.id;
                          pointerStartRef.current = {
                            x: e.clientX,
                            y: e.clientY,
                            nodeX: node.x,
                            nodeY: node.y,
                          };
                        }}
                        onClick={() => setSelectedNode(node)}
                      >
                        {/* Glow / Ring on hover or selection */}
                        {(isHovered || isSelected) && (
                          <circle
                            r={cfg.r + 6}
                            fill={cfg.color}
                            opacity={isSelected ? 0.35 : 0.18}
                            className={isSelected ? 'animate-pulse' : ''}
                          />
                        )}
                        <circle
                          r={cfg.r}
                          fill={cfg.color}
                          stroke={isSelected ? 'white' : (isHovered ? cfg.color : cfg.stroke)}
                          strokeWidth={isSelected ? 2.5 : 1.5}
                        />

                        {/* Text formatting inside and outside */}
                        {cfg.r >= 18 && (
                          <text
                            textAnchor="middle"
                            dy="0.3em"
                            className="font-display fill-white"
                            style={{
                              fontSize: isUser ? 10 : 8.5,
                              fontWeight: isUser ? 700 : 600,
                              pointerEvents: 'none',
                            }}
                          >
                            {isUser ? 'You' : displayLabel}
                          </text>
                        )}

                        {cfg.r < 18 && (isHovered || isSelected || searchQuery) && (
                          <text
                            textAnchor="middle"
                            y={cfg.r + 10}
                            className="font-sans fill-white/90"
                            style={{
                              fontSize: 7.5,
                              fontWeight: 500,
                              pointerEvents: 'none',
                            }}
                          >
                            {displayLabel}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </g>
              </svg>

              {/* Connected Detail Drawer Overlay (Supermemory / Understand Anything style) */}
              <AnimatePresence>
                {selectedNode && (
                  <motion.div
                    initial={{ x: '100%' }}
                    animate={{ x: 0 }}
                    exit={{ x: '100%' }}
                    transition={{ type: 'spring', damping: 22, stiffness: 120 }}
                    className="absolute right-0 top-0 h-full w-80 sm:w-96 bg-zinc-950/85 border-l border-zinc-800/80 backdrop-blur-lg p-5 shadow-[-10px_0_35px_-5px_rgba(0,0,0,0.6)] overflow-y-auto flex flex-col z-20"
                  >
                    {/* Dynamic top gradient line matching node type */}
                    <div
                      className="absolute top-0 left-0 right-0 h-1.5"
                      style={{
                        background: `linear-gradient(90deg, ${getCfgForNode(selectedNode).color}, transparent)`,
                      }}
                    />

                    <div className="flex items-start justify-between border-b border-zinc-800/60 pb-3 mb-4 mt-2">
                      <div>
                        <Badge
                          className="mb-1.5 text-[9px] uppercase tracking-wider font-semibold"
                          style={{ background: getCfgForNode(selectedNode).color }}
                        >
                          {selectedNode.type}
                        </Badge>
                        <h4 className="text-base font-display font-bold text-white tracking-tight truncate max-w-[200px] sm:max-w-[260px]">
                          {selectedNode.type === 'User' ? 'Your Memory Profile' : selectedNode.label}
                        </h4>
                      </div>
                      <button
                        onClick={() => setSelectedNode(null)}
                        className="text-muted-foreground hover:text-white hover:bg-zinc-900 p-1.5 rounded-lg transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>

                    <div className="flex-1 space-y-4 text-xs">
                      {/* Node attributes */}
                      {selectedNode.type === 'Memory' ? (
                        <div className="space-y-1.5 bg-zinc-900/40 p-4 rounded-xl border border-white/5 relative overflow-hidden group">
                          <div className="absolute -top-1 -right-1 text-white/5 font-serif text-6xl pointer-events-none select-none group-hover:text-white/10 transition-colors">“</div>
                          {selectedNode.state_category && (
                            <div className="flex items-center gap-1.5 mb-1">
                              <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider">State Category:</span>
                              <Badge className="text-[8px] uppercase tracking-wide px-1.5 py-0" style={{ background: getCfgForNode(selectedNode).color }}>
                                {selectedNode.state_category}
                              </Badge>
                            </div>
                          )}
                          <p className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider">Memory Content</p>
                          <p className="text-foreground leading-relaxed italic text-sm font-serif pr-4">"{selectedNode.content || selectedNode.label}"</p>
                        </div>
                      ) : (
                        <div className="space-y-1 bg-zinc-900/40 p-3.5 rounded-xl border border-white/5">
                          <p className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider">Entity Name</p>
                          <p className="text-foreground leading-relaxed text-sm font-medium">{selectedNode.label}</p>
                        </div>
                      )}

                      {/* Connections section */}
                      <div className="space-y-2">
                        <p className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider flex items-center gap-1">
                          <Network className="w-3 h-3 text-ojas" /> Connections
                        </p>
                        {kgEdges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).length === 0 ? (
                          <p className="text-muted-foreground italic pl-1">No direct connections.</p>
                        ) : (
                          <div className="space-y-2">
                            {kgEdges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).map((e, idx) => {
                              const neighborId = e.source === selectedNode.id ? e.target : e.source;
                              const neighbor = kgNodes.find(n => n.id === neighborId);
                              if (!neighbor) return null;
                              return (
                                <button
                                  key={idx}
                                  onClick={() => setSelectedNode(neighbor)}
                                  className="w-full text-left p-2.5 rounded-lg border border-zinc-800/60 bg-zinc-900/20 hover:bg-zinc-900 hover:border-zinc-700/80 flex items-center justify-between transition-all group hover:scale-[1.01]"
                                >
                                  <span className="truncate text-foreground font-medium max-w-[180px] sm:max-w-[220px] group-hover:text-white transition-colors">
                                    {neighbor.label}
                                  </span>
                                  <Badge
                                    className="scale-75 origin-right uppercase text-[8px]"
                                    style={{ background: getCfgForNode(neighbor).color }}
                                  >
                                    {neighbor.type}
                                  </Badge>
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Actions Panel */}
                    {selectedNode.type === 'Memory' && (
                      <div className="border-t border-border pt-3 mt-3">
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button variant="destructive" size="sm" className="w-full flex items-center justify-center gap-1.5 text-xs">
                              <Trash2 className="w-3.5 h-3.5" /> Release Memory
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Forget this memory?</AlertDialogTitle>
                              <AlertDialogDescription>
                                "{selectedNode.label}"
                                <br />
                                <br />
                                The guru will release this node from your graph.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Keep</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleForget(selectedNode.id)}>
                                Forget
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Consciousness Insights Sidebar */}
              <AnimatePresence>
                {showInsightsPanel && (
                  <motion.div
                    initial={{ x: '-100%' }}
                    animate={{ x: 0 }}
                    exit={{ x: '-100%' }}
                    transition={{ type: 'spring', damping: 22, stiffness: 120 }}
                    className="absolute left-0 top-0 h-full w-64 bg-zinc-950/90 border-r border-zinc-800/80 backdrop-blur-lg p-4 shadow-[10px_0_35px_-5px_rgba(0,0,0,0.6)] overflow-y-auto flex flex-col z-20"
                  >
                    <div className="flex items-center justify-between border-b border-zinc-800/60 pb-2.5 mb-3 font-display">
                      <div className="flex items-center gap-1.5 text-white">
                        <Sparkles className="w-3.5 h-3.5 text-ojas" />
                        <span className="text-[10px] font-bold uppercase tracking-wider">Consciousness States</span>
                      </div>
                      <button
                        onClick={() => setShowInsightsPanel(false)}
                        className="text-muted-foreground hover:text-white p-1 rounded hover:bg-zinc-900"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="space-y-4 text-[11px] text-muted-foreground select-none">
                      {/* Summary statistic */}
                      <div className="bg-zinc-900/30 p-2.5 rounded-lg border border-white/5 space-y-1">
                        <div className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider">Mapped Reflections</div>
                        <div className="text-sm font-bold text-white font-serif">
                          {kgNodes.filter(n => n.type === 'Memory').length} total
                        </div>
                      </div>

                      {/* Grouped state counts */}
                      <div className="space-y-2">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider">States Identified</span>
                        
                        {(() => {
                          const stateGroups = ['Beautiful State', 'Suffering State', 'Shrinking Self', 'Destructive Self', 'Inert Self'];
                          const memories = kgNodes.filter(n => n.type === 'Memory');
                          
                          return stateGroups.map(state => {
                            const matchingNodes = memories.filter(n => n.state_category === state);
                            if (matchingNodes.length === 0) return null;
                            
                            return (
                              <div key={state} className="space-y-1 bg-zinc-950/40 p-2 rounded-lg border border-zinc-900">
                                <div className="flex items-center justify-between">
                                  <span className="font-semibold text-white">{state}</span>
                                  <Badge className="text-[8px] scale-75 origin-right px-1.5 py-0" style={{ background: getCfgForNode({ type: 'Memory', state_category: state } as any).color }}>
                                    {matchingNodes.length}
                                  </Badge>
                                </div>
                                <div className="space-y-1 pl-1.5 border-l border-zinc-800 mt-1">
                                  {matchingNodes.map(node => (
                                    <button
                                      key={node.id}
                                      onClick={() => focusNode(node)}
                                      className="w-full text-left text-muted-foreground hover:text-white truncate block py-0.5"
                                      title={node.label}
                                    >
                                      • {node.label}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            );
                          });
                        })()}
                      </div>

                      {/* Associated teachings */}
                      <div className="space-y-2">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider">Top Concepts Mapped</span>
                        <div className="flex flex-wrap gap-1">
                          {kgNodes
                            .filter(n => n.type === 'Concept' && !['Beautiful State', 'Suffering State', 'Shrinking Self', 'Destructive Self', 'Inert Self'].includes(n.label))
                            .map(concept => {
                              const connectionCount = kgEdges.filter(
                                e => (e.source === concept.id || e.target === concept.id)
                              ).length;
                              if (connectionCount === 0) return null;

                              return (
                                <button
                                  key={concept.id}
                                  onClick={() => focusNode(concept)}
                                  className="px-2 py-0.5 rounded-full border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-900 hover:border-zinc-700 text-muted-foreground hover:text-white text-[10px] flex items-center gap-1 transition-all"
                                >
                                  <span>{concept.label}</span>
                                  <span className="text-[8px] text-muted-foreground">({connectionCount})</span>
                                </button>
                              );
                            })}
                        </div>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Legend overlay */}
              <div className="absolute bottom-3 left-3 bg-zinc-900/60 backdrop-blur-sm border border-border/40 px-2.5 py-1 rounded-lg flex gap-3 flex-wrap max-w-[90%] select-none pointer-events-none font-display">
                <div className="flex items-center gap-1">
                  <div className="rounded-full w-2 h-2" style={{ background: 'hsl(142 65% 45%)' }} />
                  <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Beautiful State</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="rounded-full w-2 h-2" style={{ background: 'hsl(350 70% 55%)' }} />
                  <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Suffering State</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="rounded-full w-2 h-2" style={{ background: 'hsl(25 80% 55%)' }} />
                  <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Shrinking Self</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="rounded-full w-2 h-2" style={{ background: 'hsl(0 75% 50%)' }} />
                  <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Destructive Self</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="rounded-full w-2 h-2" style={{ background: 'hsl(275 60% 55%)' }} />
                  <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Inert Self</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="rounded-full w-2 h-2" style={{ background: 'hsl(340 55% 55%)' }} />
                  <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Neutral</span>
                </div>
              </div>
            </>
          )}

          {/* Vertical resizer drag handle (Only visible in normal card mode) */}
          {!isFullscreen && (
            <div
              className="absolute bottom-0 left-0 w-full h-1.5 bg-border hover:bg-ojas/50 cursor-ns-resize transition-all flex items-center justify-center"
              onPointerDown={(e) => {
                e.preventDefault();
                const startY = e.clientY;
                const startHeight = containerHeight;
                const onPointerMove = (moveEvent: PointerEvent) => {
                  const newHeight = Math.max(350, Math.min(900, startHeight + (moveEvent.clientY - startY)));
                  setContainerHeight(newHeight);
                };
                const onPointerUp = () => {
                  window.removeEventListener('pointermove', onPointerMove);
                  window.removeEventListener('pointerup', onPointerUp);
                };
                window.addEventListener('pointermove', onPointerMove);
                window.addEventListener('pointerup', onPointerUp);
              }}
            />
          )}
        </div>
      </div>
    );
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
            <Brain className="w-5 h-5 text-ojas" /> {t('memory.memory')}
          </CardTitle>
          <CardDescription>{t('memory.memoryDesc')}</CardDescription>
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

  const filteredMemories = memories.filter((m) =>
    m.content.toLowerCase().includes(listSearchQuery.toLowerCase())
  );

  return (
    <div className={`space-y-6 ${isFullscreen ? 'fixed inset-0 z-50 bg-zinc-950/98 overflow-y-auto p-6 md:p-10' : ''}`}>
      {/* Floating close button in fullscreen */}
      {isFullscreen && (
        <button
          onClick={() => setIsFullscreen(false)}
          className="fixed top-6 right-6 z-50 p-3 rounded-full border border-white/10 bg-zinc-900/60 text-muted-foreground hover:text-white hover:border-white/20 transition-all hover:scale-105 backdrop-blur-md shadow-xl group"
          title="Exit Fullscreen (Esc)"
        >
          <X className="w-5 h-5 transition-transform group-hover:rotate-90 duration-300" />
        </button>
      )}

      {/* ── Statistics Bento Dashboard ─────────────────────────────────── */}
      {!isFullscreen && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="bg-zinc-900/40 border-zinc-800/80 backdrop-blur-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-ojas/10 rounded-lg text-ojas"><Brain className="w-4 h-4" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statMemories')}</p>
                <p className="text-lg font-bold text-white mt-0.5">{memories.length}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/40 border-zinc-800/80 backdrop-blur-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-prana/10 rounded-lg text-prana"><Sparkles className="w-4 h-4" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statCoreStatus')}</p>
                <p className="text-xs font-bold text-white mt-1">{coreText.trim() ? t('memory.active') : t('memory.unset')}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/40 border-zinc-800/80 backdrop-blur-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-blue-500/10 rounded-lg text-blue-400"><Network className="w-4 h-4" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statKgNodes')}</p>
                <p className="text-lg font-bold text-white mt-0.5">{kgNodes.length}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/40 border-zinc-800/80 backdrop-blur-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-emerald-500/10 rounded-lg text-emerald-400"><BookText className="w-4 h-4" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statReflections')}</p>
                <p className="text-lg font-bold text-white mt-0.5">{summaries.length}</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Core Memory Editor ─────────────────────────────────────────── */}
      {!isFullscreen && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-ojas" /> {t('memory.coreMemory')}
            </CardTitle>
            <CardDescription>
              {t('memory.coreMemoryDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={coreText}
              onChange={(e) => setCoreText(e.target.value)}
              placeholder={t('memory.corePlaceholder')}
              rows={4}
              maxLength={2048}
              disabled={coreSaving}
            />
            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => coreVoice.isListening ? coreVoice.stopListening() : void coreVoice.startListening()}
                disabled={!coreVoice.isSupported || coreSaving}
                aria-label={coreVoice.isListening ? 'Stop voice input' : 'Dictate core memory'}
                className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-ojas disabled:opacity-40 py-1"
              >
                {coreVoice.isListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                {coreVoice.isListening ? 'Listening…' : 'Dictate'}
              </button>
              <div className="flex items-center gap-2">
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
                  {t('common.save')}
                </Button>
              </div>
            </div>
            {core?.updated_at && (
              <p className="text-xs text-muted-foreground">{t('memory.lastSaved', { date: formatDate(core.updated_at) })}</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Episodic Memories ──────────────────────────────────────────── */}
      <Card className={isFullscreen ? 'border-none bg-transparent shadow-none' : ''}>
        <CardHeader className={isFullscreen ? 'px-0 pt-0' : ''}>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2 font-display font-semibold tracking-tight text-white">
              <Brain className="w-5 h-5 text-ojas" /> {isFullscreen ? t('memory.consciousnessMap') : t('memory.memories')}
              <Badge variant="secondary" className="ml-2 font-display">
                {memories.length}
              </Badge>
            </CardTitle>
            <div className="flex gap-1">
              {!isFullscreen && (
                <Button
                  variant={viewMode === 'list' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setViewMode('list')}
                  className="h-8 px-2 font-display"
                  title={t('memory.listView')}
                >
                  <List className="w-4 h-4" />
                </Button>
              )}
              <Button
                variant={viewMode === 'graph' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('graph')}
                className="h-8 px-2 font-display"
                title={t('memory.graphView')}
              >
                <Network className="w-4 h-4" />
              </Button>
            </div>
          </div>
          <CardDescription className="font-sans text-xs">
            {isFullscreen
              ? t('memory.fullscreenDesc')
              : t('memory.graphDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className={isFullscreen ? 'px-0 space-y-6' : 'space-y-6'}>
          {!isFullscreen && (
            <div className="space-y-2">
              <Textarea
                value={newText}
                onChange={(e) => setNewText(e.target.value)}
                placeholder={t('memory.reflectPlaceholder')}
                rows={2}
                maxLength={500}
                disabled={adding}
              />
              <div className="flex justify-between items-center">
                <button
                  type="button"
                  onClick={() => reflectVoice.isListening ? reflectVoice.stopListening() : void reflectVoice.startListening()}
                  disabled={!reflectVoice.isSupported || adding}
                  aria-label={reflectVoice.isListening ? 'Stop voice input' : 'Dictate memory'}
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-ojas disabled:opacity-40"
                >
                  {reflectVoice.isListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                  {reflectVoice.isListening ? 'Listening…' : 'Dictate'}
                </button>
                <div className="flex items-center gap-2">
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
                    {t('memory.saveMemory')}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {viewMode === 'graph' ? (
            renderGraph()
          ) : (
            <div className="space-y-4">
              {/* Memories List Search */}
              {memories.length > 0 && (
                <div className="relative w-full max-w-[320px]">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder={t('memory.searchPlaceholder')}
                    value={listSearchQuery}
                    onChange={(e) => setListSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-7 py-1.5 rounded-md border border-zinc-800 bg-zinc-950 text-foreground text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ojas"
                  />
                  {listSearchQuery && (
                    <button
                      onClick={() => setListSearchQuery('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )}

              {filteredMemories.length === 0 ? (
                <div className="text-center py-8 space-y-2">
                  <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                    <Brain className="w-6 h-6" />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {listSearchQuery ? t('memory.noMatchFound') : t('memory.noMemories')}
                  </p>
                </div>
              ) : (
                <ul className="space-y-2">
                  <AnimatePresence initial={false}>
                    {filteredMemories.map((m) => (
                      <motion.li
                        key={m.id}
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, height: 0 }}
                        className="flex gap-3 p-3 rounded-lg bg-ojas/5 border border-ojas/10 items-start"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-foreground/90 leading-relaxed font-serif">
                            "{m.content}"
                          </p>
                          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                            <span className="text-xs text-muted-foreground">
                              {formatDate(m.created_at)}
                            </span>
                            {m.source === 'explicit' ? (
                              <Badge variant="outline" className="text-xs bg-zinc-900 border-zinc-800">
                                {t('memory.youAdded')}
                              </Badge>
                            ) : (
                              <Badge variant="secondary" className="text-xs bg-zinc-800/50">
                                {t('memory.autoExtracted')}
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
                              aria-label={t('memory.forgetAria')}
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
                              <AlertDialogTitle>{t('memory.forgetTitle')}</AlertDialogTitle>
                              <AlertDialogDescription>
                                "{m.content}"
                                <br />
                                <br />
                                {t('memory.forgetWarning')}
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>{t('common.keep')}</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleForget(m.id)}>
                                {t('memory.forgetBtn')}
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </motion.li>
                    ))}
                  </AnimatePresence>
                </ul>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Session Summaries ──────────────────────────────────────────── */}
      {summaries.length > 0 && !isFullscreen && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <BookText className="w-5 h-5 text-ojas" /> {t('memory.sessionReflections')}
              <Badge variant="secondary" className="ml-2">{summaries.length}</Badge>
            </CardTitle>
            <CardDescription>
              {t('memory.sessionReflectionsDesc')}
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
