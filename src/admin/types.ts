// Types mirror the eventual Postgres schema 1:1.
// When backend auth is enabled, these stay; only the data-fetching bodies in
// src/admin/lib/mockData.ts swap from in-memory to real database queries.

export type ISODate = string;

export interface TelemetryEvent {
  id: string;
  user_id: string | null;
  session_id: string | null;
  user_message_id: string;
  last_message_id: string | null;
  metric_type: string;
  metric_value: number;
  tags: Record<string, unknown>;
  created_at: ISODate;
}

export interface TelemetryFilters extends Partial<DateRange> {
  user_id?: string;
  session_id?: string;
  metric_type?: string;
  user_message_id?: string;
  limit?: number;
  offset?: number;
}

export interface TelemetryResponse {
  data: TelemetryEvent[];
  count: number;
  limit: number;
  offset: number;
}

export interface PromptVersion {
  id: string;
  name: string;
  version: number;
  content: string;
  active: boolean;
  created_at: ISODate;
}

export interface ChatSession {
  id: string;
  anon_user_id: string;
  channel: "web" | "mobile" | "api";
  started_at: ISODate;
}

export type QueryStatus = "ok" | "error" | "blocked";

export interface ChatQuery {
  id: string;
  session_id: string;
  anon_user_id: string;
  query_text: string;
  prompt_version_id: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_estimate: number;
  latency_ms: number;
  status: QueryStatus;
  created_at: ISODate;
}

export interface RetrievalEvent {
  id: string;
  query_id: string;
  chunk_ids: string[];
  source_docs: string[];
  scores: number[];
  top_k: number;
  retrieval_hit: boolean;
}

export interface ChatResponse {
  id: string;
  query_id: string;
  response_text: string;
  citations: { source: string; snippet: string }[];
  faithfulness: number;
  answer_relevancy: number;
  context_precision: number;
  context_recall: number;
  hallucination_flag: boolean;
  judge_reasoning: string;
  confidence: number;
  created_at: ISODate;
}

export interface TriggerEvent {
  id: string;
  query_id: string;
  trigger_name:
    | "serene_mind"
    | "fallback"
    | "safety"
    | "meditation"
    | "youtube_link"
    | "guru_handoff";
  metadata: Record<string, unknown>;
  created_at: ISODate;
}

export interface UserFeedback {
  id: string;
  response_id: string;
  rating: -1 | 0 | 1;
  accuracy: number | null;
  comment: string | null;
  created_at: ISODate;
}

export type SpanName =
  | "guardrails_in"
  | "embed"
  | "vector_search"
  | "rerank"
  | "llm"
  | "judge"
  | "guardrails_out";

export interface TraceSpan {
  id: string;
  query_id: string;
  parent_span_id: string | null;
  name: SpanName;
  start_ms: number;
  duration_ms: number;
  attributes: Record<string, unknown>;
}

export interface SafetyEvent {
  id: string;
  query_id: string;
  type: "prompt_injection" | "pii_input" | "pii_output" | "toxicity" | "jailbreak";
  severity: "low" | "medium" | "high";
  excerpt: string;
  created_at: ISODate;
}

export interface GoldenQuestion {
  id: string;
  question: string;
  expected_answer: string;
  expected_sources: string[];
  tags: string[];
  active: boolean;
}

export interface EvalRun {
  id: string;
  triggered_by: "manual" | "scheduled" | "prompt_change";
  prompt_version_id: string;
  started_at: ISODate;
  finished_at: ISODate;
  summary: {
    total: number;
    passed: number;
    avg_faithfulness: number;
    avg_answer_relevancy: number;
    avg_context_precision: number;
    avg_context_recall: number;
  };
}

export interface EvalResult {
  id: string;
  eval_run_id: string;
  golden_id: string;
  faithfulness: number;
  answer_relevancy: number;
  context_precision: number;
  context_recall: number;
  passed: boolean;
  response_text: string;
}

export interface IngestionRun {
  id: string;
  source: string;
  chunks_added: number;
  embedding_model: string;
  duration_ms: number;
  status: "ok" | "partial" | "failed";
  error_log: string | null;
  created_at: ISODate;
}

export interface AppLog {
  id: number;
  level: "debug" | "info" | "warn" | "error";
  message: string;
  context: Record<string, unknown>;
  request_id: string;
  created_at: ISODate;
}

export interface ModelPricing {
  model: string;
  input_per_1k: number;
  output_per_1k: number;
  currency: "USD";
}

export interface QueryCluster {
  cluster_id: number;
  cluster_label: string;
  size: number;
  avg_faithfulness: number;
  centroid_query: string;
}

export interface AlertRule {
  id: string;
  name: string;
  metric:
    | "hallucination_rate"
    | "p95_latency_ms"
    | "error_rate"
    | "cost_burn_usd"
    | "retrieval_hit_rate";
  comparator: ">" | "<" | ">=" | "<=";
  threshold: number;
  window_minutes: number;
  channel: "email" | "webhook" | "slack";
  target: string;
  active: boolean;
}

