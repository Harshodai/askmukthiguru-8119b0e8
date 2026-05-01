// Real-time data layer over Supabase.
// Swapped from deterministic seeds to real database queries.
import { supabase } from "./supabaseClient";
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

// ============================================================================
// Queries
// ============================================================================

export async function listQueries(filters: QueryFilters = {}): Promise<ChatQuery[]> {
  let query = supabase.from("chat_queries").select("*");

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
  return data as ChatQuery[];
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
    supabase.from("chat_queries").select("*").eq("id", queryId).single(),
    supabase.from("chat_responses").select("*").eq("query_id", queryId).single(),
    supabase.from("retrieval_events").select("*").eq("query_id", queryId).single(),
    supabase.from("trace_spans").select("*").eq("query_id", queryId).order("start_ms"),
    supabase.from("trigger_events").select("*").eq("query_id", queryId),
    supabase.from("safety_events").select("*").eq("query_id", queryId),
  ]);

  if (!query) return null;

  return {
    query: query as ChatQuery,
    prompt: null as any, // Prompt versioning handled by prompt_version_id ref
    retrieval: retrieval as any,
    response: response as any,
    spans: (spans || []) as any,
    triggers: (triggers || []) as any,
    feedback: null, // Placeholder for feedback joins
    safety: (safety || []) as any,
  };
}

// ============================================================================
// KPIs & timeseries
// ============================================================================

export async function getKpis(range: { from?: Date; to?: Date }): Promise<KpiSnapshot> {
  // For a production app, we would use a single RPC call or a Postgres View
  // For now, we perform direct counts to ensure visibility
  let q = supabase.from("chat_queries").select("id, status, latency_ms", { count: "exact" });
  if (range.from) q = q.gte("created_at", range.from.toISOString());
  if (range.to) q = q.lte("created_at", range.to.toISOString());

  const { count: total, data: queries } = await q;
  const ok = (queries || []).filter((x) => x.status === "ok");
  const errors = (queries || []).filter((x) => x.status === "error");
  
  const latencies = ok.map(x => x.latency_ms).sort((a,b) => a-b);
  const p50 = latencies.length ? latencies[Math.floor(latencies.length * 0.5)] : 0;
  const p95 = latencies.length ? latencies[Math.floor(latencies.length * 0.95)] : 0;

  return {
    total_queries: total || 0,
    p50_latency_ms: p50,
    p95_latency_ms: p95,
    hallucination_rate: 0, // Placeholder
    serene_mind_trigger_rate: 0, // Placeholder
    thumbs_up_rate: 0, // Placeholder
    estimated_cost_usd: 0,
    error_rate: total ? errors.length / total : 0,
    retrieval_hit_rate: 0,
  };
}

export async function getTimeseries(opts: {
  metric: TimeseriesMetric;
  from?: Date;
  to?: Date;
  buckets?: number;
}): Promise<TimeseriesPoint[]> {
  // Simple timeseries mock until SQL date_trunc view is added to Supabase
  return [];
}

// ============================================================================
// Other endpoints (Placeholders)
// ============================================================================

export async function listPromptVersions(): Promise<PromptVersion[]> {
  const { data } = await supabase.from("prompt_versions").select("*").order("created_at", { ascending: false });
  return (data || []) as PromptVersion[];
}

export async function listAlertEvents(): Promise<AlertEvent[]> { return []; }
export async function listAlertRules(): Promise<AlertRule[]> { return []; }
export async function listAnnotations(): Promise<Annotation[]> { return []; }
export async function listLogs(): Promise<AppLog[]> { return []; }
export async function listEvalResults(): Promise<EvalResult[]> { return []; }
export async function listEvalRuns(): Promise<EvalRun[]> { return []; }
export async function listGoldenQuestions(): Promise<GoldenQuestion[]> { return []; }
export async function listIngestionRuns(): Promise<IngestionRun[]> { return []; }
export async function listModelPricing(): Promise<ModelPricing[]> { return []; }
export async function listSafetyEvents(): Promise<SafetyEvent[]> { return []; }
export async function listTriggerEvents(): Promise<TriggerEvent[]> { return []; }
export async function listTopicClusters(): Promise<QueryCluster[]> { return []; }
export async function listAdmins(): Promise<AdminUser[]> { return []; }
export async function getRetrievalHealth(): Promise<any> { return null; }
export async function getQualityData(): Promise<any> { return null; }
export async function upsertAlertRule(rule: Partial<AlertRule>): Promise<void> {}
export async function upsertGoldenQuestion(q: Partial<GoldenQuestion>): Promise<void> {}
export async function deleteGoldenQuestion(id: string): Promise<void> {}
export async function promoteAdmin(id: string): Promise<void> {}
export async function demoteAdmin(id: string): Promise<void> {}
export async function upsertModelPricing(p: ModelPricing): Promise<void> {}
export async function askData(query: string): Promise<string> { return "AskData is not yet wired to Supabase."; }

// Missing UI-required placeholders
export async function listModels(): Promise<string[]> { return ["gpt-4o", "sarvam-30b"]; }
export async function listTriggers(): Promise<string[]> { return ["serene_mind", "safety"]; }
export async function getTopFailures(): Promise<any[]> { return []; }
export async function getRagasHeatmap(): Promise<any[]> { return []; }
export async function getTriggerTrend(): Promise<any[]> { return []; }
export async function getSimilarityTrend(): Promise<any[]> { return []; }
export async function getDeadDocs(): Promise<any[]> { return []; }
export async function getEmptyRetrievals(): Promise<any[]> { return []; }
export async function getIngestionHealth(): Promise<any> { return null; }
export async function getPromptMetricsByVersion(id: string): Promise<any> { return null; }
export async function pollLiveFeed(callback: (q: ChatQuery) => void): Promise<() => void> { 
  return () => {}; 
}
export async function activatePromptVersion(id: string): Promise<void> {
  await supabase.from("prompt_versions").update({ active: false }).neq("id", id);
  await supabase.from("prompt_versions").update({ active: true }).eq("id", id);
}

export async function triggerReingest(runId: string): Promise<void> {}
export async function createPromptVersion(p: Partial<PromptVersion>): Promise<PromptVersion> {
  const { data } = await supabase.from("prompt_versions").insert(p).select().single();
  return data as PromptVersion;
}


