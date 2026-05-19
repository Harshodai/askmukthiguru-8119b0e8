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
    prompt: null,
    retrieval: retrieval as any || null,
    response: response as any || null,
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
  // Join with responses to get hallucination and citations, and triggers to get serene mind events
  let q = fromUntyped("chat_queries").select("id, status, latency_ms, cost_estimate, chat_responses(hallucination_flag, citations), trigger_events(trigger_type)");
  if (range.from) q = q.gte("created_at", range.from.toISOString());
  if (range.to) q = q.lte("created_at", range.to.toISOString());

  const { data: queries } = await q;
  const rows = (queries || []) as any[];
  const total = rows.length;
  
  const ok = rows.filter((x) => x.status === "ok");
  const errors = rows.filter((x) => x.status === "error");
  
  const latencies = ok.map((x: any) => x.latency_ms).filter(x => typeof x === 'number').sort((a: number, b: number) => a - b);
  const p50 = latencies.length ? latencies[Math.floor(latencies.length * 0.5)] : 0;
  const p95 = latencies.length ? latencies[Math.floor(latencies.length * 0.95)] : 0;

  let hallucinationCount = 0;
  let retrievalHitCount = 0;
  let sereneMindTriggerCount = 0;
  let totalCost = 0;
  
  rows.forEach(row => {
    // Check responses for hallucination and retrieval hits
    const responses = row.chat_responses || [];
    if (responses.length > 0) {
       const res = responses[0];
       if (res.hallucination_flag) hallucinationCount++;
       
       // A retrieval hit means it cited at least one document
       let citations = res.citations || [];
       if (typeof citations === "string") {
          try { citations = JSON.parse(citations); } catch(e) {}
       }
       if (Array.isArray(citations) && citations.length > 0) {
          retrievalHitCount++;
       }
    }
    
    // Check triggers for DISTRESS/Serene Mind
    const triggers = row.trigger_events || [];
    if (triggers.length > 0 && triggers.some((t: any) => t.trigger_type === 'DISTRESS' || t.trigger_type === 'meditation')) {
       sereneMindTriggerCount++;
    }
    
    if (row.cost_estimate) {
       totalCost += Number(row.cost_estimate);
    }
  });

  const { count: totalSeekers } = await fromUntyped("user_profiles").select("*", { count: 'exact', head: true });

  return {
    total_queries: total || 0,
    total_seekers: totalSeekers || 0,
    p50_latency_ms: p50,
    p95_latency_ms: p95,
    hallucination_rate: total ? hallucinationCount / total : 0,
    serene_mind_trigger_rate: total ? sereneMindTriggerCount / total : 0,
    thumbs_up_rate: 0, // Not yet implemented in schema
    estimated_cost_usd: totalCost,
    error_rate: total ? errors.length / total : 0,
    retrieval_hit_rate: total ? retrievalHitCount / total : 0,
  };
}

export async function getTimeseries(opts: {
  metric: TimeseriesMetric;
  from?: Date;
  to?: Date;
  buckets?: number;
}): Promise<TimeseriesPoint[]> {
  const numBuckets = opts.buckets || 24;
  let q = fromUntyped("chat_queries").select("id, status, latency_ms, cost_estimate, created_at");
  if (opts.from) q = q.gte("created_at", opts.from.toISOString());
  if (opts.to) q = q.lte("created_at", opts.to.toISOString());

  const { data } = await q;
  const queries = (data || []) as ChatQuery[];
  
  // If no date range provided, we can't cleanly bucket
  if (queries.length === 0 || !opts.from || !opts.to) return [];

  const startTime = opts.from.getTime();
  const endTime = opts.to.getTime();
  const bucketMs = (endTime - startTime) / numBuckets;

  const buckets = Array.from({ length: numBuckets }, (_, i) => ({
    bucket: new Date(startTime + i * bucketMs).toISOString(),
    value: 0,
    count: 0,
    latencies: [] as number[]
  }));

  queries.forEach((query) => {
    const qTime = new Date(query.created_at).getTime();
    let bIdx = Math.floor((qTime - startTime) / bucketMs);
    if (bIdx >= numBuckets) bIdx = numBuckets - 1;
    if (bIdx < 0) bIdx = 0;
    
    buckets[bIdx].count++;
    if (opts.metric === "queries") {
      buckets[bIdx].value++;
    } else if (opts.metric === "cost_usd") {
      buckets[bIdx].value += (query.cost_estimate || 0);
    } else if (opts.metric === "p50_latency_ms" || opts.metric === "p95_latency_ms") {
       if (query.status === "ok" && query.latency_ms) {
         buckets[bIdx].latencies.push(query.latency_ms);
       }
    }
  });

  if (opts.metric === "p50_latency_ms" || opts.metric === "p95_latency_ms") {
    buckets.forEach(b => {
      if (b.latencies.length === 0) { b.value = 0; return; }
      b.latencies.sort((a: number, b: number) => a - b);
      if (opts.metric === "p50_latency_ms") b.value = b.latencies[Math.floor(b.latencies.length * 0.5)];
      if (opts.metric === "p95_latency_ms") b.value = b.latencies[Math.floor(b.latencies.length * 0.95)];
    });
  }

  return buckets.map(b => ({ bucket: b.bucket, value: b.value }));
}

