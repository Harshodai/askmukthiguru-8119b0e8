import { useState, useMemo, useEffect, type ReactNode, type MouseEvent as ReactMouseEvent } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  Position,
  MarkerType,
  Handle,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useRagFlowGraph } from "@/admin/hooks/useAdminData";
import {
  Network,
  RefreshCw,
  Activity,
  HelpCircle,
  Flame,
  Clock,
  Database,
  ArrowRight,
  Sparkles,
  ShieldCheck,
  Search,
  MessageSquare,
  AlertCircle
} from "lucide-react";
import { fmtMs } from "@/admin/lib/formatters";
import type { RagFlowGraphNode } from "@/admin/lib/api";
type RagStrategy = "standard" | "fast" | "deep" | "first_person";
type FlowNode = Node<CustomRAGNodeData>;
const isRagStrategy = (value: string): value is RagStrategy => (
  value === "standard" || value === "fast" || value === "deep" || value === "first_person"
);

// Node description library for detailed admin inspect panel
const NODE_DESCRIPTIONS: Record<string, { title: string; desc: string; category: string }> = {
  // Intake & Common Nodes
  __start__: {
    title: "Pipeline Intake",
    desc: "Entry point receiving user question and initiating safety & intent checks.",
    category: "Intent"
  },
  __end__: {
    title: "Response Output",
    desc: "Final streaming terminal delivering verified response, citations, and metadata.",
    category: "Generation"
  },
  intent_router: {
    title: "Intent Router",
    desc: "Analyzes incoming query intent, routing it to distress, casual chat, meditation, or full RAG flows.",
    category: "Intent"
  },
  handle_distress_check: {
    title: "Distress Pre-Filter",
    desc: "Parallel evaluation verifying acute distress signals before standard dispatch.",
    category: "Intent"
  },
  resolve_parallel: {
    title: "Parallel Dispatch",
    desc: "Coordinates concurrent execution branches across retrieval and specialized flows.",
    category: "Augmentation"
  },
  resolve_followup: {
    title: "Resolve Follow-up",
    desc: "Uses message history to expand pronoun references and context for multi-turn conversations.",
    category: "Intent"
  },
  decompose_query: {
    title: "Decompose Query",
    desc: "Splits complex multi-part queries into sub-questions to retrieve distinct information subsets.",
    category: "Intent"
  },
  navigate_and_hyde: {
    title: "Navigate & HyDE",
    desc: "Generates a hypothetical response (HyDE) and extracts metadata navigation filters to guide vector search.",
    category: "Retrieval"
  },
  retrieve_documents: {
    title: "Retrieve Documents",
    desc: "Performs hybrid search against Qdrant vector store and Neo4j knowledge graph.",
    category: "Retrieval"
  },
  rerank_documents: {
    title: "Rerank Documents",
    desc: "Applies cross-encoder model to re-score retrieved documents, filtering out low-relevance chunks.",
    category: "Retrieval"
  },
  grade_documents: {
    title: "Grade Documents",
    desc: "Assesses document relevance against query keywords, flagging completely irrelevant passages.",
    category: "Retrieval"
  },
  _map_docs_to_relevant: {
    title: "Document Map & Threshold",
    desc: "Extracts top candidate passages meeting minimum relevance threshold score.",
    category: "Retrieval"
  },
  enrich_context: {
    title: "Enrich Context",
    desc: "Fetches parent chunk passages, adjacent timelines, and entity definitions from graph storage.",
    category: "Augmentation"
  },
  check_context_sufficiency: {
    title: "Check Context Sufficiency",
    desc: "Evaluates whether retrieved documents provide enough factual support to answer the query.",
    category: "Augmentation"
  },
  rewrite_query: {
    title: "Rewrite Query",
    desc: "Reformulates query if context is insufficient, triggering a refined second-pass retrieval step.",
    category: "Augmentation"
  },
  context_engineer: {
    title: "Context Engineer",
    desc: "Applies Reversible Context Compression (CCR) to prune tokens while maintaining crucial information.",
    category: "Augmentation"
  },
  generate_answer: {
    title: "Generate Answer",
    desc: "Invokes core LLM with engineered context and safety system instructions.",
    category: "Generation"
  },
  reflect_on_answer: {
    title: "Reflect on Answer",
    desc: "Validates response draft against original documents to ensure absolute correctness.",
    category: "Generation"
  },
  verify_answer: {
    title: "Verify Answer",
    desc: "Performs Self-RAG verification, computing faithfulness, answer relevance, and safety scores.",
    category: "Generation"
  },
  extract_citations: {
    title: "Extract Citations",
    desc: "Validates source coordinates, discourse timestamps, and verified YouTube links.",
    category: "Generation"
  },
  explain_retrieval: {
    title: "Explain Retrieval",
    desc: "Builds user-facing citations, source listings, and relevance explanations.",
    category: "Generation"
  },
  format_final_answer: {
    title: "Format Final Answer",
    desc: "Formats Markdown headers, bullet points, audio TTS metadata, and links.",
    category: "Generation"
  },
  check_contradiction: {
    title: "Check Contradiction",
    desc: "Checks final answer against historical sessions to prevent conflicting advice.",
    category: "Generation"
  },
  first_person: {
    title: "First Person Fast-Track",
    desc: "Serves direct verbatim teacher quote and audio playback bypassing LLM generation.",
    category: "First Person"
  },
  handle_casual: {
    title: "Handle Casual Chat",
    desc: "Greets user, responds to small talk, and establishes conversational rapport without RAG retrieval.",
    category: "Fallback/Special"
  },
  handle_distress: {
    title: "Handle Distress",
    desc: "Processes distress indicators, logging critical safety events and serving safe mental health protocols.",
    category: "Fallback/Special"
  },
  handle_meditation: {
    title: "Handle Meditation Flow",
    desc: "Initiates interactive deep breathing exercises and meditation guidelines (Serene Mind).",
    category: "Fallback/Special"
  },
  handle_fallback: {
    title: "Handle Fallback",
    desc: "Serves helpful pre-configured response when errors occur or safety triggers block completion.",
    category: "Fallback/Special"
  },
  web_search: {
    title: "Web Search Node",
    desc: "Performs external internet search to fetch recent context if internal knowledge base is lacking.",
    category: "Fallback/Special"
  },

  // First-Person Serving Architecture
  fp_input: {
    title: "Seeker Query Intake",
    desc: "Entry point evaluating query semantics, teacher intent, and language preferences.",
    category: "First Person"
  },
  fp_directness_gate: {
    title: "Directness & Intent Gate",
    desc: "Verifies whether question directly asks for authentic teacher guidance (threshold >= 0.70).",
    category: "First Person"
  },
  fp_asr_resolver: {
    title: "ASR Timestamp Resolver",
    desc: "Maps transcript coordinates into exact audio file slice windows [audio_start_ms, audio_end_ms].",
    category: "First Person"
  },
  fp_ecapa_verify: {
    title: "ECAPA Acoustic Attribution",
    desc: "Verifies speaker identity using ECAPA-TDNN neural embeddings against certified voice centroids.",
    category: "First Person"
  },
  fp_rights_gate: {
    title: "B5 Rights Clearing Gate",
    desc: "Cross-checks content against audited rights register (docs/rights/CONTENT-RIGHTS.md); excludes unverified tiers.",
    category: "First Person"
  },
  fp_context_harness: {
    title: "Context Harness Assembler",
    desc: "Assembles parent discourse window using purely stored verbatim spans with zero LLM fabrication.",
    category: "First Person"
  },
  fp_schema_contract: {
    title: "B4 Serving Contract Guard",
    desc: "Enforces collection isolation, exact-cache fingerprinting, and fail-closed non-production safety.",
    category: "First Person"
  },
  fp_audio_output: {
    title: "Verbatim Audio & Citation",
    desc: "Emits verified YouTube video timestamp, audio strip playback, and authentic aphorism.",
    category: "First Person"
  }
};

