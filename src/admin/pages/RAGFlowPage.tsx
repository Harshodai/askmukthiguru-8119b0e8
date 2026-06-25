import { useState, useMemo, useEffect } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  Position,
  MarkerType,
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
  MessageSquare
} from "lucide-react";
import { fmtMs } from "@/admin/lib/formatters";

// Node description library for detailed admin inspect panel
const NODE_DESCRIPTIONS: Record<string, { title: string; desc: string; category: string }> = {
  intent_router: {
    title: "Intent Router",
    desc: "Analyzes incoming query intent, routing it to distress, casual chat, meditation, or full RAG flows.",
    category: "Intent"
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
  }
};

// Colors matching admin console aesthetic
const CATEGORY_STYLES: Record<string, { bg: string; border: string; text: string; glow: string }> = {
  "Intent": {
    bg: "bg-blue-500/10 dark:bg-blue-500/5",
    border: "border-blue-500/40 dark:border-blue-500/30",
    text: "text-blue-600 dark:text-blue-400",
    glow: "shadow-[0_0_15px_rgba(59,130,246,0.1)]"
  },
  "Retrieval": {
    bg: "bg-emerald-500/10 dark:bg-emerald-500/5",
    border: "border-emerald-500/40 dark:border-emerald-500/30",
    text: "text-emerald-600 dark:text-emerald-400",
    glow: "shadow-[0_0_15px_rgba(16,185,129,0.1)]"
  },
  "Augmentation": {
    bg: "bg-amber-500/10 dark:bg-amber-500/5",
    border: "border-amber-500/40 dark:border-amber-500/30",
    text: "text-amber-600 dark:text-amber-400",
    glow: "shadow-[0_0_15px_rgba(245,158,11,0.1)]"
  },
  "Generation": {
    bg: "bg-purple-500/10 dark:bg-purple-500/5",
    border: "border-purple-500/40 dark:border-purple-500/30",
    text: "text-purple-600 dark:text-purple-400",
    glow: "shadow-[0_0_15px_rgba(168,85,247,0.1)]"
  },
  "Fallback/Special": {
    bg: "bg-rose-500/10 dark:bg-rose-500/5",
    border: "border-rose-500/40 dark:border-rose-500/30",
    text: "text-rose-600 dark:text-rose-400",
    glow: "shadow-[0_0_15px_rgba(244,63,94,0.1)]"
  }
};

const STRATEGY_DESCRIPTIONS: Record<string, string> = {
  standard: "Balanced RAG pipeline. Utilizes query decomposition, cross-encoder reranking, parent enrichment, and Self-RAG verification.",
  fast: "High-performance RAG. Bypasses query decomposition, parent enrichment, and reflection, running basic vector search and generation directly.",
  deep: "Deep analysis RAG. Employs HyDE, parent enrichment, recursive query rewriting, full safety contradiction checks, and deep self-reflection."
};

// Node Layer mapping to define auto-layout columns (x-axis coordinates)
const NODE_COLUMNS: Record<string, number> = {
  // Intent (Col 1)
  intent_router: 0,
  resolve_followup: 0,
  decompose_query: 0,

  // Retrieval (Col 2)
  navigate_and_hyde: 1,
  retrieve_documents: 1,
  rerank_documents: 1,
  grade_documents: 1,

  // Augmentation (Col 3)
  enrich_context: 2,
  check_context_sufficiency: 2,
  rewrite_query: 2,
  context_engineer: 2,

  // Generation (Col 4)
  generate_answer: 3,
  reflect_on_answer: 3,
  verify_answer: 3,
  explain_retrieval: 3,
  format_final_answer: 3,
  check_contradiction: 3,

  // Handlers (Col 5)
  handle_casual: 4,
  handle_distress: 4,
  handle_meditation: 4,
  handle_fallback: 4,
  web_search: 4
};

