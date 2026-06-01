/* eslint-disable */
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
  // Use maybeSingle() so missing rows return null instead of throwing — fixes
  // drill-down failures when a query has no response/retrieval row yet.
  const [
    { data: query },
    { data: response },
    { data: retrieval },
    { data: spans },
    { data: triggers },
    { data: safety },
  ] = await Promise.all([
    fromUntyped("chat_queries").select("*").eq("id", queryId).maybeSingle(),
    fromUntyped("chat_responses").select("*").eq("query_id", queryId).maybeSingle(),
    fromUntyped("retrieval_events").select("*").eq("query_id", queryId).maybeSingle(),
    fromUntyped("trace_spans").select("*").eq("query_id", queryId).order("start_ms"),
    fromUntyped("trigger_events").select("*").eq("query_id", queryId),
    fromUntyped("safety_events").select("*").eq("query_id", queryId),
  ]);

  if (!query) return null;

  return {
    query: query as ChatQuery,
    prompt: null as unknown as import('@/admin/types').PromptVersion,
    retrieval: (retrieval as any) ?? null,
    response: (response as any) ?? null,
    spans: ((spans as any) ?? []) as any,
    triggers: ((triggers as any) ?? []) as any,
    feedback: null,
    safety: ((safety as any) ?? []) as any,
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
  const { data, error } = await (supabase as any).rpc("list_admins");
  if (error) { console.error("list_admins RPC failed:", error); return []; }
  return ((data as any[]) || []).map((row) => ({
    id: row.id,
    email: row.email,
    role: "admin" as const,
    created_at: row.created_at,
  })) as AdminUser[];
}

// ============================================================================
// Retrieval health, similarity, empty retrievals
// ============================================================================
function aggregateRetrieval(rows: any[]) {
  const sourceMap = new Map<string, { count: number; faithSum: number; faithN: number }>();
  let topScoreSum = 0, topScoreN = 0, empties = 0;
  rows.forEach((r) => {
    const docs: string[] = r.source_docs || [];
    const scores: number[] = r.scores || [];
    if (docs.length === 0) empties++;
    if (scores.length > 0) { topScoreSum += scores[0]; topScoreN++; }
    const cr = r.chat_responses ?? r.chat_queries?.chat_responses;
    const faith = Array.isArray(cr) ? cr[0]?.faithfulness : cr?.faithfulness;
    docs.forEach((src) => {
      const e = sourceMap.get(src) ?? { count: 0, faithSum: 0, faithN: 0 };
      e.count++;
      if (typeof faith === "number") { e.faithSum += faith; e.faithN++; }
      sourceMap.set(src, e);
    });
  });
  const sources = Array.from(sourceMap.entries())
    .map(([source, v]) => ({ source, count: v.count, avgFaith: v.faithN ? v.faithSum / v.faithN : 0 }))
    .sort((a, b) => b.count - a.count);
  const total = rows.length;
  return {
    total_retrievals: total,
    hit_rate: total ? (total - empties) / total : 0,
    empty_retrievals: empties,
    avg_top_score: topScoreN ? topScoreSum / topScoreN : 0,
    avg_precision: 0,
    avg_recall: 0,
    miss_rate: total ? empties / total : 0,
    avg_chunks_per_query: total ? rows.reduce((s, r) => s + (r.source_docs?.length || 0), 0) / total : 0,
    top_missing_topics: [],
    sources,
  };
}

export async function getRetrievalHealth(range?: { from?: Date; to?: Date }): Promise<any> {
  let q = fromUntyped("retrieval_events").select("query_id, source_docs, scores, chat_queries!inner(created_at, chat_responses(faithfulness))");
  if (range?.from) q = q.gte("chat_queries.created_at", range.from.toISOString());
  if (range?.to) q = q.lte("chat_queries.created_at", range.to.toISOString());
  const { data, error } = await q;
  if (error) {
    console.error("Error in getRetrievalHealth:", error);
    const { data: simple } = await fromUntyped("retrieval_events").select("query_id, source_docs, scores, chat_queries!inner(created_at)");
    return aggregateRetrieval((simple || []) as any[]);
  }
  return aggregateRetrieval((data || []) as any[]);
}