// Colors matching admin console aesthetic
const CATEGORY_STYLES: Record<string, { bg: string; border: string; text: string; glow: string; badge: string }> = {
  "Intent": {
    bg: "bg-blue-500/10 dark:bg-blue-950/20",
    border: "border-blue-500/30 dark:border-blue-800/40",
    text: "text-blue-600 dark:text-blue-400",
    glow: "shadow-[0_0_15px_rgba(59,130,246,0.1)]",
    badge: "bg-blue-500/15 text-blue-600 dark:text-blue-300 border-blue-500/30"
  },
  "Retrieval": {
    bg: "bg-emerald-500/10 dark:bg-emerald-950/20",
    border: "border-emerald-500/30 dark:border-emerald-800/40",
    text: "text-emerald-600 dark:text-emerald-400",
    glow: "shadow-[0_0_15px_rgba(16,185,129,0.1)]",
    badge: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-500/30"
  },
  "Augmentation": {
    bg: "bg-amber-500/10 dark:bg-amber-950/20",
    border: "border-amber-500/30 dark:border-amber-800/40",
    text: "text-amber-600 dark:text-amber-400",
    glow: "shadow-[0_0_15px_rgba(245,158,11,0.1)]",
    badge: "bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-500/30"
  },
  "Generation": {
    bg: "bg-purple-500/10 dark:bg-purple-950/20",
    border: "border-purple-500/30 dark:border-purple-800/40",
    text: "text-purple-600 dark:text-purple-400",
    glow: "shadow-[0_0_15px_rgba(168,85,247,0.1)]",
    badge: "bg-purple-500/15 text-purple-600 dark:text-purple-300 border-purple-500/30"
  },
  "First Person": {
    bg: "bg-amber-500/15 dark:bg-amber-950/30",
    border: "border-amber-500/50 dark:border-amber-600/50",
    text: "text-amber-600 dark:text-amber-300 font-semibold",
    glow: "shadow-[0_0_18px_rgba(245,158,11,0.2)]",
    badge: "bg-amber-500/20 text-amber-700 dark:text-amber-300 border-amber-500/40 font-semibold"
  },
  "Fallback/Special": {
    bg: "bg-rose-500/10 dark:bg-rose-950/20",
    border: "border-rose-500/30 dark:border-rose-800/40",
    text: "text-rose-600 dark:text-rose-400",
    glow: "shadow-[0_0_15px_rgba(244,63,94,0.1)]",
    badge: "bg-rose-500/15 text-rose-600 dark:text-rose-300 border-rose-500/30"
  }
};

