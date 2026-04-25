// Read-only data layer over the deterministic seed.
// Every function returns Promises so swapping to real Supabase queries later
// is purely a body change — public signatures stay identical.

import { getSeed } from "./seed";
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

const delay = (ms = 100) => new Promise((r) => setTimeout(r, ms));

function inRange(iso: string, from?: Date, to?: Date) {
  const t = new Date(iso).getTime();
  if (from && t < from.getTime()) return false;
  if (to && t > to.getTime()) return false;
  return true;
}

function p(percentile: number, sorted: number[]): number {
  if (sorted.length === 0) return 0;
  const idx = Math.min(sorted.length - 1, Math.floor((percentile / 100) * sorted.length));
  return sorted[idx];
}

// ============================================================================
// Queries
// ============================================================================

export async function listQueries(filters: QueryFilters = {}): Promise<ChatQuery[]> {
  await delay(60);
  const { queries, responses } = getSeed();
  const respByQuery = new Map(responses.map((r) => [r.query_id, r]));
  const search = filters.search?.toLowerCase().trim();

  return queries
    .filter((q) => inRange(q.created_at, filters.from, filters.to))
    .filter((q) => !filters.promptVersionId || q.prompt_version_id === filters.promptVersionId)
    .filter((q) => !filters.model || q.model === filters.model)
    .filter((q) => !filters.status || q.status === filters.status)
    .filter((q) => !search || q.query_text.toLowerCase().includes(search))
    .filter((q) => {
      if (filters.minJudgeScore == null) return true;
      const r = respByQuery.get(q.id);
      return r ? r.faithfulness >= filters.minJudgeScore : false;
    })
    .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
    .slice(0, filters.limit ?? 200);
}

export async function getQueryTrace(queryId: string): Promise<QueryTrace | null> {
  await delay(40);
  const s = getSeed();
  const query = s.queries.find((q) => q.id === queryId);
  if (!query) return null;
  const prompt = s.prompt_versions.find((p) => p.id === query.prompt_version_id)!;
  return {
    query,
    prompt,
    retrieval: s.retrievals.find((r) => r.query_id === queryId) ?? null,
    response: s.responses.find((r) => r.query_id === queryId) ?? null,
    spans: s.spans.filter((sp) => sp.query_id === queryId).sort((a, b) => a.start_ms - b.start_ms),
    triggers: s.triggers.filter((t) => t.query_id === queryId),
    feedback:
      s.feedback.find((f) => {
        const resp = s.responses.find((r) => r.id === f.response_id);
        return resp?.query_id === queryId;
      }) ?? null,
    safety: s.safety_events.filter((e) => e.query_id === queryId),
  };
}

// ============================================================================
// KPIs & timeseries
// ============================================================================

export async function getKpis(range: { from?: Date; to?: Date }): Promise<KpiSnapshot> {
  await delay(50);
  const s = getSeed();
  const queries = s.queries.filter((q) => inRange(q.created_at, range.from, range.to));
  const ok = queries.filter((q) => q.status === "ok");
  const respByQuery = new Map(s.responses.map((r) => [r.query_id, r]));
  const fbByResp = new Map(s.feedback.map((f) => [f.response_id, f]));
  const trgByQuery = new Set(
    s.triggers.filter((t) => t.trigger_name === "serene_mind").map((t) => t.query_id),
  );

  const latencies = ok.map((q) => q.latency_ms).sort((a, b) => a - b);
  const totalCost = queries.reduce((acc, q) => acc + q.cost_estimate, 0);
  const halluc = ok.filter((q) => respByQuery.get(q.id)?.hallucination_flag).length;
  const sereneCount = ok.filter((q) => trgByQuery.has(q.id)).length;
  const fbAll = ok
    .map((q) => respByQuery.get(q.id))
    .filter(Boolean)
    .map((r) => fbByResp.get(r!.id))
    .filter(Boolean) as { rating: number }[];
  const thumbsUp = fbAll.filter((f) => f.rating === 1).length;
  const errors = queries.filter((q) => q.status === "error").length;
  const retrievalsInRange = s.retrievals.filter((r) =>
    queries.some((q) => q.id === r.query_id),
  );
  const hits = retrievalsInRange.filter((r) => r.retrieval_hit).length;

  return {
    total_queries: queries.length,
    p50_latency_ms: p(50, latencies),
    p95_latency_ms: p(95, latencies),
    hallucination_rate: ok.length ? halluc / ok.length : 0,
    serene_mind_trigger_rate: ok.length ? sereneCount / ok.length : 0,
    thumbs_up_rate: fbAll.length ? thumbsUp / fbAll.length : 0,
    estimated_cost_usd: +totalCost.toFixed(4),
    error_rate: queries.length ? errors / queries.length : 0,
    retrieval_hit_rate: retrievalsInRange.length ? hits / retrievalsInRange.length : 0,
  };
}

