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
