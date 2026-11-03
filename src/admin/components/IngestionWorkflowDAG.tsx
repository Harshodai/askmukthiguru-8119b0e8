import { useMemo, useState } from "react";
import {
  ReactFlow,
  type Node,
  type Edge,
  type NodeTypes,
  Handle,
  Position,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  CheckCircle2,
  Clock,
  Sparkles,
  ShieldCheck,
  Headphones,
  FileText,
  UserCheck,
  Filter,
  Layers,
  Database,
  RefreshCw,
  ExternalLink,
  ChevronRight,
  Play,
  Activity,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VideoHitlPanel, decisionBlocksServing } from "@/admin/components/VideoReviewControls";
import {
  deriveNodeStates,
  normalizeJobPhase,
  type DagStageId,
  type JobSnapshot,
  type NodeRunState,
} from "@/admin/lib/ingestionStages";
import type { VideoHumanDecision } from "@/admin/types";

export interface IngestionVideoContext {
  videoId: string;
  title: string;
  url?: string;
  guru?: string;
  status?: string;
  duration?: string;
  chunksCount?: number;
  rightsStatus?: string;
  channel?: string;
  verifiedSpans?: number;
  totalSpans?: number;
  /** Lowest per-window ECAPA cosine measured for this video, when the backend has it. */
  minWindowCosine?: number | null;
  /** Machine speaker status across the video's spans: none | partial | full | n/a. */
  speakerStatus?: string;
  /** Teachers the voice match assigned to this video's spans. */
  guruIds?: string[];
  approved?: boolean | null;
  inV10?: boolean;
  /** Stored human decision; enables the Human Review tab and the serving toggle. */
  decision?: VideoHumanDecision | null;
}

/** Live job state, as reported by the backend job status endpoints. */
export interface IngestionJobView extends JobSnapshot {
  jobId?: string;
  progressPct?: number | null;
  errorMessage?: string | null;
  updatedAt?: string | null;
}

export interface IngestionStageData {
  [key: string]: unknown;
  id: string;
  stageNumber: number;
  title: string;
  category: string;
  desc: string;
  badge: string;
  metric: string;
  /** Run state from the live job; "unknown" when no job is being tracked. */
  status: NodeRunState;
  /** Progress of the whole job, shown on the active node only. */
  progressPct?: number | null;
  details: {
    inputs: string;
    algorithm: string;
    outputs: string;
    invariants: string[];
    logSample?: string;
  };
}

const CATEGORY_THEMES: Record<
  string,
  { bg: string; border: string; text: string; glow: string; badge: string; icon: React.ComponentType<{ className?: string }> }