// ============================================================================
// Other endpoints
// ============================================================================

export async function listPromptVersions(): Promise<PromptVersion[]> {
  const { data } = await fromUntyped("prompt_versions").select("*").order("created_at", { ascending: false });
  return (data || []) as PromptVersion[];
}

export async function listAlertEvents(): Promise<AlertEvent[]> {
  const { data } = await fromUntyped("alert_events").select("*").order("fired_at", { ascending: false });
  return (data || []) as AlertEvent[];
}

export async function listAlertRules(): Promise<AlertRule[]> {
  const { data } = await fromUntyped("alert_rules").select("*");
  return (data || []) as AlertRule[];
}

export async function listAnnotations(): Promise<Annotation[]> {
  const { data } = await fromUntyped("annotations").select("*").order("created_at", { ascending: false });
  return (data || []) as Annotation[];
}

export async function listLogs(filters?: { level?: string; search?: string; from?: Date; to?: Date }): Promise<AppLog[]> {
  let q = fromUntyped("app_logs").select("*");
  if (filters?.from) q = q.gte("created_at", filters.from.toISOString());
  if (filters?.to) q = q.lte("created_at", filters.to.toISOString());
  if (filters?.level) q = q.eq("level", filters.level);
  if (filters?.search) q = q.ilike("message", `%${filters.search}%`);
  const { data } = await q.order("created_at", { ascending: false }).limit(200);
  return (data || []) as AppLog[];
}

export async function listEvalResults(): Promise<EvalResult[]> {
  const { data } = await fromUntyped("eval_results").select("*");
  return (data || []) as EvalResult[];
}

export async function listEvalRuns(): Promise<EvalRun[]> {
  const { data } = await fromUntyped("eval_runs").select("*").order("started_at", { ascending: false });
  return (data || []) as EvalRun[];
}

export async function listGoldenQuestions(): Promise<GoldenQuestion[]> {
  const { data } = await fromUntyped("golden_questions").select("*");
  return (data || []) as GoldenQuestion[];
}

export async function listIngestionRuns(): Promise<IngestionRun[]> {
  const { data } = await fromUntyped("ingestion_runs").select("*").order("created_at", { ascending: false });
  return (data || []) as IngestionRun[];
}

export async function listModelPricing(): Promise<ModelPricing[]> {
  const { data } = await fromUntyped("model_pricing").select("*");
  return (data || []) as ModelPricing[];
}

export async function listSafetyEvents(range?: { from?: Date; to?: Date }): Promise<SafetyEvent[]> {
  let q = fromUntyped("safety_events").select("*");
  if (range?.from) q = q.gte("created_at", range.from.toISOString());
  if (range?.to) q = q.lte("created_at", range.to.toISOString());
  const { data } = await q.order("created_at", { ascending: false }).limit(100);
  return (data || []) as SafetyEvent[];
}

export async function listTriggerEvents(): Promise<TriggerEvent[]> {
  const { data } = await fromUntyped("trigger_events").select("*").order("created_at", { ascending: false });
  return (data || []) as TriggerEvent[];
}

export async function listTopicClusters(): Promise<QueryCluster[]> {
  const { data } = await fromUntyped("query_clusters").select("*");
  return (data || []) as QueryCluster[];
}

export async function listAdmins(): Promise<AdminUser[]> {
  const { data } = await fromUntyped("user_roles").select("*, auth_users:user_id(email)").eq("role", "admin");
  return (data || []).map((row: any) => ({
    id: row.user_id,
    email: row.auth_users?.email || "Unknown",
    role: row.role,
    created_at: "2024-01-01T00:00:00Z"
  })) as AdminUser[];
}

