// Real-time data layer over Supabase.
// Swapped from deterministic seeds to real database queries.
// NOTE: Many admin tables (chat_queries, prompt_versions, etc.) are not yet
// created in the database. We cast through `as any` to avoid type errors
// until the full admin schema migration is run.
import { supabase } from "@/integrations/supabase/client";
import type {
  AdminUser,
  AlertEvent,
  AlertRule,
  Annotation,
  AppLog,
  ChatQuery,
  EvalResult,
  EvalRun,
  GoldenQuestion,
  IngestionRun,
  KpiSnapshot,
  ModelPricing,
  PromptVersion,
  QueryCluster,
  QueryFilters,
  QueryTrace,
  SafetyEvent,
  TimeseriesMetric,
  TimeseriesPoint,
  TriggerEvent,
} from "../types";

// Helper to query tables not yet in the typed schema
const fromUntyped = (table: string) => (supabase as any).from(table);

// ============================================================================
// Queries
// ============================================================================

export async function listQueries(filters: QueryFilters = {}): Promise<ChatQuery[]> {
  let query = fromUntyped("chat_queries").select("*");

  if (filters.from) query = query.gte("created_at", filters.from.toISOString());
  if (filters.to) query = query.lte("created_at", filters.to.toISOString());
  if (filters.promptVersionId) query = query.eq("prompt_version_id", filters.promptVersionId);
  if (filters.model) query = query.eq("model", filters.model);
  if (filters.status) query = query.eq("status", filters.status);
  if (filters.search) query = query.ilike("query_text", `%${filters.search}%`);

  const { data, error } = await query
    .order("created_at", { ascending: false })
    .limit(filters.limit ?? 200);

  if (error) {
    console.error("Supabase error fetching queries:", error);
    return [];
  }
  return (data || []) as ChatQuery[];
}

export async function getQueryTrace(queryId: string): Promise<QueryTrace | null> {
  const [
    { data: query },
    { data: response },
    { data: retrieval },
    { data: spans },
    { data: triggers },
    { data: safety },
  ] = await Promise.all([
    fromUntyped("chat_queries").select("*").eq("id", queryId).single(),
    fromUntyped("chat_responses").select("*").eq("query_id", queryId).single(),
    fromUntyped("retrieval_events").select("*").eq("query_id", queryId).single(),
    fromUntyped("trace_spans").select("*").eq("query_id", queryId).order("start_ms"),
    fromUntyped("trigger_events").select("*").eq("query_id", queryId),
    fromUntyped("safety_events").select("*").eq("query_id", queryId),
  ]);

  if (!query) return null;

  return {
    query: query as ChatQuery,
    prompt: null as any,
    retrieval: retrieval as any,
    response: response as any,
    spans: (spans || []) as any,
    triggers: (triggers || []) as any,
    feedback: null,
    safety: (safety || []) as any,
  };
}

// ============================================================================
// KPIs & timeseries
// ============================================================================

export async function getKpis(range: { from?: Date; to?: Date }): Promise<KpiSnapshot> {
  let q = fromUntyped("chat_queries").select("id, status, latency_ms", { count: "exact" });
  if (range.from) q = q.gte("created_at", range.from.toISOString());
  if (range.to) q = q.lte("created_at", range.to.toISOString());

  const { count: total, data: queries } = await q;
  const rows = (queries || []) as any[];
  const ok = rows.filter((x) => x.status === "ok");
  const errors = rows.filter((x) => x.status === "error");
  
  const latencies = ok.map((x: any) => x.latency_ms).sort((a: number, b: number) => a - b);
  const p50 = latencies.length ? latencies[Math.floor(latencies.length * 0.5)] : 0;
  const p95 = latencies.length ? latencies[Math.floor(latencies.length * 0.95)] : 0;

  return {
    total_queries: total || 0,
    p50_latency_ms: p50,
    p95_latency_ms: p95,
    hallucination_rate: 0,
    serene_mind_trigger_rate: 0,
    thumbs_up_rate: 0,
    estimated_cost_usd: 0,
    error_rate: total ? errors.length / total : 0,
    retrieval_hit_rate: 0,
  };
}