> = {
  Intake: {
    bg: "bg-blue-500/10 dark:bg-blue-950/20",
    border: "border-blue-500/30 dark:border-blue-800/40",
    text: "text-blue-600 dark:text-blue-400",
    glow: "shadow-[0_0_15px_rgba(59,130,246,0.12)]",
    badge: "bg-blue-500/15 text-blue-600 dark:text-blue-300 border-blue-500/30",
    icon: ExternalLink,
  },
  Audio: {
    bg: "bg-cyan-500/10 dark:bg-cyan-950/20",
    border: "border-cyan-500/30 dark:border-cyan-800/40",
    text: "text-cyan-600 dark:text-cyan-400",
    glow: "shadow-[0_0_15px_rgba(6,182,212,0.12)]",
    badge: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-300 border-cyan-500/30",
    icon: Headphones,
  },
  Transcription: {
    bg: "bg-indigo-500/10 dark:bg-indigo-950/20",
    border: "border-indigo-500/30 dark:border-indigo-800/40",
    text: "text-indigo-600 dark:text-indigo-400",
    glow: "shadow-[0_0_15px_rgba(99,102,241,0.12)]",
    badge: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-300 border-indigo-500/30",
    icon: FileText,
  },
  Attribution: {
    bg: "bg-amber-500/15 dark:bg-amber-950/30",
    border: "border-amber-500/50 dark:border-amber-600/50",
    text: "text-amber-600 dark:text-amber-300 font-semibold",
    glow: "shadow-[0_0_18px_rgba(245,158,11,0.2)]",
    badge: "bg-amber-500/20 text-amber-700 dark:text-amber-300 border-amber-500/40 font-semibold",
    icon: UserCheck,
  },
  "Quality Gate": {
    bg: "bg-rose-500/10 dark:bg-rose-950/20",
    border: "border-rose-500/30 dark:border-rose-800/40",
    text: "text-rose-600 dark:text-rose-400",
    glow: "shadow-[0_0_15px_rgba(244,63,94,0.12)]",
    badge: "bg-rose-500/15 text-rose-600 dark:text-rose-300 border-rose-500/30",
    icon: Filter,
  },
  Chunking: {
    bg: "bg-emerald-500/10 dark:bg-emerald-950/20",
    border: "border-emerald-500/30 dark:border-emerald-800/40",
    text: "text-emerald-600 dark:text-emerald-400",
    glow: "shadow-[0_0_15px_rgba(16,185,129,0.12)]",
    badge: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-500/30",
    icon: Layers,
  },
  Embedding: {
    bg: "bg-purple-500/10 dark:bg-purple-950/20",
    border: "border-purple-500/30 dark:border-purple-800/40",
    text: "text-purple-600 dark:text-purple-400",
    glow: "shadow-[0_0_15px_rgba(168,85,247,0.12)]",
    badge: "bg-purple-500/15 text-purple-600 dark:text-purple-300 border-purple-500/30",
    icon: Sparkles,
  },
  Persistence: {
    bg: "bg-teal-500/10 dark:bg-teal-950/20",
    border: "border-teal-500/30 dark:border-teal-800/40",
    text: "text-teal-600 dark:text-teal-400",
    glow: "shadow-[0_0_15px_rgba(20,184,166,0.12)]",
    badge: "bg-teal-500/15 text-teal-600 dark:text-teal-300 border-teal-500/30",
    icon: Database,
  },
};

type IngestionNode = Node<IngestionStageData>;

/** Ring/border classes for a node, by run state. The active node pulses. */
function nodeStateClasses(status: NodeRunState, selected: boolean | undefined, themeBorder: string, themeGlow: string) {
  if (status === "active") return "border-primary ring-4 ring-primary/30 animate-pulse shadow-xl z-10";
  if (status === "failed") return "border-red-500 ring-2 ring-red-500/40";
  if (selected) return "border-amber-400 ring-2 ring-amber-400/40 scale-105 shadow-xl z-20";
  return `${themeBorder} hover:border-amber-400/60 hover:scale-[1.02] ${themeGlow}`;
}