export async function getTimeseries(opts: {
  metric: TimeseriesMetric;
  from?: Date;
  to?: Date;
  buckets?: number;
}): Promise<TimeseriesPoint[]> {
  await delay(40);
  const { metric, from, to, buckets = 24 } = opts;
  const s = getSeed();
  const fromT = from?.getTime() ?? Date.now() - 7 * 24 * 3600 * 1000;
  const toT = to?.getTime() ?? Date.now();
  const step = (toT - fromT) / buckets;
  const respByQuery = new Map(s.responses.map((r) => [r.query_id, r]));
  const fbByResp = new Map(s.feedback.map((f) => [f.response_id, f]));
  const retrByQuery = new Map(s.retrievals.map((r) => [r.query_id, r]));

  const points: TimeseriesPoint[] = [];
  for (let i = 0; i < buckets; i++) {
    const bStart = fromT + i * step;
    const bEnd = bStart + step;
    const inBucket = s.queries.filter((q) => {
      const t = +new Date(q.created_at);
      return t >= bStart && t < bEnd;
    });
    let value = 0;
    if (metric === "queries") value = inBucket.length;
    else if (metric === "p50_latency_ms")
      value = p(50, inBucket.map((q) => q.latency_ms).sort((a, b) => a - b));
    else if (metric === "p95_latency_ms")
      value = p(95, inBucket.map((q) => q.latency_ms).sort((a, b) => a - b));
    else if (metric === "cost_usd")
      value = +inBucket.reduce((a, q) => a + q.cost_estimate, 0).toFixed(4);
    else if (metric === "hallucination_rate") {
      const ok = inBucket.filter((q) => q.status === "ok");
      const h = ok.filter((q) => respByQuery.get(q.id)?.hallucination_flag).length;
      value = ok.length ? h / ok.length : 0;
    } else if (metric === "thumbs_up_rate") {
      const fbs = inBucket
        .map((q) => respByQuery.get(q.id))
        .filter(Boolean)
        .map((r) => fbByResp.get(r!.id))
        .filter(Boolean) as { rating: number }[];
      value = fbs.length ? fbs.filter((f) => f.rating === 1).length / fbs.length : 0;
    } else if (metric === "retrieval_hit_rate") {
      const rs = inBucket.map((q) => retrByQuery.get(q.id)).filter(Boolean);
      value = rs.length ? rs.filter((r) => r!.retrieval_hit).length / rs.length : 0;
    }
    points.push({ bucket: new Date(bStart).toISOString(), value });
  }
  return points;
}

// ============================================================================
// Reference lists
// ============================================================================

export async function listPromptVersions(): Promise<PromptVersion[]> {
  await delay(20);
  return [...getSeed().prompt_versions].sort(
    (a, b) => +new Date(b.created_at) - +new Date(a.created_at),
  );
}

export async function listModels(): Promise<string[]> {
  await delay(10);
  return Array.from(new Set(getSeed().queries.map((q) => q.model)));
}

// ============================================================================
// Triggers / safety / topics
// ============================================================================

export async function listTriggers(range: { from?: Date; to?: Date }): Promise<TriggerEvent[]> {
  await delay(30);
  return getSeed().triggers.filter((t) => inRange(t.created_at, range.from, range.to));
}