export default function RAGFlowPage() {
  const [strategy, setStrategy] = useState<"standard" | "fast" | "deep">("standard");
  const { data: graphData, isLoading, refetch, isFetching } = useRagFlowGraph(strategy);
  const [selectedNode, setSelectedNode] = useState<any>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Compute Layout when graphData changes
  useEffect(() => {
    if (!graphData) return;

    // Group nodes by their column index
    const colGroups: Record<number, string[]> = {};
    graphData.nodes.forEach((node: any) => {
      const col = NODE_COLUMNS[node.id] !== undefined ? NODE_COLUMNS[node.id] : 2;
      if (!colGroups[col]) colGroups[col] = [];
      colGroups[col].push(node.id);
    });

    const xSpacing = 280;
    const ySpacing = 110;
    const xOffset = 50;
    const yOffset = 60;

    // Generate react-flow nodes
    const flowNodes = graphData.nodes.map((node: any) => {
      const col = NODE_COLUMNS[node.id] !== undefined ? NODE_COLUMNS[node.id] : 2;
      const indexInCol = colGroups[col].indexOf(node.id);
      const colSize = colGroups[col].length;
      
      // Center column vertically
      const totalColHeight = (colSize - 1) * ySpacing;
      const startY = yOffset + (400 - totalColHeight) / 2;
      
      const x = xOffset + col * xSpacing;
      const y = startY + indexInCol * ySpacing;

      const descInfo = NODE_DESCRIPTIONS[node.id] || { title: node.label, desc: "RAG pipeline execution node.", category: "Retrieval" };
      const styles = CATEGORY_STYLES[descInfo.category] || CATEGORY_STYLES["Retrieval"];

      // Dynamic warning borders for slow nodes
      const isSlow = node.avg_latency_ms > 1500;
      const latencyBorder = isSlow ? "border-rose-500/80 shadow-[0_0_15px_rgba(239,68,68,0.2)]" : styles.border;

      return {
        id: node.id,
        position: { x, y },
        type: "default",
        data: {
          label: (
            <div className={`p-3 rounded-lg border bg-card/90 backdrop-blur-md transition-all duration-300 text-left w-56 ${styles.glow} ${latencyBorder}`}>
              <div className="flex items-center justify-between gap-1 mb-1">
                <span className={`text-xs font-semibold uppercase tracking-wider ${styles.text}`}>
                  {descInfo.category}
                </span>
                {node.avg_latency_ms > 0 && (
                  <Badge variant={isSlow ? "destructive" : "secondary"} className="h-4 px-1.5 text-[10px]">
                    {fmtMs(node.avg_latency_ms)}
                  </Badge>
                )}
              </div>
              <h3 className="font-semibold text-sm truncate text-foreground">{descInfo.title}</h3>
              {node.invocation_count > 0 && (
                <div className="text-[10px] text-muted-foreground mt-1 flex items-center justify-between">
                  <span>Invocations:</span>
                  <span className="font-mono">{node.invocation_count}</span>
                </div>
              )}
            </div>
          ),
          raw: node
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });

    // Generate react-flow edges
    const flowEdges = graphData.edges.map((edge: any) => {
      // Find latency if edge source matches any node's avg latency
      const srcNode = graphData.nodes.find((n: any) => n.id === edge.source);
      const isSlowPath = srcNode && srcNode.avg_latency_ms > 1500;
      
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        animated: edge.animated,
        style: {
          stroke: isSlowPath ? "rgba(239, 68, 68, 0.45)" : "rgba(156, 163, 175, 0.3)",
          strokeWidth: isSlowPath ? 2.5 : 1.5,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 16,
          height: 16,
          color: isSlowPath ? "rgba(239, 68, 68, 0.6)" : "rgba(156, 163, 175, 0.4)",
        },
      };
    });

    setNodes(flowNodes);
    setEdges(flowEdges);

    // Keep active selection in sync if it exists
    if (selectedNode) {
      const updatedNode = graphData.nodes.find((n: any) => n.id === selectedNode.id);
      if (updatedNode) {
        setSelectedNode(updatedNode);
      }
    }
  }, [graphData]);

  const onNodeClick = (_: any, node: any) => {
    setSelectedNode(node.data.raw);
  };

  const selectedNodeDesc = useMemo(() => {
    if (!selectedNode) return null;
    return NODE_DESCRIPTIONS[selectedNode.id] || {
      title: selectedNode.label,
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
              setStrategy(val as any);
              setSelectedNode(null);
            }}
          >
            <TabsList className="bg-card border border-border">
              <TabsTrigger value="fast">Fast</TabsTrigger>
              <TabsTrigger value="standard">Standard</TabsTrigger>
              <TabsTrigger value="deep">Deep</TabsTrigger>
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
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground gap-2">
              <RefreshCw className="h-5 w-5 animate-spin text-primary" />
              Loading strategy graph structure...
            </div>
          ) : (
            <div className="flex-1 h-full w-full relative">
              <ReactFlow
                nodes={nodes}
                edges={edges}
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
                        {fmtMs(selectedNode.avg_latency_ms)}
                      </div>
                    </div>

                    <div className="bg-muted/40 p-2.5 rounded-lg border border-border/50">
                      <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                        <Database className="h-3 w-3 text-emerald-500" /> Invocations
                      </div>
                      <div className="text-lg font-bold font-mono mt-1 text-foreground">
                        {selectedNode.invocation_count}
                      </div>
                    </div>
                  </div>

                  {/* Latency Threshold Indicator */}
                  {selectedNode.avg_latency_ms > 0 && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-[10px] text-muted-foreground">
                        <span>Latency Status:</span>
                        <span className={selectedNode.avg_latency_ms > 1500 ? "text-rose-500 font-semibold" : "text-emerald-500"}>
                          {selectedNode.avg_latency_ms > 1500 ? "Degraded (Slow)" : "Optimal"}
                        </span>
                      </div>
                      <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
                        <div 
                          className={`h-full rounded-full transition-all duration-500 ${
                            selectedNode.avg_latency_ms > 1500 ? "bg-rose-500" : "bg-emerald-500"
                          }`}
                          style={{ width: `${Math.min((selectedNode.avg_latency_ms / 3000) * 100, 100)}%` }}
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