export async function getTimeseries(_opts: {
  metric: TimeseriesMetric;
  from?: Date;
  to?: Date;
  buckets?: number;
}): Promise<TimeseriesPoint[]> {
  return [];
}

// ============================================================================
// Other endpoints (Placeholders)
// ============================================================================

export async function listPromptVersions(): Promise<PromptVersion[]> {
  const { data } = await fromUntyped("prompt_versions").select("*").order("created_at", { ascending: false });
  return (data || []) as PromptVersion[];
}

export async function listAlertEvents(): Promise<AlertEvent[]> { return []; }
export async function listAlertRules(): Promise<AlertRule[]> { return []; }
export async function listAnnotations(): Promise<Annotation[]> { return []; }
export async function listLogs(_filters?: { level?: string; search?: string; from?: Date; to?: Date }): Promise<AppLog[]> { return []; }
export async function listEvalResults(): Promise<EvalResult[]> { return []; }
export async function listEvalRuns(): Promise<EvalRun[]> { return []; }
export async function listGoldenQuestions(): Promise<GoldenQuestion[]> { return []; }
export async function listIngestionRuns(): Promise<IngestionRun[]> { return []; }
export async function listModelPricing(): Promise<ModelPricing[]> { return []; }
export async function listSafetyEvents(_range?: { from?: Date; to?: Date }): Promise<SafetyEvent[]> { return []; }
export async function listTriggerEvents(): Promise<TriggerEvent[]> { return []; }
export async function listTopicClusters(): Promise<QueryCluster[]> { return []; }
export async function listAdmins(): Promise<AdminUser[]> { return []; }
export async function getRetrievalHealth(_range?: { from?: Date; to?: Date }): Promise<any> { return null; }
export async function getQualityData(_range?: { from?: Date; to?: Date }): Promise<any> { return null; }
export async function upsertAlertRule(_rule: Partial<AlertRule>): Promise<void> {}
export async function upsertGoldenQuestion(_q: Partial<GoldenQuestion>): Promise<void> {}
export async function deleteGoldenQuestion(_id: string): Promise<void> {}
export async function promoteAdmin(_id: string): Promise<void> {}
export async function demoteAdmin(_id: string): Promise<void> {}
export async function upsertModelPricing(_p: ModelPricing): Promise<void> {}
export async function askData(_query: string): Promise<string> { return "AskData is not yet wired."; }

export async function listModels(): Promise<string[]> { return ["gpt-4o", "sarvam-30b"]; }
export async function listTriggers(_range?: { from?: Date; to?: Date }): Promise<TriggerEvent[]> { return []; }
export async function getTopFailures(_range?: { from?: Date; to?: Date }, _limit?: number): Promise<any[]> { return []; }
export async function getRagasHeatmap(_range?: { from?: Date; to?: Date }, _buckets?: number): Promise<any[]> { return []; }
export async function getTriggerTrend(_range?: { from?: Date; to?: Date }, _buckets?: number): Promise<any[]> { return []; }
export async function getSimilarityTrend(_range?: { from?: Date; to?: Date }, _buckets?: number): Promise<any[]> { return []; }
export async function getDeadDocs(_range?: { from?: Date; to?: Date }): Promise<any[]> { return []; }
export async function getEmptyRetrievals(_range?: { from?: Date; to?: Date }, _limit?: number): Promise<any[]> { return []; }
export async function getIngestionHealth(): Promise<any> { return null; }
export async function getPromptMetricsByVersion(): Promise<any> { return null; }
export async function pollLiveFeed(): Promise<ChatQuery[]> { return []; }

export async function activatePromptVersion(id: string): Promise<void> {
  await fromUntyped("prompt_versions").update({ active: false }).neq("id", id);
  await fromUntyped("prompt_versions").update({ active: true }).eq("id", id);
}

export async function triggerReingest(_runId: string): Promise<void> {}
export async function createPromptVersion(p: Partial<PromptVersion>): Promise<PromptVersion> {
  const { data } = await fromUntyped("prompt_versions").insert(p).select().single();
  return data as PromptVersion;
}