export async function getRetrievalHealth(range?: { from?: Date; to?: Date }): Promise<any> { return { sources: [] }; }
export async function getQualityData(range?: { from?: Date; to?: Date }): Promise<any> { return { metrics: [] }; }
export async function upsertAlertRule(rule: Partial<AlertRule>): Promise<void> {}
export async function upsertGoldenQuestion(q: Partial<GoldenQuestion>): Promise<void> {}
export async function deleteGoldenQuestion(id: string): Promise<void> {}
export async function promoteAdmin(id: string): Promise<void> {}
export async function demoteAdmin(id: string): Promise<void> {}
export async function upsertModelPricing(p: ModelPricing): Promise<void> {}
export async function askData(query: string): Promise<string> { return "AskData is not yet wired."; }

export async function listModels(): Promise<string[]> {
  return ["sarvam-30b", "qwen3-30b"]; 
}

export async function listTriggers(range?: { from?: Date; to?: Date }): Promise<TriggerEvent[]> {
  let q = fromUntyped("trigger_events").select("*");
  if (range?.from) q = q.gte("created_at", range.from.toISOString());
  if (range?.to) q = q.lte("created_at", range.to.toISOString());
  const { data } = await q.order("created_at", { ascending: false }).limit(200);
  return (data || []) as TriggerEvent[];
}

export async function getTopFailures(range?: { from?: Date; to?: Date }, limit = 8): Promise<any[]> {
  let q = fromUntyped("chat_responses").select("*, chat_queries(*)");
  if (range?.from) q = q.gte("created_at", range.from.toISOString());
  if (range?.to) q = q.lte("created_at", range.to.toISOString());
  
  // Sort by lowest faithfulness + relevancy
  const { data } = await q;
  if (!data) return [];
  
  return data
    .filter((r: any) => r.faithfulness !== null && r.answer_relevancy !== null)
    .sort((a: any, b: any) => (a.faithfulness + a.answer_relevancy) - (b.faithfulness + b.answer_relevancy))
    .slice(0, limit)
    .map((r: any) => ({
      query_id: r.query_id || r.id,
      query_text: r.chat_queries?.query_text || "Unknown query",
      faithfulness: r.faithfulness,
      answer_relevancy: r.answer_relevancy,
      created_at: r.created_at || new Date().toISOString(),
      reason: "Low faithfulness score"
    }));
}

export async function getRagasHeatmap(range?: { from?: Date; to?: Date }, buckets = 8): Promise<any[]> { return []; }
export async function getTriggerTrend(range?: { from?: Date; to?: Date }, buckets = 14): Promise<any[]> { return []; }
export async function getSimilarityTrend(range?: { from?: Date; to?: Date }, buckets = 14): Promise<any[]> { return []; }
export async function getDeadDocs(range?: { from?: Date; to?: Date }): Promise<any[]> { return []; }
export async function getEmptyRetrievals(range?: { from?: Date; to?: Date }, limit = 20): Promise<any[]> { return []; }
export async function getIngestionHealth(): Promise<any> {
  const { data } = await fromUntyped("ingestion_runs").select("*");
  const runs = (data || []) as IngestionRun[];
  
  let indexed_docs = 0;
  let failed_docs = 0;
  let total_runs = runs.length;
  let ok = 0;
  let partial = 0;
  let failed = 0;
  let total_chunks = 0;
  let last_run = new Date(0).toISOString();

  runs.forEach(r => {
    total_chunks += r.chunks_added || 0;
    if (r.status === "ok") {
      ok++;
      indexed_docs++;
    } else if (r.status === "partial") {
      partial++;
      indexed_docs++;
    } else if (r.status === "failed") {
      failed++;
      failed_docs++;
    }
    if (r.created_at && r.created_at > last_run) {
      last_run = r.created_at;
    }
  });

  return {
    status: failed > 0 ? "Degraded" : (total_runs > 0 ? "Healthy" : "Unknown"),
    last_run: last_run === new Date(0).toISOString() ? new Date().toISOString() : last_run,
    indexed_docs,
    failed_docs,
    total_runs,
    ok,
    partial,
    failed,
    total_chunks
  };
}
export async function getPromptMetricsByVersion(): Promise<any> { return null; }
export async function pollLiveFeed(): Promise<ChatQuery[]> {
  return listQueries({ limit: 10 });
}

export async function activatePromptVersion(id: string): Promise<void> {
  await fromUntyped("prompt_versions").update({ active: false }).neq("id", id);
  await fromUntyped("prompt_versions").update({ active: true }).eq("id", id);
}

export async function triggerReingest(_runId: string): Promise<void> {}
export async function createPromptVersion(p: Partial<PromptVersion>): Promise<PromptVersion> {
  const { data } = await fromUntyped("prompt_versions").insert(p).select().single();
  return data as PromptVersion;
}