export async function listSafetyEvents(range: {
  from?: Date;
  to?: Date;
}): Promise<SafetyEvent[]> {
  await delay(30);
  return getSeed().safety_events.filter((e) => inRange(e.created_at, range.from, range.to));
}

export async function listTopicClusters(): Promise<QueryCluster[]> {
  await delay(20);
  return getSeed().query_clusters;
}

// ============================================================================
// Retrieval health
// ============================================================================

export async function getRetrievalHealth(range: { from?: Date; to?: Date }) {
  await delay(50);
  const s = getSeed();
  const queries = s.queries.filter((q) => inRange(q.created_at, range.from, range.to));
  const qIds = new Set(queries.map((q) => q.id));
  const retrievals = s.retrievals.filter((r) => qIds.has(r.query_id));
  const respByQuery = new Map(s.responses.map((r) => [r.query_id, r]));

  const sourceStats = new Map<string, { count: number; avgFaith: number; sumFaith: number }>();
  retrievals.forEach((r) => {
    const fa = respByQuery.get(r.query_id)?.faithfulness ?? 0;
    r.source_docs.forEach((src) => {
      const cur = sourceStats.get(src) ?? { count: 0, avgFaith: 0, sumFaith: 0 };
      cur.count++;
      cur.sumFaith += fa;
      cur.avgFaith = cur.sumFaith / cur.count;
      sourceStats.set(src, cur);
    });
  });

  return {
    total_retrievals: retrievals.length,
    hit_rate: retrievals.length
      ? retrievals.filter((r) => r.retrieval_hit).length / retrievals.length
      : 0,
    empty_retrievals: retrievals.filter((r) => !r.retrieval_hit).length,
    avg_top_score: retrievals.length
      ? +(
          retrievals.reduce((a, r) => a + (r.scores[0] ?? 0), 0) / retrievals.length
        ).toFixed(3)
      : 0,
    sources: Array.from(sourceStats.entries())
      .map(([source, v]) => ({ source, ...v }))
      .sort((a, b) => b.count - a.count),
  };
}

// ============================================================================
// Quality: judge vs user disagreement, low confidence
// ============================================================================

export async function getQualityData(range: { from?: Date; to?: Date }) {
  await delay(40);
  const s = getSeed();
  const queries = s.queries.filter((q) => inRange(q.created_at, range.from, range.to));
  const qIds = new Set(queries.map((q) => q.id));
  const responses = s.responses.filter((r) => qIds.has(r.query_id));

  const fbMap = new Map(s.feedback.map((f) => [f.response_id, f]));
  const disagreements = responses
    .map((r) => {
      const fb = fbMap.get(r.id);
      if (!fb) return null;
      const judgeGood = !r.hallucination_flag && r.faithfulness > 0.75;
      if (judgeGood && fb.rating === -1) return { ...r, fb, kind: "judge_good_user_bad" as const };
      if (!judgeGood && fb.rating === 1) return { ...r, fb, kind: "judge_bad_user_good" as const };
      return null;
    })
    .filter(Boolean);

  return {
    disagreements: disagreements as Array<
      (typeof responses)[number] & { fb: any; kind: "judge_good_user_bad" | "judge_bad_user_good" }
    >,
    low_confidence: responses.filter((r) => r.confidence < 0.78).slice(0, 30),
  };
}

// ============================================================================
// Prompts (mutations only mutate in-memory cache)
// ============================================================================

export async function activatePromptVersion(promptVersionId: string): Promise<void> {
  await delay(20);
  const s = getSeed();
  const target = s.prompt_versions.find((p) => p.id === promptVersionId);
  if (!target) return;
  s.prompt_versions
    .filter((p) => p.name === target.name)
    .forEach((p) => (p.active = p.id === promptVersionId));
}

// ============================================================================
// Evals
// ============================================================================

export async function listEvalRuns(): Promise<EvalRun[]> {
  await delay(20);
  return [...getSeed().eval_runs].sort(
    (a, b) => +new Date(b.started_at) - +new Date(a.started_at),
  );
}

export async function listEvalResults(runId: string): Promise<EvalResult[]> {
  await delay(20);
  return getSeed().eval_results.filter((r) => r.eval_run_id === runId);
}