interface CustomRAGNodeData {
  [key: string]: unknown;
  raw: RagFlowGraphNode;
  title: string;
  desc: string;
  category: string;
  isSlow: boolean;
  styles: { bg: string; border: string; text: string; glow: string; badge: string };
  invocationCount: number;
  avgLatencyMs: number;
}

function CustomRAGNode({ data, selected }: { data: CustomRAGNodeData; selected?: boolean }) {
  const { title, desc, category, isSlow, styles, invocationCount, avgLatencyMs } = data;
  return (
    <div
      className={`relative w-64 rounded-xl border p-3.5 backdrop-blur-md transition-all duration-200 select-none cursor-pointer ${
        styles.bg
      } ${
        selected
          ? "border-primary shadow-[0_0_20px_rgba(217,119,6,0.25)] ring-2 ring-primary ring-offset-2 ring-offset-background scale-[1.02]"
          : isSlow
          ? "border-destructive/80 shadow-[0_0_12px_rgba(239,68,68,0.2)]"
          : `${styles.border} hover:border-primary/60 hover:shadow-md`
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2.5 !h-2.5 !bg-primary/90 !border-2 !border-background !-left-1.5 shadow-sm"
      />
      <div className="flex items-center justify-between gap-1.5 mb-1.5">
        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${styles.badge}`}>
          {category}
        </span>
        {avgLatencyMs > 0 && (
          <Badge
            variant={isSlow ? "destructive" : "secondary"}
            className="h-4 px-1.5 text-[10px] font-mono tracking-tight"
          >
            {fmtMs(avgLatencyMs)}
          </Badge>
        )}
      </div>

      <h3 className="font-semibold text-xs text-foreground tracking-tight line-clamp-1">
        {title}
      </h3>

      <p className="text-[10px] text-muted-foreground line-clamp-2 leading-relaxed mt-1">
        {desc}
      </p>

      {invocationCount > 0 && (
        <div className="text-[9px] text-muted-foreground/80 mt-2 pt-1.5 border-t border-border/40 flex items-center justify-between font-mono">
          <span>Invocations</span>
          <span className="font-semibold text-foreground/90">{invocationCount}</span>
        </div>
      )}
      <Handle
        type="source"
        position={Position.Right}
        className="!w-2.5 !h-2.5 !bg-primary/90 !border-2 !border-background !-right-1.5 shadow-sm"
      />
    </div>
  );
}