// ============================================================================
// Quality (disagreement + low confidence)
// ============================================================================
export async function getQualityData(range?: { from?: Date; to?: Date }): Promise<any> {
  let q = fromUntyped("chat_responses").select("id, response_text, faithfulness, hallucination_flag, confidence, created_at, query_id");
  if (range?.from) q = q.gte("created_at", range.from.toISOString());
  if (range?.to) q = q.lte("created_at", range.to.toISOString());
  const { data } = await q.limit(500);
  const rows = (data || []) as any[];

  const low_confidence = rows
    .filter((r) => typeof r.confidence === "number" && r.confidence < 0.6)
    .sort((a, b) => a.confidence - b.confidence)
    .slice(0, 20)
    .map((r) => ({ id: r.id, confidence: r.confidence, response_text: r.response_text || "", created_at: r.created_at }));

  const { data: fb } = await fromUntyped("feedback_events").select("query_id, rating");
  const fbMap = new Map<string, number>();
  ((fb || []) as any[]).forEach((f) => fbMap.set(f.query_id, f.rating));

  const disagreements: any[] = [];
  rows.forEach((r) => {
    if (!fbMap.has(r.query_id)) return;
    const rating = fbMap.get(r.query_id)!;
    const judgeGood = (r.faithfulness ?? 0) > 0.8;
    if (judgeGood && rating < 0) disagreements.push({ id: r.id, kind: "judge_good_user_bad", faithfulness: r.faithfulness, response_text: r.response_text || "" });
    else if (!judgeGood && rating > 0) disagreements.push({ id: r.id, kind: "judge_bad_user_good", faithfulness: r.faithfulness, response_text: r.response_text || "" });
  });

  return { disagreements: disagreements.slice(0, 20), low_confidence };
}

// ============================================================================
// Timeseries helpers
// ============================================================================
function bucketize<T>(items: T[], from: Date, to: Date, buckets: number, getTime: (r: T) => number) {
  const start = from.getTime(), end = to.getTime();
  const w = Math.max(1, (end - start) / buckets);
  const arr = Array.from({ length: buckets }, (_, i) => ({ bucket: new Date(start + i * w).toISOString(), items: [] as T[] }));
  items.forEach((r) => {
    let idx = Math.floor((getTime(r) - start) / w);
    if (idx < 0) idx = 0; if (idx >= buckets) idx = buckets - 1;
    arr[idx].items.push(r);
  });
  return arr;
}

export async function getRagasHeatmap(range?: { from?: Date; to?: Date }, buckets = 8): Promise<any[]> {
  const from = range?.from ?? new Date(Date.now() - 7 * 86400000);
  const to = range?.to ?? new Date();
  const { data } = await fromUntyped("chat_responses")
    .select("faithfulness, answer_relevancy, context_precision, context_recall, created_at")
    .gte("created_at", from.toISOString()).lte("created_at", to.toISOString());
  const bs = bucketize((data || []) as any[], from, to, buckets, (r) => new Date(r.created_at).getTime());
  return bs.map((b) => {
    const n = b.items.length || 1;
    const avg = (k: string) => b.items.reduce((s: number, r: any) => s + (r[k] ?? 0), 0) / n;
    return {
      bucket: b.bucket,
      faithfulness: avg("faithfulness"),
      answer_relevancy: avg("answer_relevancy"),
      context_precision: avg("context_precision"),
      context_recall: avg("context_recall"),
      count: b.items.length,
    };
  });
}

export async function getTriggerTrend(range?: { from?: Date; to?: Date }, buckets = 14): Promise<any[]> {
  const from = range?.from ?? new Date(Date.now() - buckets * 86400000);
  const to = range?.to ?? new Date();
  const { data } = await fromUntyped("trigger_events").select("trigger_name, created_at")
    .gte("created_at", from.toISOString()).lte("created_at", to.toISOString());
  const bs = bucketize((data || []) as any[], from, to, buckets, (r) => new Date(r.created_at).getTime());
  return bs.map((b) => {
    const out: any = { bucket: b.bucket };
    b.items.forEach((r: any) => { out[r.trigger_name] = (out[r.trigger_name] || 0) + 1; });
    return out;
  });
}