export async function listGoldenQuestions(): Promise<GoldenQuestion[]> {
  await delay(20);
  return [...getSeed().golden_questions];
}

export async function upsertGoldenQuestion(q: GoldenQuestion): Promise<void> {
  await delay(20);
  const s = getSeed();
  const idx = s.golden_questions.findIndex((g) => g.id === q.id);
  if (idx >= 0) s.golden_questions[idx] = q;
  else s.golden_questions.push(q);
}

export async function deleteGoldenQuestion(id: string): Promise<void> {
  await delay(20);
  const s = getSeed();
  const idx = s.golden_questions.findIndex((g) => g.id === id);
  if (idx >= 0) s.golden_questions.splice(idx, 1);
}

// ============================================================================
// Ingestion / logs / alerts / annotations / admins
// ============================================================================

export async function listIngestionRuns(): Promise<IngestionRun[]> {
  await delay(20);
  return [...getSeed().ingestion_runs].sort(
    (a, b) => +new Date(b.created_at) - +new Date(a.created_at),
  );
}

export async function listLogs(filters: {
  level?: string;
  search?: string;
  from?: Date;
  to?: Date;
}): Promise<AppLog[]> {
  await delay(30);
  const search = filters.search?.toLowerCase();
  return getSeed()
    .app_logs.filter((l) => !filters.level || l.level === filters.level)
    .filter((l) => !search || l.message.toLowerCase().includes(search))
    .filter((l) => inRange(l.created_at, filters.from, filters.to))
    .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
}

export async function listAlertRules(): Promise<AlertRule[]> {
  await delay(20);
  return [...getSeed().alert_rules];
}
export async function upsertAlertRule(rule: AlertRule): Promise<void> {
  await delay(20);
  const s = getSeed();
  const idx = s.alert_rules.findIndex((r) => r.id === rule.id);
  if (idx >= 0) s.alert_rules[idx] = rule;
  else s.alert_rules.push(rule);
}
export async function listAlertEvents(): Promise<AlertEvent[]> {
  await delay(20);
  return [...getSeed().alert_events].sort(
    (a, b) => +new Date(b.fired_at) - +new Date(a.fired_at),
  );
}

export async function listAnnotations(): Promise<Annotation[]> {
  await delay(20);
  return [...getSeed().annotations].sort(
    (a, b) => +new Date(b.created_at) - +new Date(a.created_at),
  );
}

export async function listAdmins(): Promise<AdminUser[]> {
  await delay(20);
  return [...getSeed().admins];
}
export async function promoteAdmin(email: string): Promise<void> {
  await delay(20);
  const s = getSeed();
  if (!s.admins.find((a) => a.email === email)) {
    s.admins.push({
      id: `admin_${Date.now()}`,
      email,
      role: "admin",
      created_at: new Date().toISOString(),
    });
  }
}
export async function demoteAdmin(id: string): Promise<void> {
  await delay(20);
  const s = getSeed();
  const idx = s.admins.findIndex((a) => a.id === id);
  if (idx >= 0) s.admins.splice(idx, 1);
}

export async function listModelPricing(): Promise<ModelPricing[]> {
  await delay(20);
  return [...getSeed().model_pricing];
}
export async function upsertModelPricing(p: ModelPricing): Promise<void> {
  await delay(20);
  const s = getSeed();
  const idx = s.model_pricing.findIndex((m) => m.model === p.model);
  if (idx >= 0) s.model_pricing[idx] = p;
  else s.model_pricing.push(p);
}

// ============================================================================
// Extended analytics for deeper page features
// ============================================================================

export interface TopFailure {
  query_id: string;
  query_text: string;
  reason: string;
  faithfulness: number;
  created_at: string;
}