export interface AlertEvent {
  id: string;
  rule_id: string;
  rule_name: string;
  value: number;
  fired_at: ISODate;
  resolved_at: ISODate | null;
}

export interface Annotation {
  id: string;
  response_id: string;
  reviewer_id: string;
  label: "good" | "bad" | "needs_review";
  notes: string;
  promoted_to_golden: boolean;
  created_at: ISODate;
}

export interface AdminUser {
  id: string;
  email: string;
  role: "admin" | "user";
  created_at: ISODate;
}

// ============================================================================
// API request/response shapes used by the data layer
// ============================================================================

export interface DateRange {
  from: Date;
  to: Date;
}

export interface QueryFilters extends Partial<DateRange> {
  promptVersionId?: string;
  model?: string;
  minJudgeScore?: number; // 0..1, applied to faithfulness
  search?: string;
  status?: QueryStatus;
  limit?: number;
}

export interface KpiSnapshot {
  total_queries: number;
  total_seekers: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  hallucination_rate: number; // 0..1
  serene_mind_trigger_rate: number; // 0..1
  thumbs_up_rate: number; // 0..1
  estimated_cost_usd: number;
  estimated_cost_inr?: number;
  error_rate: number; // 0..1
  retrieval_hit_rate: number; // 0..1
}

export type TimeseriesMetric =
  | "queries"
  | "p50_latency_ms"
  | "p95_latency_ms"
  | "hallucination_rate"
  | "cost_usd"
  | "thumbs_up_rate"
  | "retrieval_hit_rate";

export interface TimeseriesPoint {
  bucket: ISODate;
  value: number;
}

export interface QueryTrace {
  query: ChatQuery;
  prompt: PromptVersion;
  retrieval: RetrievalEvent | null;
  response: ChatResponse | null;
  spans: TraceSpan[];
  triggers: TriggerEvent[];
  feedback: UserFeedback | null;
  safety: SafetyEvent[];
}

export type ChatTrace = ChatQuery;
export type DataPoint = TimeseriesPoint;
export type TopicCluster = QueryCluster;

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  status: "active" | "inactive" | "warming";
  latency_p50: number;
  cost_per_1k: number;
}

export interface RetrievalHealth {
  total_retrievals: number;
  hit_rate: number;
  empty_retrievals: number;
  avg_top_score: number;
  avg_precision: number;
  avg_recall: number;
  miss_rate: number;
  avg_chunks_per_query: number;
  top_missing_topics: string[];
  sources: { source: string; count: number; avgFaith: number }[];
}

export interface QualityData {
  faithfulness: number;
  relevancy: number;
  safety_score: number;
  manual_review_score: number;
  disagreements: Array<{
    id: string;
    kind: "judge_good_user_bad" | "judge_bad_user_good";
    faithfulness: number;
    response_text: string;
  }>;
  low_confidence: Array<{
    id: string;
    confidence: number;
    response_text: string;
    created_at: ISODate;
  }>;
  abstentions?: {
    crisis_redirect: number;
    serving_contract_violation: number;
    unverified_speaker: number;
    empty_retrieval: number;
    total: number;
    reasons?: Record<string, number>;
  };
}

export interface QueueJob {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  user_id: string;
  created_at: number;
  is_stream: boolean;
  queue_position: number | null;
}

export interface QueueResponse {
  jobs: QueueJob[];
  queue_enabled: boolean;
  total: number;
}

export interface QdrantCollectionInfo {
  points: number;
  indexed_vectors: number;
  status: string;
  vector_size: number | null;
}

export interface Neo4jStats {
  nodes_by_label: Record<string, number>;
  total_nodes: number;
  relationships_by_type: Record<string, number>;
  total_relationships: number;
}

export interface LightRAGStats {
  initialized: boolean;
  embedding_dim: number | null;
  max_embed_tokens: number | null;
  chunk_token_size: number;
  cache_size: number;
}

export interface DataStoreError {
  error: string;
}

export interface DataStoreInfo {
  qdrant: Record<string, QdrantCollectionInfo> | DataStoreError;
  neo4j: Neo4jStats | DataStoreError;
  lightrag: LightRAGStats | DataStoreError;
}

export interface IngestionHealth {
  status: string;
  last_run: ISODate;
  indexed_docs: number;
  failed_docs: number;
  total_runs: number;
  ok: number;
  partial: number;
  failed: number;
  total_chunks: number;
}

// ── Cache Management ─────────────────────────────────────────────────────
export interface CacheTierStats {
  available: boolean;
  size?: number;
  hits?: number;
  misses?: number;
  error?: string;
}

export interface CacheMetrics {
  timestamp: number;
  tiers: {
    hot: CacheTierStats;
    exact: CacheTierStats;
    semantic: CacheTierStats;
  };
}

export interface CacheClearResult {
  status: string;
  tiers: Record<string, string>;
}

export interface OperationsSnapshot {
  sample_size: number;
  failure_count: number;
  failure_rate: number;
  average_latency_ms: number | null;
  cost_estimate_usd: number;
  model_policy_id: string;
  budget_guard_enabled: boolean;
}