const STRATEGY_DESCRIPTIONS: Record<string, string> = {
  standard: "Balanced RAG pipeline. Utilizes query decomposition, cross-encoder reranking, parent enrichment, and Self-RAG verification.",
  fast: "High-performance RAG. Bypasses query decomposition, parent enrichment, and reflection, running basic vector search and generation directly.",
  deep: "Deep analysis RAG. Employs HyDE, parent enrichment, recursive query rewriting, full safety contradiction checks, and deep self-reflection.",
  first_person: "Acoustic verbatim serving pipeline. Direct quotes from Sri Preethaji and Sri Krishnaji with ECAPA-TDNN voice verification, B5 rights clearing, and exact audio timecode alignment."
};

// Node Layer mapping to define auto-layout columns (x-axis coordinates)
const NODE_COLUMNS: Record<string, number> = {
  // Column 0: Intake & Gate
  __start__: 0,
  intent_router: 0,
  handle_distress_check: 0,
  fp_input: 0,

  // Column 1: Dispatch & Decomposition
  resolve_parallel: 1,
  resolve_followup: 1,
  decompose_query: 1,
  fp_directness_gate: 1,

  // Column 2: Handlers & Retrieval Initiation
  handle_casual: 2,
  handle_distress: 2,
  handle_meditation: 2,
  web_search: 2,
  navigate_and_hyde: 2,
  retrieve_documents: 2,
  fp_asr_resolver: 2,

  // Column 3: Reranking & Augmentation
  rerank_documents: 3,
  grade_documents: 3,
  _map_docs_to_relevant: 3,
  enrich_context: 3,
  check_context_sufficiency: 3,
  rewrite_query: 3,
  context_engineer: 3,
  first_person: 3,
  fp_ecapa_verify: 3,

  // Column 4: Synthesis & Verification
  generate_answer: 4,
  reflect_on_answer: 4,
  verify_answer: 4,
  check_contradiction: 4,
  fp_rights_gate: 4,

  // Column 5: Formatting & Attribution
  extract_citations: 5,
  format_final_answer: 5,
  explain_retrieval: 5,
  handle_fallback: 5,
  fp_context_harness: 5,

  // Column 6: Schema Contract & Terminal Exit
  fp_schema_contract: 6,
  fp_audio_output: 6,
  __end__: 6,
};