export async function getTopFailures(
  range: { from?: Date; to?: Date },
  limit = 8,
): Promise<TopFailure[]> {
  await delay(40);
  const s = getSeed();
  const queries = s.queries.filter((q) => inRange(q.created_at, range.from, range.to));
  const qIds = new Set(queries.map((q) => q.id));
  const failed = s.responses
    .filter((r) => qIds.has(r.query_id) && (r.hallucination_flag || r.faithfulness < 0.6))
    .sort((a, b) => a.faithfulness - b.faithfulness)
    .slice(0, limit);
  return failed.map((r) => {
    const q = queries.find((qq) => qq.id === r.query_id)!;
    return {
      query_id: q.id,
      query_text: q.query_text,
      reason: r.judge_reasoning,
      faithfulness: r.faithfulness,
      created_at: q.created_at,
    };
  });
}

export interface RagasHeatCell {
  bucket: string;
  metric: "faithfulness" | "answer_relevancy" | "context_precision" | "context_recall";
  value: number;
}

export async function getRagasHeatmap(
  range: { from?: Date; to?: Date },
  buckets = 8,
): Promise<RagasHeatCell[]> {
  await delay(40);
  const s = getSeed();
  const fromT = range.from?.getTime() ?? Date.now() - 7 * DAY;
  const toT = range.to?.getTime() ?? Date.now();
  const step = (toT - fromT) / buckets;
  const respByQuery = new Map(s.responses.map((r) => [r.query_id, r]));
  const cells: RagasHeatCell[] = [];
  const metrics: RagasHeatCell["metric"][] = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
  ];
  for (let i = 0; i < buckets; i++) {
    const bStart = fromT + i * step;
    const bEnd = bStart + step;
    const inB = s.queries.filter((q) => {
      const t = +new Date(q.created_at);
      return t >= bStart && t < bEnd;
    });
    const resps = inB.map((q) => respByQuery.get(q.id)).filter(Boolean) as typeof s.responses;
    metrics.forEach((m) => {
      const v = resps.length ? resps.reduce((a, r) => a + r[m], 0) / resps.length : 0;
      cells.push({ bucket: new Date(bStart).toISOString(), metric: m, value: +v.toFixed(3) });
    });
  }
  return cells;
}

const DAY = 24 * 60 * 60 * 1000;

export interface TriggerTrendPoint {
  bucket: string;
  serene_mind: number;
  fallback: number;
  safety: number;
  meditation: number;
  youtube_link: number;
  guru_handoff: number;
}

export async function getTriggerTrend(
  range: { from?: Date; to?: Date },
  buckets = 14,
): Promise<TriggerTrendPoint[]> {
  await delay(30);
  const s = getSeed();
  const fromT = range.from?.getTime() ?? Date.now() - 14 * DAY;
  const toT = range.to?.getTime() ?? Date.now();
  const step = (toT - fromT) / buckets;
  const out: TriggerTrendPoint[] = [];
  for (let i = 0; i < buckets; i++) {
    const bStart = fromT + i * step;
    const bEnd = bStart + step;
    const slice = s.triggers.filter((t) => {
      const x = +new Date(t.created_at);
      return x >= bStart && x < bEnd;
    });
    out.push({
      bucket: new Date(bStart).toISOString(),
      serene_mind: slice.filter((t) => t.trigger_name === "serene_mind").length,
      fallback: slice.filter((t) => t.trigger_name === "fallback").length,
      safety: slice.filter((t) => t.trigger_name === "safety").length,
      meditation: slice.filter((t) => t.trigger_name === "meditation").length,
      youtube_link: slice.filter((t) => t.trigger_name === "youtube_link").length,
      guru_handoff: slice.filter((t) => t.trigger_name === "guru_handoff").length,
    });
  }
  return out;
}

export interface SimilarityTrendPoint {
  bucket: string;
  avg_top_score: number;
  hit_rate: number;
}

