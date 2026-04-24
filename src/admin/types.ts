// Types mirror the eventual Postgres schema 1:1.
// When Lovable Cloud is enabled, these stay; only the data-fetching bodies in
// src/admin/lib/mockData.ts swap from in-memory to supabase.from(...).

export type ISODate = string;

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
  p50_latency_ms: number;
  p95_latency_ms: number;
  hallucination_rate: number; // 0..1
  serene_mind_trigger_rate: number; // 0..1
  thumbs_up_rate: number; // 0..1
  estimated_cost_usd: number;
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