export default function RAGFlowPage() {
  const [strategy, setStrategy] = useState<RagStrategy>("standard");
  const { data: graphData, isLoading, error, refetch, isFetching } = useRagFlowGraph(strategy);
  const [selectedNode, setSelectedNode] = useState<RagFlowGraphNode | null>(null);

  const nodeTypes = useMemo(() => ({ ragNode: CustomRAGNode }), []);
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Compute Layout when graphData changes
  useEffect(() => {
    if (!graphData || !Array.isArray(graphData.nodes) || !Array.isArray(graphData.edges)) {
      setNodes([]);
      setEdges([]);
      return;
    }

    // Group nodes by their column index
    const colGroups: Record<number, string[]> = {};
    graphData.nodes.forEach((node) => {
      if (!node?.id) return;
      const col = NODE_COLUMNS[node.id] !== undefined ? NODE_COLUMNS[node.id] : 2;
      if (!colGroups[col]) colGroups[col] = [];
      colGroups[col].push(node.id);
    });

    const xSpacing = 340;
    const ySpacing = 145;
    const xOffset = 60;
    const midY = 380;

    // Generate react-flow nodes
    const flowNodes: FlowNode[] = graphData.nodes.map((node) => {
      const col = node?.id && NODE_COLUMNS[node.id] !== undefined ? NODE_COLUMNS[node.id] : 2;
      const indexInCol = node?.id && colGroups[col] ? colGroups[col].indexOf(node.id) : 0;
      const colSize = colGroups[col]?.length || 1;

      // Center column vertically around midY
      const x = xOffset + col * xSpacing;
      const y = midY + (indexInCol - (colSize - 1) / 2) * ySpacing;

      const descInfo = (node?.id && NODE_DESCRIPTIONS[node.id]) || {
        title: node?.label || node?.id || "Node",
        desc: "RAG pipeline execution node.",
        category: "Retrieval"
      };
      const styles = CATEGORY_STYLES[descInfo.category] || CATEGORY_STYLES["Retrieval"];
      const isSlow = (node?.avg_latency_ms ?? 0) > 1500;

      return {
        id: node?.id ?? "unknown-node",
        position: { x, y },
        type: "ragNode",
        data: {
          raw: node,
          title: descInfo.title,
          desc: descInfo.desc,
          category: descInfo.category,
          isSlow,
          styles,
          invocationCount: node?.invocation_count ?? 0,
          avgLatencyMs: node?.avg_latency_ms ?? 0,
        },
      };
    });

    // Generate react-flow edges
    const flowEdges = graphData.edges.map((edge) => {
      // Find latency if edge source matches any node's avg latency
      const srcNode = graphData.nodes?.find((n) => n?.id === edge?.source);
      const isSlowPath = srcNode && (srcNode.avg_latency_ms ?? 0) > 1500;

      return {
        id: edge?.id ?? `${edge?.source}-${edge?.target}`,
        source: edge?.source ?? "",
        target: edge?.target ?? "",
        animated: edge?.animated ?? false,
        type: "smoothstep",
        style: {
          stroke: isSlowPath ? "rgba(239, 68, 68, 0.8)" : "hsl(var(--primary) / 0.55)",
          strokeWidth: isSlowPath ? 2.5 : 2,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: isSlowPath ? "rgba(239, 68, 68, 0.9)" : "hsl(var(--primary) / 0.7)",
        },
      };
    });

    setNodes(flowNodes);
    setEdges(flowEdges);

    // Keep active selection in sync if it exists
    if (selectedNode) {
      const updatedNode = graphData.nodes?.find((n) => n?.id === selectedNode.id);
      if (updatedNode) {
        setSelectedNode(updatedNode);
      }
    }
  }, [graphData, selectedNode, setEdges, setNodes]);

  const onNodeClick = (_: ReactMouseEvent, node: FlowNode) => {
    const raw = (node?.data as unknown as CustomRAGNodeData | undefined)?.raw;
    if (raw) {
      setSelectedNode(raw);
    }
  };

  const selectedNodeDesc = useMemo(() => {
    if (!selectedNode?.id) return null;
    return NODE_DESCRIPTIONS[selectedNode.id] || {
      title: selectedNode.label || selectedNode.id,
      desc: "No description available for this custom node.",
      category: "Custom"
    };
  }, [selectedNode]);

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Network className="h-6 w-6 text-primary" />
            Interactive RAG Flow Graph
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Visualize the active LangGraph routing paths and execution node latency times.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Tabs
            value={strategy}
            onValueChange={(val) => {
              if (isRagStrategy(val)) setStrategy(val);
              setSelectedNode(null);
            }}
          >
            <TabsList className="bg-card border border-border">
              <TabsTrigger value="fast">Fast</TabsTrigger>
              <TabsTrigger value="standard">Standard</TabsTrigger>
              <TabsTrigger value="deep">Deep</TabsTrigger>
              <TabsTrigger value="first_person">First Person</TabsTrigger>
            </TabsList>
          </Tabs>

          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isFetching}
            className="shrink-0 border-border bg-card hover:bg-muted"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0 grid lg:grid-cols-4 gap-4">
        {/* Main Flow Canvas */}
        <Card className="lg:col-span-3 h-full overflow-hidden border border-border bg-card/50 flex flex-col relative">
          {error ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-destructive gap-3">
              <div className="flex items-center gap-2 font-medium">
                <AlertCircle className="h-5 w-5" />
                Failed to load RAG flow graph
              </div>
              <p className="text-xs text-muted-foreground max-w-sm">
                Could not retrieve pipeline graph structure. Verify backend service is healthy.
              </p>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                Retry
              </Button>
            </div>
          ) : isLoading ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground gap-2">
              <RefreshCw className="h-5 w-5 animate-spin text-primary" />
              Loading strategy graph structure...
            </div>
          ) : (
            <div className="flex-1 h-full w-full relative">
              <ReactFlow<FlowNode>
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                fitView
                fitViewOptions={{ padding: 0.15 }}
                maxZoom={1.5}
                minZoom={0.5}
                proOptions={{ hideAttribution: true }}
              >
                <Background color="rgba(156, 163, 175, 0.15)" gap={16} size={1} />
                <Controls showInteractive={false} className="bg-background border border-border rounded shadow" />
                <MiniMap
                  nodeStrokeColor={(n) => {
                    const desc = NODE_DESCRIPTIONS[n.id];
                    if (desc?.category === "Intent") return "#3b82f6";
                    if (desc?.category === "Retrieval") return "#10b981";
                    if (desc?.category === "Augmentation") return "#f59e0b";
                    if (desc?.category === "Generation") return "#a855f7";
                    return "#9ca3af";
                  }}
                  nodeColor="#1f2937"
                  className="bg-card border border-border rounded shadow dark:bg-card"
                  maskColor="rgba(0, 0, 0, 0.1)"
                />
              </ReactFlow>

              {/* Floating Strategy Descriptor */}
              <div className="absolute top-4 left-4 max-w-sm bg-background/95 backdrop-blur-md p-3 border border-border rounded-lg shadow-lg pointer-events-none">
                <h4 className="text-xs font-semibold capitalize text-primary flex items-center gap-1.5 mb-1">
                  <Sparkles className="h-3.5 w-3.5" />
                  {strategy} strategy active
                </h4>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  {STRATEGY_DESCRIPTIONS[strategy]}
                </p>
              </div>
            </div>
          )}
        </Card>

        {/* Side Inspector Panel */}
        <Card className="h-full border border-border bg-card flex flex-col overflow-hidden">
          <CardHeader className="border-b border-border bg-muted/20 px-4 py-3 shrink-0">
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              Inspector
            </CardTitle>
            <CardDescription className="text-xs">
              Click any node in the graph layout to inspect active latency details.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
            {selectedNode && selectedNodeDesc ? (
              <div className="space-y-4">
                {/* Node category badge and ID */}
                <div className="flex items-center justify-between">
                  <Badge className="capitalize select-none">
                    {selectedNodeDesc.category}
                  </Badge>
                  <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                    {selectedNode.id}
                  </span>
                </div>

                {/* Node Title & Description */}
                <div>
                  <h3 className="text-lg font-bold text-foreground">{selectedNodeDesc.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">
                    {selectedNodeDesc.desc}
                  </p>
                </div>

                <hr className="border-border" />

                {/* Metrics */}
                <div className="space-y-3">
                  <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Execution Telemetry
                  </h4>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-muted/40 p-2.5 rounded-lg border border-border/50">
                      <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3 text-primary" /> Avg Latency
                      </div>
                      <div className="text-lg font-bold font-mono mt-1 text-foreground">
                        {fmtMs(selectedNode?.avg_latency_ms ?? 0)}
                      </div>
                    </div>

                    <div className="bg-muted/40 p-2.5 rounded-lg border border-border/50">
                      <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                        <Database className="h-3 w-3 text-emerald-500" /> Invocations
                      </div>
                      <div className="text-lg font-bold font-mono mt-1 text-foreground">
                        {selectedNode?.invocation_count ?? 0}
                      </div>
                    </div>
                  </div>

                  {/* Latency Threshold Indicator */}
                  {(selectedNode?.avg_latency_ms ?? 0) > 0 && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-[10px] text-muted-foreground">
                        <span>Latency Status:</span>
                        <span className={(selectedNode?.avg_latency_ms ?? 0) > 1500 ? "text-rose-500 font-semibold" : "text-emerald-500"}>
                          {(selectedNode?.avg_latency_ms ?? 0) > 1500 ? "Degraded (Slow)" : "Optimal"}
                        </span>
                      </div>
                      <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            (selectedNode?.avg_latency_ms ?? 0) > 1500 ? "bg-rose-500" : "bg-emerald-500"
                          }`}
                          style={{ width: `${Math.min(((selectedNode?.avg_latency_ms ?? 0) / 3000) * 100, 100)}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Specific features links / highlights */}
                {selectedNode.id === "context_engineer" && (
                  <div className="mt-4 p-3 bg-primary/5 border border-primary/20 rounded-lg text-[11px] text-muted-foreground leading-relaxed">
                    <span className="font-semibold text-primary block mb-0.5">ℹ️ Reversible Context Compression (CCR)</span>
                    Intercepts <code>[RETRIEVE: url]</code> directives in LLM generation, restoring original text from <code>raw_documents</code> cache to verify citations.
                  </div>
                )}

                {selectedNode.id === "verify_answer" && (
                  <div className="mt-4 p-3 bg-primary/5 border border-primary/20 rounded-lg text-[11px] text-muted-foreground leading-relaxed">
                    <span className="font-semibold text-primary block mb-0.5">ℹ️ Ralph Teacher-Student Loop</span>
                    Validated corrections generated by the Teacher model are verified by the local Student model inside LettuceDetect and stored as active prompt patches.
                  </div>
                )}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-4 text-muted-foreground">
                <HelpCircle className="h-8 w-8 stroke-[1.5] mb-2 text-muted-foreground/50" />
                <p className="text-xs">No node selected.</p>
                <p className="text-[11px] text-muted-foreground/70 mt-1">
                  Click any node in the graph layout to inspect active timings and descriptions.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