export async function getSimilarityTrend(range?: { from?: Date; to?: Date }, buckets = 14): Promise<any[]> {
  const from = range?.from ?? new Date(Date.now() - buckets * 86400000);
  const to = range?.to ?? new Date();
  const { data } = await fromUntyped("retrieval_events").select("scores, chat_queries!inner(created_at)")
    .gte("chat_queries.created_at", from.toISOString()).lte("chat_queries.created_at", to.toISOString());
  const bs = bucketize((data || []) as any[], from, to, buckets, (r) => new Date(r.chat_queries?.created_at || r.created_at).getTime());
  return bs.map((b) => {
    const scores = b.items.map((r: any) => (r.scores?.[0] ?? 0)).filter((s: number) => s > 0);
    return { bucket: b.bucket, avg_top_score: scores.length ? scores.reduce((s: number, x: number) => s + x, 0) / scores.length : 0 };
  });
}

export async function getDeadDocs(_range?: { from?: Date; to?: Date }): Promise<any[]> {
  // Requires document_registry table populated by ingestion — see BACKEND_INTEGRATION.md
  return [];
}

export async function getEmptyRetrievals(range?: { from?: Date; to?: Date }, limit = 20): Promise<any[]> {
  let q = fromUntyped("retrieval_events").select("query_id, source_docs, scores, chat_queries!inner(created_at, query_text)");
  if (range?.from) q = q.gte("chat_queries.created_at", range.from.toISOString());
  if (range?.to) q = q.lte("chat_queries.created_at", range.to.toISOString());
  const { data } = await q.order("created_at", { referencedTable: "chat_queries", ascending: false });
  return ((data || []) as any[])
    .filter((r) => !r.source_docs || r.source_docs.length === 0 || (r.scores?.[0] ?? 0) < 0.3)
    .slice(0, limit)
    .map((r) => ({
      query_id: r.query_id,
      query_text: r.chat_queries?.query_text || "(unknown)",
      top_score: r.scores?.[0] ?? 0,
      created_at: r.chat_queries?.created_at,
    }));
}

export async function getIngestionHealth(): Promise<any> {
  const { data } = await fromUntyped("ingestion_runs").select("*");
  const runs = (data || []) as IngestionRun[];
  let indexed_docs = 0, failed_docs = 0, ok = 0, partial = 0, failed = 0, total_chunks = 0;
  let last_run = new Date(0).toISOString();
  runs.forEach((r) => {
    total_chunks += r.chunks_added || 0;
    if (r.status === "ok") { ok++; indexed_docs++; }
    else if (r.status === "partial") { partial++; indexed_docs++; }
    else if (r.status === "failed") { failed++; failed_docs++; }
    if (r.created_at && r.created_at > last_run) last_run = r.created_at;
  });
  return {
    status: failed > 0 ? "Degraded" : (runs.length > 0 ? "Healthy" : "Unknown"),
    last_run: last_run === new Date(0).toISOString() ? new Date().toISOString() : last_run,
    indexed_docs, failed_docs, total_runs: runs.length, ok, partial, failed, total_chunks,
  };
}

export async function getPromptMetricsByVersion(): Promise<any[]> {
  const { data: prompts } = await fromUntyped("prompt_versions").select("id, name, version");
  const { data: queries } = await fromUntyped("chat_queries").select("id, prompt_version_id, chat_responses(faithfulness, answer_relevancy, hallucination_flag)");
  const pList = (prompts || []) as any[];
  const qList = (queries || []) as any[];
  return pList.map((p) => {
    const matched = qList.filter((q) => q.prompt_version_id === p.id);
    const resps = matched.flatMap((q) => Array.isArray(q.chat_responses) ? q.chat_responses : (q.chat_responses ? [q.chat_responses] : []));
    const n = resps.length || 1;
    const avg = (k: string) => resps.reduce((s, r) => s + (r[k] ?? 0), 0) / n;
    const hallRate = resps.length ? resps.filter((r) => r.hallucination_flag).length / resps.length : 0;
    return {
      label: `${p.name} v${p.version}`,
      faithfulness: avg("faithfulness"),
      answer_relevancy: avg("answer_relevancy"),
      hallucination_rate: hallRate,
    };
  });
}