export async function getSimilarityTrend(
  range: { from?: Date; to?: Date },
  buckets = 14,
): Promise<SimilarityTrendPoint[]> {
  await delay(30);
  const s = getSeed();
  const fromT = range.from?.getTime() ?? Date.now() - 14 * DAY;
  const toT = range.to?.getTime() ?? Date.now();
  const step = (toT - fromT) / buckets;
  const qById = new Map(s.queries.map((q) => [q.id, q]));
  const out: SimilarityTrendPoint[] = [];
  for (let i = 0; i < buckets; i++) {
    const bStart = fromT + i * step;
    const bEnd = bStart + step;
    const rs = s.retrievals.filter((r) => {
      const q = qById.get(r.query_id);
      if (!q) return false;
      const x = +new Date(q.created_at);
      return x >= bStart && x < bEnd;
    });
    const avg = rs.length ? rs.reduce((a, r) => a + (r.scores[0] ?? 0), 0) / rs.length : 0;
    const hit = rs.length ? rs.filter((r) => r.retrieval_hit).length / rs.length : 0;
    out.push({
      bucket: new Date(bStart).toISOString(),
      avg_top_score: +avg.toFixed(3),
      hit_rate: +hit.toFixed(3),
    });
  }
  return out;
}

export interface DeadDoc {
  source: string;
  last_seen: string | null;
}

export async function getDeadDocs(range: { from?: Date; to?: Date }): Promise<DeadDoc[]> {
  await delay(30);
  const s = getSeed();
  const queries = s.queries.filter((q) => inRange(q.created_at, range.from, range.to));
  const qIds = new Set(queries.map((q) => q.id));
  const used = new Set<string>();
  s.retrievals
    .filter((r) => qIds.has(r.query_id))
    .forEach((r) => r.source_docs.forEach((d) => used.add(d)));
  const allSources = new Set<string>();
  s.retrievals.forEach((r) => r.source_docs.forEach((d) => allSources.add(d)));
  return Array.from(allSources)
    .filter((src) => !used.has(src))
    .map((source) => ({ source, last_seen: null }));
}

export interface EmptyRetrievalRow {
  query_id: string;
  query_text: string;
  top_score: number;
  created_at: string;
}

export async function getEmptyRetrievals(
  range: { from?: Date; to?: Date },
  limit = 20,
): Promise<EmptyRetrievalRow[]> {
  await delay(30);
  const s = getSeed();
  const queries = s.queries.filter((q) => inRange(q.created_at, range.from, range.to));
  const qById = new Map(queries.map((q) => [q.id, q]));
  return s.retrievals
    .filter((r) => !r.retrieval_hit && qById.has(r.query_id))
    .slice(0, limit)
    .map((r) => {
      const q = qById.get(r.query_id)!;
      return {
        query_id: r.query_id,
        query_text: q.query_text,
        top_score: r.scores[0] ?? 0,
        created_at: q.created_at,
      };
    });
}

export interface IngestionHealth {
  total_runs: number;
  ok: number;
  partial: number;
  failed: number;
  total_chunks: number;
}

export async function getIngestionHealth(): Promise<IngestionHealth> {
  await delay(20);
  const runs = getSeed().ingestion_runs;
  return {
    total_runs: runs.length,
    ok: runs.filter((r) => r.status === "ok").length,
    partial: runs.filter((r) => r.status === "partial").length,
    failed: runs.filter((r) => r.status === "failed").length,
    total_chunks: runs.reduce((a, r) => a + r.chunks_added, 0),
  };
}

export async function triggerReingest(source: string): Promise<{ runId: string }> {
  await delay(150);
  const s = getSeed();
  const run: IngestionRun = {
    id: `ing_${Date.now()}`,
    source,
    chunks_added: Math.floor(Math.random() * 50) + 10,
    embedding_model: "all-MiniLM-L6-v2",
    duration_ms: Math.floor(Math.random() * 5000) + 1500,
    status: "ok",
    error_log: null,
    created_at: new Date().toISOString(),
  };
  s.ingestion_runs.unshift(run);
  return { runId: run.id };
}

export interface PromptMetricsPoint {
  promptVersionId: string;
  label: string;
  faithfulness: number;
  answer_relevancy: number;
  hallucination_rate: number;
  count: number;
}

