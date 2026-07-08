import { useEffect, useRef, useState } from 'react';
import { List, Loader2, Plus, Trash2, Brain, Sparkles, AlertCircle, Save, BookText, ZoomIn, ZoomOut, RotateCcw, Network, Maximize2, Minimize2, Search, X, Info } from 'lucide-react';
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

/** Initial ring layout for coordinate seeding */
const getInitialCoords = (nodes: KGNode[], height: number) => {
  const coords = new Map<string, { x: number; y: number }>();
  const rings: Record<number, KGNode[]> = { 0: [], 1: [], 2: [], 3: [] };
  const CX = WIDTH / 2;
  const CY = height / 2;

  for (const node of nodes) {
    const ring = (NODE_CONFIG[node.type] ?? DEFAULT_NODE).ring;
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

  // Layout & Resizability
  const [viewMode, setViewMode] = useState<'list' | 'graph'>('list');
  const [containerHeight, setContainerHeight] = useState(500);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Search & Filtering
  const [searchQuery, setSearchQuery] = useState('');

  // Personal KG raw state
  const [kgNodes, setKgNodes] = useState<KGNode[]>([]);
  const [kgEdges, setKgEdges] = useState<KGEdge[]>([]);
  const [kgLoading, setKgLoading] = useState(false);

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
  const CX = WIDTH / 2;
  const CY = activeHeight / 2;

  // Initialize and update simulation nodes
  useEffect(() => {
    if (kgNodes.length === 0) return;

    const initialCoords = getInitialCoords(kgNodes, activeHeight);
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
  }, [kgNodes, activeHeight]);

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
  }, [viewMode, kgNodes, kgEdges, activeHeight]);

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
      loadKg(); // Refresh KG layout to include the new memory node
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
      setKgNodes((prev) => prev.filter((n) => n.id !== id));
      setKgEdges((prev) => prev.filter((e) => e.source !== id && e.target !== id));
      if (selectedNode?.id === id) {
        setSelectedNode(null);
      }
      toast({ title: 'Forgotten', description: 'This memory has been released.' });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not forget memory.';
      toast({ title: 'Could not forget', description: msg, variant: 'destructive' });
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

  const renderGraph = () => {
    return (
      <div className="space-y-3">
        {/* Graph controls & Search bar */}
        <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <button onClick={() => setZoom((z) => Math.min(4, z + 0.25))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom in"><ZoomIn className="w-3.5 h-3.5" /></button>
            <button onClick={() => setZoom((z) => Math.max(0.2, z - 0.25))} className="p-1.5 rounded border border-border hover:bg-muted" title="Zoom out"><ZoomOut className="w-3.5 h-3.5" /></button>
            <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="p-1.5 rounded border border-border hover:bg-muted" title="Reset view"><RotateCcw className="w-3.5 h-3.5" /></button>
            <button onClick={() => setIsFullscreen(!isFullscreen)} className="p-1.5 rounded border border-border hover:bg-muted ml-2" title="Toggle Fullscreen">
              {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            </button>
            <span className="ml-2 hidden sm:inline">Drag to pan · Scroll to zoom</span>
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
          className="rounded-xl border border-border bg-zinc-950 overflow-hidden relative"
          style={{ height: activeHeight }}
        >
          {kgLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-6 h-6 text-ojas animate-spin" />
            </div>
          ) : kgNodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 h-full">
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
                height="100%"
                viewBox={`0 0 ${WIDTH} ${activeHeight}`}
                className="block touch-none select-none"
                style={{ cursor: dragRef.current ? 'grabbing' : activeDraggedNodeRef.current ? 'grabbing' : 'grab' }}
                onWheel={(e) => {
                  e.preventDefault();
                  setZoom((z) => Math.min(4, Math.max(0.2, z - e.deltaY * 0.001)));
                }}
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
                  <marker id="arrow" markerWidth="6" markerHeight="6" refX="10" refY="3" orient="auto">
                    <path d="M0,0 L0,6 L6,3 z" fill="hsl(var(--border))" />
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

                    const mx = (s.x + t.x) / 2 + (t.y - s.y) * 0.08;
                    const my = (s.y + t.y) / 2 - (t.x - s.x) * 0.08;

                    return (
                      <g key={`e-${i}`} style={{ opacity: isDimmed ? 0.08 : 0.65, transition: 'opacity 0.2s' }}>
                        <path
                          d={`M${s.x},${s.y} Q${mx},${my} ${t.x},${t.y}`}
                          fill="none"
                          stroke={isDimmed ? 'hsl(var(--border))' : 'hsl(var(--ojas) / 0.45)'}
                          strokeWidth={isDimmed ? 1.0 : 1.5}
                          markerEnd="url(#arrow)"
                        />
                        {edge.label && !isDimmed && (
                          <text
                            x={mx} y={my}
                            textAnchor="middle"
                            className="fill-muted-foreground"
                            style={{ fontSize: 6.5, pointerEvents: 'none' }}
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

                    const cfg = NODE_CONFIG[node.type] ?? DEFAULT_NODE;
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
                            style={{
                              fontSize: isUser ? 10 : 8.5,
                              fontWeight: isUser ? 700 : 600,
                              pointerEvents: 'none',
                              fill: 'white',
                            }}
                          >
                            {isUser ? 'You' : displayLabel}
                          </text>
                        )}

                        {cfg.r < 18 && (
                          <text
                            textAnchor="middle"
                            y={cfg.r + 10}
                            style={{
                              fontSize: 7.5,
                              fontWeight: 500,
                              pointerEvents: 'none',
                              fill: 'white',
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
                    transition={{ type: 'spring', damping: 20 }}
                    className="absolute right-0 top-0 h-full w-72 bg-zinc-900/95 border-l border-border backdrop-blur-md p-4 shadow-2xl overflow-y-auto flex flex-col z-20"
                  >
                    <div className="flex items-start justify-between border-b border-border pb-2.5 mb-3.5">
                      <div>
                        <Badge className="mb-1 text-[10px]" style={{ background: (NODE_CONFIG[selectedNode.type] ?? DEFAULT_NODE).color }}>
                          {selectedNode.type}
                        </Badge>
                        <h4 className="text-sm font-semibold text-white truncate max-w-[200px]">
                          {selectedNode.type === 'User' ? 'Your Memory Profile' : selectedNode.label}
                        </h4>
                      </div>
                      <button onClick={() => setSelectedNode(null)} className="text-muted-foreground hover:text-white p-1 rounded-md">
                        <X className="w-4 h-4" />
                      </button>
                    </div>

                    <div className="flex-1 space-y-4 text-xs">
                      {/* Node attributes */}
                      <div className="space-y-1 bg-zinc-950/40 p-2.5 rounded-lg border border-border/40">
                        <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Node Details</p>
                        <p className="text-foreground leading-relaxed">{selectedNode.label}</p>
                      </div>

                      {/* Connections section */}
                      <div className="space-y-2">
                        <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Connections</p>
                        {kgEdges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).length === 0 ? (
                          <p className="text-muted-foreground italic">No direct connections.</p>
                        ) : (
                          <div className="space-y-1.5">
                            {kgEdges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).map((e, idx) => {
                              const neighborId = e.source === selectedNode.id ? e.target : e.source;
                              const neighbor = kgNodes.find(n => n.id === neighborId);
                              if (!neighbor) return null;
                              return (
                                <button
                                  key={idx}
                                  onClick={() => setSelectedNode(neighbor)}
                                  className="w-full text-left p-2 rounded border border-border/40 bg-zinc-950/20 hover:bg-zinc-800 flex items-center justify-between"
                                >
                                  <span className="truncate text-foreground font-medium max-w-[150px]">{neighbor.label}</span>
                                  <Badge className="scale-75 origin-right" style={{ background: (NODE_CONFIG[neighbor.type] ?? DEFAULT_NODE).color }}>
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

              {/* Legend overlay */}
              <div className="absolute bottom-3 left-3 bg-zinc-900/60 backdrop-blur-sm border border-border/40 px-2 py-1 rounded-md flex gap-2.5 flex-wrap">
                {Object.entries(NODE_CONFIG).map(([type, cfg]) => (
                  <div key={type} className="flex items-center gap-1">
                    <div className="rounded-full w-2 h-2" style={{ background: cfg.color }} />
                    <span className="text-[9px] text-muted-foreground">{type}</span>
                  </div>
                ))}
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
    <div className={`space-y-6 ${isFullscreen ? 'fixed inset-0 z-50 bg-background/98 overflow-y-auto p-6 md:p-10' : ''}`}>
      {/* ── Core Memory Editor ─────────────────────────────────────────── */}
      {!isFullscreen && (
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
      )}

      {/* ── Episodic Memories ──────────────────────────────────────────── */}
      <Card className={isFullscreen ? 'border-none bg-transparent shadow-none' : ''}>
        <CardHeader className={isFullscreen ? 'px-0 pt-0' : ''}>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <Brain className="w-5 h-5 text-ojas" /> {isFullscreen ? 'Ontology Knowledge Graph' : 'Memories'}
              <Badge variant="secondary" className="ml-2">
                {memories.length}
              </Badge>
            </CardTitle>
            <div className="flex gap-1">
              {!isFullscreen && (
                <Button
                  variant={viewMode === 'list' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setViewMode('list')}
                  className="h-8 px-2"
                  title="List view"
                >
                  <List className="w-4 h-4" />
                </Button>
              )}
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
            {isFullscreen
              ? 'Fullscreen view of your interactive personal knowledge graph. Drag nodes to move, drag background to pan, scroll to zoom.'
              : 'Add a fact you\'d like remembered, or release one that no longer fits. The guru also auto-extracts memories.'}
          </CardDescription>
        </CardHeader>
        <CardContent className={isFullscreen ? 'px-0 space-y-6' : 'space-y-6'}>
          {!isFullscreen && (
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
          )}

          {viewMode === 'graph' ? renderGraph() : memories.length === 0 ? (

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