export async function pollLiveFeed(): Promise<ChatQuery[]> {
  return listQueries({ limit: 10 });
}

// ============================================================================
// Mutations
// ============================================================================
export async function upsertAlertRule(rule: Partial<AlertRule> & { id?: string }): Promise<void> {
  const payload: any = {
    name: rule.name,
    metric: rule.metric,
    comparator: rule.comparator,
    threshold: rule.threshold,
    active: (rule as any).active ?? true,
    enabled: (rule as any).active ?? true,
    window_minutes: (rule as any).window_minutes ?? 15,
    channel: (rule as any).channel ?? "email",
    target: (rule as any).target ?? "",
  };
  if (rule.id) await fromUntyped("alert_rules").update(payload).eq("id", rule.id);
  else await fromUntyped("alert_rules").insert(payload);
}

export async function upsertGoldenQuestion(q: Partial<GoldenQuestion> & { id?: string }): Promise<void> {
  const payload: any = {
    question: q.question,
    expected_answer: (q as any).expected_answer ?? null,
    tags: q.tags ?? [],
    active: (q as any).active ?? true,
    expected_sources: (q as any).expected_sources ?? [],
  };
  if (q.id) await fromUntyped("golden_questions").update(payload).eq("id", q.id);
  else await fromUntyped("golden_questions").insert(payload);
}

export async function deleteGoldenQuestion(id: string): Promise<void> {
  await fromUntyped("golden_questions").delete().eq("id", id);
}

export async function promoteAdmin(email: string): Promise<void> {
  const { data, error } = await (supabase as any).rpc("promote_admin_by_email", { _email: email });
  if (error) throw error;
  if (data?.ok === false) throw new Error(data.reason || "promote_failed");
}

export async function demoteAdmin(userId: string): Promise<void> {
  const { data, error } = await (supabase as any).rpc("demote_admin_by_id", { _user_id: userId });
  if (error) throw error;
  if (data?.ok === false) throw new Error(data.reason || "demote_failed");
}

export async function upsertModelPricing(p: ModelPricing): Promise<void> {
  await fromUntyped("model_pricing").upsert(
    { model: p.model, input_per_1k: p.input_per_1k, output_per_1k: p.output_per_1k },
    { onConflict: "model" },
  );
}

export async function askData(_query: string): Promise<string> {
  return "AskData requires the FastAPI backend. See BACKEND_INTEGRATION.md → AskData.";
}

export async function listModels(): Promise<string[]> {
  return ["sarvam-30b", "sarvam-105b", "qwen3-30b"];
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
  const { data } = await q;
  if (!data) return [];
  return (data as any[])
    .filter((r) => r.faithfulness !== null && r.answer_relevancy !== null)
    .sort((a, b) => (a.faithfulness + a.answer_relevancy) - (b.faithfulness + b.answer_relevancy))
    .slice(0, limit)
    .map((r) => ({
      query_id: r.query_id || r.id,
      query_text: r.chat_queries?.query_text || "Unknown query",
      faithfulness: r.faithfulness,
      answer_relevancy: r.answer_relevancy,
      created_at: r.created_at || new Date().toISOString(),
      reason: "Low faithfulness score",
    }));
}

export async function triggerReingest(_source: string): Promise<void> {
  // No-op in Lovable Cloud — see BACKEND_INTEGRATION.md → Ingestion API.
}

export async function activatePromptVersion(id: string): Promise<void> {
  await fromUntyped("prompt_versions").update({ active: false }).neq("id", id);
  await fromUntyped("prompt_versions").update({ active: true }).eq("id", id);
}

export async function createPromptVersion(p: Partial<PromptVersion>): Promise<PromptVersion> {
  const { data } = await fromUntyped("prompt_versions")
    .insert({ name: p.name, version: p.version, body: (p as any).content ?? (p as any).body, active: false })
    .select()
    .single();
  return data as PromptVersion;
}