export async function getPromptMetricsByVersion(): Promise<PromptMetricsPoint[]> {
  await delay(30);
  const s = getSeed();
  const respByQuery = new Map(s.responses.map((r) => [r.query_id, r]));
  const grouped = new Map<string, typeof s.responses>();
  s.queries.forEach((q) => {
    const r = respByQuery.get(q.id);
    if (!r) return;
    const arr = grouped.get(q.prompt_version_id) ?? [];
    arr.push(r);
    grouped.set(q.prompt_version_id, arr);
  });
  return Array.from(grouped.entries()).map(([pvId, rs]) => {
    const pv = s.prompt_versions.find((p) => p.id === pvId);
    const avg = (key: keyof (typeof rs)[number]) =>
      rs.length ? +(rs.reduce((a, r) => a + (r as any)[key], 0) / rs.length).toFixed(3) : 0;
    return {
      promptVersionId: pvId,
      label: pv ? `${pv.name} v${pv.version}` : pvId.slice(0, 6),
      faithfulness: avg("faithfulness"),
      answer_relevancy: avg("answer_relevancy"),
      hallucination_rate: rs.length
        ? +(rs.filter((r) => r.hallucination_flag).length / rs.length).toFixed(3)
        : 0,
      count: rs.length,
    };
  });
}

export interface LiveQueryEvent {
  id: string;
  query_text: string;
  model: string;
  latency_ms: number;
  hallucination: boolean;
  created_at: string;
}

let liveCursor = 0;
export async function pollLiveFeed(): Promise<LiveQueryEvent[]> {
  await delay(30);
  const s = getSeed();
  const sorted = [...s.queries].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
  liveCursor = (liveCursor + 1) % Math.max(1, sorted.length - 8);
  return sorted.slice(liveCursor, liveCursor + 8).map((q) => {
    const r = s.responses.find((x) => x.query_id === q.id);
    return {
      id: q.id,
      query_text: q.query_text,
      model: q.model,
      latency_ms: q.latency_ms,
      hallucination: !!r?.hallucination_flag,
      created_at: q.created_at,
    };
  });
}

// ============================================================================
// AskData — small canned-question stub
// ============================================================================

export async function askData(
  question: string,
): Promise<{ summary: string; rows: Array<Record<string, string | number>> }> {
  await delay(120);
  const s = getSeed();
  const q = question.toLowerCase();
  if (q.includes("hallucinat")) {
    const counts = new Map<string, { total: number; halluc: number }>();
    s.responses.forEach((r) => {
      const query = s.queries.find((qq) => qq.id === r.query_id);
      if (!query) return;
      const cur = counts.get(query.prompt_version_id) ?? { total: 0, halluc: 0 };
      cur.total++;
      if (r.hallucination_flag) cur.halluc++;
      counts.set(query.prompt_version_id, cur);
    });
    return {
      summary: "Hallucination rate per prompt version (last 30d).",
      rows: Array.from(counts.entries())
        .map(([id, v]) => {
          const pv = s.prompt_versions.find((p) => p.id === id);
          return {
            prompt: pv ? `${pv.name} v${pv.version}` : id,
            total: v.total,
            hallucination_rate: +(v.halluc / v.total).toFixed(3),
          };
        })
        .sort((a, b) => +b.hallucination_rate - +a.hallucination_rate),
    };
  }
  if (q.includes("slow") || q.includes("latenc")) {
    const rows = [...s.queries]
      .sort((a, b) => b.latency_ms - a.latency_ms)
      .slice(0, 10)
      .map((q) => ({ id: q.id, query: q.query_text.slice(0, 60), latency_ms: q.latency_ms }));
    return { summary: "Top 10 slowest queries.", rows };
  }
  if (q.includes("serene") || q.includes("trigger")) {
    return {
      summary: "serene_mind trigger count by day (last 7d).",
      rows: Array.from({ length: 7 }, (_, i) => {
        const day = new Date(Date.now() - i * 86_400_000);
        const dayStart = new Date(day.toDateString()).getTime();
        const dayEnd = dayStart + 86_400_000;
        const count = s.triggers.filter(
          (t) =>
            t.trigger_name === "serene_mind" &&
            +new Date(t.created_at) >= dayStart &&
            +new Date(t.created_at) < dayEnd,
        ).length;
        return { date: day.toDateString().slice(4, 10), count };
      }).reverse(),
    };
  }
  return {
    summary:
      "I can answer: hallucination rate by prompt, slowest queries, serene_mind triggers by day.",
    rows: [],
  };
}