// ── Speaker Attribution & Dialogue Types ─────────────────────────────────────
export interface AttributionQueueItem {
  video_id: string;
  title: string;
  youtube_url: string;
  corpus_teacher: string;
  total_conflicts: number;
  crossover_count: number;
  third_party_count: number;
  ambient_count: number;
  decided_count: number;
  status: "reviewed" | "pending_review";
}

export interface AttributionTurn {
  span_id: string;
  audio_start_ms: number;
  audio_end_ms: number;
  slice_duration_ms: number;
  file_duration_ms: number;
  youtube_url: string;
  text: string;
  corpus_teacher: string;
  predicted_guru: string;
  cosine: number;
  margin: number;
  category: "crossover" | "third_party" | "ambient";
  dialogue_role: "teacher" | "guest_speaker" | "seeker" | "devotee_testimonial" | "ambient";
  decision: "reject_span" | "mark_unknown" | "accept_guru_label" | "pending";
  audio_sha256: string;
}

export interface AttributionVideoDetail {
  video_id: string;
  title: string;
  youtube_url: string;
  corpus_teacher: string;
  total_spans: number;
  turns: AttributionTurn[];
}

export interface AttributionTriagePayload {
  action: "promote_teacher" | "convert_to_context_header" | "reject_span" | "mark_unknown";
  assigned_guru?: string;
  interlocutor_role?: string;
  notes?: string;
}

// ── First-person video approval ──────────────────────────────────────────────
export type VideoGrade = "A" | "B" | "C" | "D" | "F";
export type HumanSpeakerCheck = "confirmed" | "rejected";
export type MachineSpeakerStatus = "none" | "partial" | "full" | "n/a";
export type VideoApprovalState = "approved" | "rejected" | "undecided";

export interface VideoHumanDecision {
  video_id: string;
  admin_approved: boolean | null;
  human_speaker_check: HumanSpeakerCheck | null;
  grade: VideoGrade | null;
  notes: string | null;
  updated_by: string;
  updated_at: string;
  reason: string;
}

export interface VideoReviewRow {
  video_id: string;
  title: string;
  channel: string;
  youtube_url: string;
  in_v10: boolean;
  status_note: string;
  /** Machine-measured evidence. Read-only: this page never writes it. */
  machine: {
    source: "live" | "inventory" | "decision_only";
    child_spans: number;
    speaker_verified_spans: number;
    spans_with_voice_method: number;
    min_window_cosine: number | null;
    speaker_status: MachineSpeakerStatus;
    guru_ids: string[];
  };
  decision: VideoHumanDecision | null;
  approval_state: VideoApprovalState;
  serving: "blocked_by_admin" | "gates_apply" | "not_in_v10";
}

export interface VideoReviewSummary {
  videos: number;
  in_v10: number;
  missing_in_v10: number;
  approved: number;
  rejected: number;
  undecided: number;
  blocked_by_admin: number;
  machine_speaker: Record<MachineSpeakerStatus, number>;
}

export interface VideoReviewList {
  total: number;
  limit: number;
  offset: number;
  rows: VideoReviewRow[];
  summary: VideoReviewSummary;
  channels: string[];
  live: boolean;
  collection: string;
}

export interface VideoReviewFilters {
  q?: string;
  channel?: string;
  verified?: Exclude<MachineSpeakerStatus, "n/a">;
  approved?: VideoApprovalState;
  in_v10?: boolean;
  limit?: number;
  offset?: number;
  refresh?: boolean;
}

export interface VideoAuditEntry {
  ts: string;
  actor: string;
  video_id: string;
  reason: string;
  before: VideoHumanDecision | null;
  after: VideoHumanDecision | null;
}

export interface VideoDecisionPayload {
  admin_approved: boolean | null;
  human_speaker_check: HumanSpeakerCheck | null;
  grade: VideoGrade | null;
  notes: string | null;
  reason: string | null;
}

export interface CorpusProvenance {
  point_id: string;
  source_url?: string;
  source_release_version?: number | string;
  content_checksum?: string;
  embedding_model?: string;
  embedding_dimension?: number;
  chunker_version?: string;
  gate_verdict?: string;
  gate_reason?: string;
  asr_method?: string;
  align_method?: string;
  rights_status?: string;
  parent_id?: string;
  parent_id_scheme?: string;
  created_at?: string;
  ingested_at?: string;
  audio_start_ms?: number;
  audio_end_ms?: number;
  speaker?: string;
  payload?: Record<string, unknown>;
}

export interface QdrantIndexHealth {
  status: "green" | "yellow" | "red" | "unknown";
  collection: string;
  points_count?: number;
  segments_count?: number;
  fragmentation_pct?: number;
  optimizer_status?: string;
  dimension?: number;
  error?: string;
}

export interface QdrantOptimizeResult {
  actions: string[];
  before: QdrantIndexHealth;
  after: QdrantIndexHealth;
}