export function IngestionCustomNode({ data, selected }: { data: IngestionStageData; selected?: boolean }) {
  const theme = CATEGORY_THEMES[data.category] || CATEGORY_THEMES.Intake;
  const Icon = theme.icon;
  const isActive = data.status === "active";

  return (
    <div
      data-testid={`dag-node-${data.id}`}
      data-run-state={data.status}
      className={`relative w-72 rounded-xl border p-4 backdrop-blur-md transition-all duration-200 select-none cursor-pointer ${
        theme.bg
      } ${nodeStateClasses(data.status, selected, theme.border, theme.glow)} ${
        data.status === "queued" ? "opacity-70" : ""
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !border-2 !border-background !bg-primary transition-transform hover:!scale-125"
      />

      {/* Header with Stage Number & Category */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground/90">
          <Icon className="w-3.5 h-3.5 text-primary" />
          <span>Stage {data.stageNumber}</span>
        </span>
        <Badge variant="outline" className={`text-[10px] uppercase tracking-wider py-0 px-2 ${theme.badge}`}>
          {data.category}
        </Badge>
      </div>

      {/* Title & Description */}
      <div className="space-y-1 mb-3">
        <h4 className="text-sm font-semibold text-foreground leading-snug line-clamp-1">
          {data.title}
        </h4>
        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
          {data.desc}
        </p>
      </div>

      {isActive && (
        <div className="mb-2 space-y-1" data-testid="dag-active-indicator">
          <Badge className="bg-primary text-primary-foreground text-[10px] gap-1 py-0">
            <Activity className="w-3 h-3" /> Processing…
          </Badge>
          {typeof data.progressPct === "number" && (
            <Progress value={Math.max(0, Math.min(100, data.progressPct))} className="h-1.5" />
          )}
        </div>
      )}
      {data.status === "failed" && (
        <Badge variant="destructive" className="mb-2 text-[10px] py-0">
          Failed here
        </Badge>
      )}

      {/* Footer Meta Chips */}
      <div className="flex items-center justify-between pt-2 border-t border-border/40 text-[11px]">
        <span
          className={`inline-flex items-center gap-1 font-medium ${
            data.status === "completed"
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-muted-foreground"
          }`}
        >
          {data.status === "completed" ? (
            <CheckCircle2 className="w-3 h-3" />
          ) : (
            <Clock className="w-3 h-3" />
          )}
          {data.badge}
        </span>
        <span className="font-mono text-muted-foreground bg-background/60 px-1.5 py-0.5 rounded border border-border/50 text-[10px]">
          {data.metric}
        </span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!w-3 !h-3 !border-2 !border-background !bg-primary transition-transform hover:!scale-125"
      />
    </div>
  );
}

const nodeTypes: NodeTypes = {
  ingestStage: IngestionCustomNode,
};

const DEFAULT_STAGES: IngestionStageData[] = [
  {
    id: "stage-1-intake",
    stageNumber: 1,
    title: "Intake & Rights Register",
    category: "Intake",
    desc: "Validates YouTube URL, resolves video metadata, and verifies rights registration in CONTENT-RIGHTS.md.",
    badge: "Rights register",
    metric: "X40 gate",
    status: "unknown",
    details: {
      inputs: "YouTube / Web Video URL (e.g. https://www.youtube.com/watch?v=kYv9qQj8K8M)",
      algorithm: "docs/rights/CONTENT-RIGHTS.md join + source_releases authority",
      outputs: "domain_rights_status='licensed', canonical asset_id, duration_ms",
      invariants: [
        "X40: Rights status originates solely from the curated rights register. Never default missing rights to 'licensed'.",
        "Rejections must be recorded in public.corpus_gate_rejections with tier & source coordinates.",
      ],
      logSample: "Validated asset against rights register: status=licensed, tier=production_authorized",
    },
  },
  {
    id: "stage-2-audio",
    stageNumber: 2,
    title: "Audio Extraction & WAV Slicing",
    category: "Audio",
    desc: "Extracts complete 16kHz mono PCM WAV master into audio archive and creates coordinate frame.",
    badge: "16kHz Mono PCM",
    metric: "fp-coords-v1",
    status: "unknown",
    details: {
      inputs: "Master video container / stream",
      algorithm: "FFmpeg demuxing @ 16,000 Hz, 16-bit mono PCM",
      outputs: "audio_archive/wavs/{video_id}.wav, audio_duration_ms, coordinate_space_version='fp-coords-v1'",
      invariants: [
        "X21: Slice ECAPA audio from audio_archive/wavs/, never from incomplete stubs.",
        "X7: Schema is first-person-speaker-conflict-v2 with explicit audio_start_ms and audio_end_ms.",
      ],
      logSample: "Extracted audio: duration=1,487,540ms, channels=1, rate=16000Hz, sha256=0197b992...",
    },
  },
  {
    id: "stage-3-asr",
    stageNumber: 3,
    title: "ASR Transcription & Alignment",
    category: "Transcription",
    desc: "Generates word-level timestamps and verbatim text normalization using Parakeet-TDT and Whisper.",
    badge: "Word Timestamps",
    metric: "Parakeet-TDT",
    status: "unknown",
    details: {
      inputs: "16kHz WAV audio master",
      algorithm: "NVIDIA Parakeet TDT 0.6B + Unicode normalization (fp-norm-unicode-v1)",
      outputs: "Timed word transcript with exact [start_ms, end_ms] token coverage",
      invariants: [
        "Verbatim alignment must cover 100% of the speech audio window without hallucinations.",
        "X32: Pre-extracted transcript cache stale check applied (PRE_EXTRACTED_MAX_AGE_SKIP=30d).",
      ],
      logSample: "ASR aligned: 488 words across 194,330ms extent. Token coverage: 1.00",
    },
  },
  {
    id: "stage-4-attribution",
    stageNumber: 4,
    title: "ECAPA Speaker Attribution",
    category: "Attribution",
    desc: "Extracts speaker voice embeddings and runs cosine distance verification against Sri Preethaji & Sri Krishnaji anchors.",
    badge: "ECAPA-TDNN",
    metric: "speaker_verified",
    status: "unknown",
    details: {
      inputs: "Word-aligned audio slices from audio_archive/wavs/",
      algorithm: "SpeechBrain ECAPA-TDNN (ENROLL_MIN=0.75, ANCHOR_LABEL_MIN=0.55, CLUSTER_DISTANCE=0.6)",
      outputs: "speaker_verified=true/false, voice_method='ecapa_anchor_v2', speaker_confidence=0.84",
      invariants: [
        "X18: Expected guru of a span is the claim under test; contradictions are quarantined as refused_guru_mismatch.",
        "X31: Displayed speaker stays as-verified; unverified speakers label as 'shared in <channel>'.",
      ],
      logSample: "Speaker verified: teacher=<guru_id>, cosine_similarity=<float>, margin=<float>",
    },
  },
  {
    id: "stage-5-sanitization",
    stageNumber: 5,
    title: "Quality Filter & CoT Sanitization",
    category: "Quality Gate",
    desc: "Enforces find_artifact() gate, stripping LLM reasoning leaks (CoT), loops, and prompt artifacts.",
    badge: "find_artifact() gate",
    metric: "CoT purge",
    status: "unknown",
    details: {
      inputs: "Verbatim transcript spans",
      algorithm: "services.text_quality_filter.find_artifact() + regex CoT / narrative story purge",
      outputs: "Clean authentic spiritual quotes with zero corporate anecdotes or LLM thoughts",
      invariants: [
        "Ingestion Safety Invariant 1: Every LLM generate output reaching Qdrant MUST pass find_artifact().",
        "Ingestion Safety Invariant 2: Graceful degradation strings ('temporary connection issue') blocked from persistence.",
      ],
      logSample: "Quality gate passed: 0 reasoning tokens, 0 degradation strings, 0 corporate anecdotes.",
    },
  },
  {
    id: "stage-6-chunking",
    stageNumber: 6,
    title: "Semantic Discourse Chunking",
    category: "Chunking",
    desc: "Chunks discourse along complete spiritual thought boundaries (boundary_v1) without breaking sacred aphorisms.",
    badge: "boundary_v1",
    metric: "complete thoughts",
    status: "unknown",
    details: {
      inputs: "Clean transcript tokens",
      algorithm: "boundary_v1 discourse chunker with overlap window",
      outputs: "Atomic semantic chunks stamped with chunker_version='boundary_v1:...'",
      invariants: [
        "X40: chunker_version must name the real chunker class (boundary_v1). Proposition chunking retired.",
        "Chunks must preserve antecedent clarity and teacher discourse continuity.",
      ],
      logSample: "Chunking complete: 18 semantic units generated. Chunker version: boundary_v1:500:50",
    },
  },
  {
    id: "stage-7-embedding",
    stageNumber: 7,
    title: "Dense Vector Embedding",
    category: "Embedding",
    desc: "Encodes spiritual text units into 1024-dimensional dense vectors using BAAI/bge-m3.",
    badge: "BGE-M3 (1024d)",
    metric: "Normalized Vectors",
    status: "unknown",
    details: {
      inputs: "Sanitized discourse chunks",
      algorithm: "BAAI/bge-m3 dense embedder with fp16 acceleration",
      outputs: "1024-dimensional unit vectors + exact cache invalidation key",
      invariants: [
        "Embedding dimension strictly pinned to 1024 to match Qdrant collection schema.",
        "Exact cache fingerprint includes legacy_collection, legacy_schema, evidence_policy.",
      ],
      logSample: "Generated 18 dense embeddings (1024d) in 1.45s. L2 norm: 1.000",
    },
  },
  {
    id: "stage-8-persistence",
    stageNumber: 8,
    title: "Dual-Store Persistence",
    category: "Persistence",
    desc: "Indexes vector chunks into Qdrant first_person_v11 collection and relational entities into Memgraph/Neo4j graph.",
    badge: "Qdrant & Memgraph",
    metric: "Contract Certified",
    status: "unknown",
    details: {
      inputs: "Vectors, metadata, and ontological concepts",
      algorithm: "Qdrant upsert (payload stamping) + Memgraph CYPHER node/edge creation",
      outputs: "Live queryable points; domain_rights_status resolved from the rights register (fails closed to 'unverified'), speaker_verified copied from the voice match",
      invariants: [
        "X13: B4 serving contract enforced — legacy and context stores cannot cross-contaminate.",
        "Ingestion Safety Invariant 3: Checkpoint state cross-validated against points_count in stores.",
      ],
      logSample: "Indexed 18 points in Qdrant (first_person_v11). Memgraph: 14 entities and 22 edges created.",
    },
  },
];

const INITIAL_EDGES: Edge[] = [
  { id: "e1-2", source: "stage-1-intake", target: "stage-2-audio", animated: true, type: "smoothstep", style: { stroke: "#3b82f6", strokeWidth: 2 } },
  { id: "e2-3", source: "stage-2-audio", target: "stage-3-asr", animated: true, type: "smoothstep", style: { stroke: "#06b6d4", strokeWidth: 2 } },
  { id: "e3-4", source: "stage-3-asr", target: "stage-4-attribution", animated: true, type: "smoothstep", style: { stroke: "#6366f1", strokeWidth: 2 } },
  { id: "e4-5", source: "stage-4-attribution", target: "stage-5-sanitization", animated: true, type: "smoothstep", style: { stroke: "#f59e0b", strokeWidth: 2 } },
  { id: "e5-6", source: "stage-5-sanitization", target: "stage-6-chunking", animated: true, type: "smoothstep", style: { stroke: "#f43f5e", strokeWidth: 2 } },
  { id: "e6-7", source: "stage-6-chunking", target: "stage-7-embedding", animated: true, type: "smoothstep", style: { stroke: "#10b981", strokeWidth: 2 } },
  { id: "e7-8", source: "stage-7-embedding", target: "stage-8-persistence", animated: true, type: "smoothstep", style: { stroke: "#a855f7", strokeWidth: 2 } },
];

const STATE_LABEL: Record<NodeRunState, string> = {
  completed: "Completed",
  active: "Processing…",
  queued: "Queued",
  failed: "Failed",
  unknown: "No live job",
};

const STATE_BADGE_CLASS: Record<NodeRunState, string> = {
  completed: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  active: "bg-primary text-primary-foreground",
  queued: "bg-muted text-muted-foreground",
  failed: "bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30",
  unknown: "bg-muted text-muted-foreground",
};

function jobBanner(job: IngestionJobView | null | undefined): { label: string; className: string } {
  switch (normalizeJobPhase(job?.status)) {
    case "running":
      return {
        label: job?.stage ? `Processing · ${job.stage}` : "Processing",
        className: "bg-primary/15 text-primary border-primary/30",
      };
    case "completed":
      return { label: "Job completed", className: STATE_BADGE_CLASS.completed };
    case "failed":
      return { label: "Job failed", className: STATE_BADGE_CLASS.failed };
    default:
      return { label: "No live job tracked", className: STATE_BADGE_CLASS.unknown };
  }
}

function EvidenceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1 border-b border-border/40 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-foreground text-right break-all">{value}</span>
    </div>
  );
}

/** Machine-measured evidence for the selected video. Read-only; every value comes from the backend. */
function VerificationEvidence({ video }: { video?: IngestionVideoContext }) {
  if (!video) {
    return <p className="text-xs text-muted-foreground">Select a video to see its measured evidence.</p>;
  }
  const spans =
    video.totalSpans != null && video.verifiedSpans != null
      ? `${video.verifiedSpans} / ${video.totalSpans}`
      : "not reported";
  return (
    <div className="space-y-3 text-xs" data-testid="verification-evidence">
      <div className="rounded-lg border border-border bg-muted/20 p-3">
        <EvidenceRow label="Speaker verification" value={video.speakerStatus ?? "not reported"} />
        <EvidenceRow label="Voice-verified spans" value={spans} />
        <EvidenceRow
          label="Lowest window cosine"
          value={video.minWindowCosine != null ? video.minWindowCosine.toFixed(3) : "not measured"}
        />
        <EvidenceRow
          label="Teacher (voice match)"
          value={video.guruIds && video.guruIds.length > 0 ? video.guruIds.join(", ") : "not reported"}
        />
        <EvidenceRow label="In serving collection" value={video.inV10 == null ? "not reported" : video.inV10 ? "yes" : "no"} />
        <EvidenceRow label="Rights status" value={video.rightsStatus ?? "not reported"} />
        <EvidenceRow
          label="Admin decision"
          value={
            video.decision == null
              ? "none"
              : decisionBlocksServing(video.decision)
                ? "excluded from serving"
                : video.decision.admin_approved === true
                  ? "allowed"
                  : "no block"
          }
        />
      </div>
      <p className="text-muted-foreground">
        Values are read from the serving collection and the decisions file. Faithfulness (LettuceDetect)
        is a chat-time check, not an ingestion metric, so it is not shown here.
      </p>
    </div>
  );
}

export function IngestionWorkflowDAG({
  videoContext,
  job,
  onRefresh,
  onDecisionSaved,
}: {
  videoContext?: IngestionVideoContext;
  /** Live job state; leave undefined when no job is tracked. */
  job?: IngestionJobView | null;
  onRefresh?: () => void;
  /** Called after a human decision is saved so the parent can reload its list. */
  onDecisionSaved?: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const nodeStates = useMemo(() => deriveNodeStates(job), [job]);

  // Derived from props on every change: a live job must be able to move the highlight.
  const stages: IngestionStageData[] = useMemo(
    () =>
      DEFAULT_STAGES.map((stage) => {
        const status = nodeStates[stage.id as DagStageId];
        return {
          ...stage,
          status,
          progressPct: status === "active" ? (job?.progressPct ?? null) : null,
          metric:
            stage.id === "stage-1-intake" && videoContext?.videoId
              ? `ID: ${videoContext.videoId}`
              : stage.id === "stage-8-persistence" && videoContext?.chunksCount
                ? `${videoContext.chunksCount} chunks indexed`
                : stage.metric,
        };
      }),
    [nodeStates, job?.progressPct, videoContext?.videoId, videoContext?.chunksCount],
  );

  const nodes: IngestionNode[] = useMemo(() => {
    const xSpacing = 320;
    const ySpacing = 160;
    return stages.map((stage, idx) => ({
      id: stage.id,
      type: "ingestStage",
      position: { x: 40 + (idx % 4) * xSpacing, y: 60 + Math.floor(idx / 4) * ySpacing },
      data: stage,
      selected: stage.id === selectedId,
    }));
  }, [stages, selectedId]);

  // Only the edge feeding the working node flows; the rest hold still.
  const edges: Edge[] = useMemo(
    () =>
      INITIAL_EDGES.map((edge) => ({
        ...edge,
        animated: nodeStates[edge.target as DagStageId] === "active",
      })),
    [nodeStates],
  );

  const selectedStage = stages.find((s) => s.id === selectedId) ?? null;
  const banner = jobBanner(job);
  const excluded = decisionBlocksServing(videoContext?.decision);
  const teacherLabel =
    videoContext?.guruIds && videoContext.guruIds.length > 0
      ? videoContext.guruIds.join(", ")
      : (videoContext?.guru ?? "not reported");

  const handleNodeClick = (_: React.MouseEvent, node: IngestionNode) => {
    setSelectedId(node.id);
    setSheetOpen(true);
  };

  return (
    <div className="space-y-4">
      {/* Video Context Banner */}
      <Card className="border-primary/20 bg-card/60 backdrop-blur-md">
        <CardContent className="p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="space-y-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs uppercase tracking-wider font-semibold text-primary flex items-center gap-1.5">
                <Play className="w-3.5 h-3.5 fill-current" /> Video Ingestion Pipeline DAG
              </span>
              {videoContext?.videoId && (
                <Badge variant="secondary" className="font-mono text-xs">
                  {videoContext.videoId}
                </Badge>
              )}
              {excluded && (
                <Badge variant="destructive" className="text-xs" data-testid="excluded-badge">
                  Excluded from serving
                </Badge>
              )}
            </div>
            <h3 className="text-base font-semibold text-foreground truncate">
              {videoContext?.title ?? "No video selected"}
            </h3>
            <p className="text-xs text-muted-foreground flex items-center gap-3 flex-wrap">
              <span>Teacher (voice match): <strong className="text-foreground">{teacherLabel}</strong></span>
              {videoContext?.totalSpans != null && (
                <>
                  <span>·</span>
                  <span>
                    Voice-verified spans:{" "}
                    <strong className="text-foreground">
                      {videoContext.verifiedSpans ?? 0} / {videoContext.totalSpans}
                    </strong>
                  </span>
                </>
              )}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {onRefresh && (
              <Button size="sm" variant="outline" onClick={onRefresh} className="gap-1.5 text-xs">
                <RefreshCw className="w-3.5 h-3.5" /> Refresh Status
              </Button>
            )}
            <Badge variant="outline" className={`text-xs px-2.5 py-1 ${banner.className}`} data-testid="job-banner">
              {banner.label}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Interactive ReactFlow DAG Canvas */}
      <Card className="border-border/60 overflow-hidden shadow-md">
        <CardHeader className="py-3 px-5 border-b border-border/50 bg-muted/20 flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Activity className="w-4 h-4 text-ojas" /> End-to-End Content Ingestion DAG
            </CardTitle>
            <CardDescription className="text-xs">
              Click any stage for its contract, log state, measured evidence and human review.
              {normalizeJobPhase(job?.status) === "idle" && " Stage colours stay neutral until a job is tracked."}
            </CardDescription>
          </div>
          <span className="text-xs text-muted-foreground font-mono">Pan & Zoom Enabled</span>
        </CardHeader>
        <CardContent className="p-0 h-[480px] bg-background/50 relative">
          <ReactFlow<IngestionNode>
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={handleNodeClick}
            nodesDraggable={false}
            nodesConnectable={false}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.6}
            maxZoom={1.5}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
            <Controls className="!bg-card !border-border !shadow-md" />
            <MiniMap
              className="!bg-card/90 !border-border !rounded-lg"
              nodeColor={(n) => (n.data?.status === "active" ? "#f59e0b" : "#94a3b8")}
              maskColor="rgba(0, 0, 0, 0.4)"
            />
          </ReactFlow>
        </CardContent>
      </Card>

      {/* Stage drawer: overview, logs, measured evidence, human review */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="w-full sm:max-w-md overflow-y-auto">
          {selectedStage && (
            <div className="space-y-4">
              <SheetHeader>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-xs font-mono uppercase">
                    Stage {selectedStage.stageNumber}
                  </Badge>
                  <Badge className={`text-xs ${STATE_BADGE_CLASS[selectedStage.status]}`}>
                    {STATE_LABEL[selectedStage.status]}
                  </Badge>
                </div>
                <SheetTitle className="text-lg font-bold text-foreground">{selectedStage.title}</SheetTitle>
                <SheetDescription className="text-xs leading-relaxed">{selectedStage.desc}</SheetDescription>
              </SheetHeader>

              <Tabs defaultValue="overview">
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="overview" className="text-[11px]">Overview</TabsTrigger>
                  <TabsTrigger value="logs" className="text-[11px]">Logs</TabsTrigger>
                  <TabsTrigger value="verification" className="text-[11px]">Verify</TabsTrigger>
                  <TabsTrigger value="review" className="text-[11px]">Review</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-4 text-xs">
                  <div className="space-y-2 rounded-lg border border-border p-3 bg-muted/20">
                    <p className="font-semibold text-foreground flex items-center gap-1.5">
                      <ChevronRight className="w-3.5 h-3.5 text-primary" /> Stage Data Contract
                    </p>
                    <div className="space-y-1.5 pl-2 text-muted-foreground">
                      <div><span className="font-medium text-foreground">Inputs:</span> {selectedStage.details.inputs}</div>
                      <div><span className="font-medium text-foreground">Algorithm:</span> {selectedStage.details.algorithm}</div>
                      <div><span className="font-medium text-foreground">Outputs:</span> {selectedStage.details.outputs}</div>
                    </div>
                  </div>
                  <div className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                    <p className="font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5" /> Binding Architecture Invariants
                    </p>
                    <ul className="space-y-1 pl-4 list-disc text-foreground/90">
                      {selectedStage.details.invariants.map((inv, idx) => (
                        <li key={idx} className="leading-relaxed">{inv}</li>
                      ))}
                    </ul>
                  </div>
                </TabsContent>

                <TabsContent value="logs" className="space-y-3 text-xs" data-testid="logs-tab">
                  {job && (selectedStage.status === "active" || selectedStage.status === "failed") ? (
                    <div className="rounded-lg border border-border bg-muted/20 p-3">
                      <EvidenceRow label="Job stage" value={job.stage ?? "not reported"} />
                      <EvidenceRow label="Job status" value={job.status ?? "not reported"} />
                      <EvidenceRow
                        label="Progress"
                        value={job.progressPct != null ? `${job.progressPct}%` : "not reported"}
                      />
                      <EvidenceRow label="Updated" value={job.updatedAt ?? "not reported"} />
                      {job.errorMessage && <EvidenceRow label="Error" value={job.errorMessage} />}
                    </div>
                  ) : (
                    <p className="text-muted-foreground">
                      {job
                        ? "This stage is not the one reporting right now."
                        : "No job is being tracked for this video."}
                    </p>
                  )}
                  <p className="text-muted-foreground">
                    The backend reports a stage name and progress per job. It does not store per-stage log
                    lines yet, so no log stream is shown.
                  </p>
                  {selectedStage.details.logSample && (
                    <div className="space-y-1.5">
                      <p className="font-semibold text-foreground">Log line format (reference, not from this video)</p>
                      <pre className="p-2.5 rounded-lg bg-zinc-950 text-zinc-300 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap border border-zinc-800">
                        {selectedStage.details.logSample}
                      </pre>
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="verification">
                  <VerificationEvidence video={videoContext} />
                </TabsContent>

                <TabsContent value="review">
                  {videoContext && videoContext.decision !== undefined ? (
                    <VideoHitlPanel
                      key={`${videoContext.videoId}-${videoContext.decision?.updated_at ?? "none"}`}
                      videoId={videoContext.videoId}
                      decision={videoContext.decision}
                      onSaved={onDecisionSaved}
                    />
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Open this video from Video Approval to review it. Human review needs the stored
                      decision for the video.
                    </p>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

export default IngestionWorkflowDAG;
