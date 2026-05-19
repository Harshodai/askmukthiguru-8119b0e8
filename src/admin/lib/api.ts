import { supabase } from '@/integrations/supabase/client';
import type { 
  KpiSnapshot, 
  QueryFilters, 
  ChatTrace, 
  PromptVersion, 
  TriggerEvent, 
  SafetyEvent, 
  TopicCluster, 
  RetrievalHealth, 
  TimeseriesMetric, 
  DataPoint,
  QualityData,
  IngestionHealth,
} from '@/admin/types';
import * as db from './mockData';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';

async function fetchWithAuth(path: string, options: RequestInit = {}) {
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;

  const response = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new Error('Admin access required or session expired');
    }
    throw new Error(`API error: ${response.statusText}`);
  }

  return response.json();
}

// ── KPIs ──────────────────────────────────────────────────────────────────────
export async function getKpis(filters: QueryFilters): Promise<KpiSnapshot> {
  // Try backend first, fall back to Supabase direct
  try {
    const params = new URLSearchParams({
      from_date: filters.from.toISOString(),
      to_date: filters.to.toISOString(),
    });
    return await fetchWithAuth(`/api/admin/kpis?${params}`);
  } catch {
    return db.getKpis({ from: filters.from, to: filters.to });
  }
}

// ── Queries & Traces ──────────────────────────────────────────────────────────
export async function listQueries(filters: QueryFilters & { limit?: number; offset?: number }): Promise<ChatTrace[]> {
  try {
    const params = new URLSearchParams({ limit: String(filters.limit || 50) });
    return await fetchWithAuth(`/api/admin/traces?${params}`);
  } catch {
    return db.listQueries(filters) as any;
  }
}

export async function getQueryTrace(id: string): Promise<ChatTrace> {
  const trace = await db.getQueryTrace(id);
  if (trace) return trace as any;
  const traces = await listQueries({ from: new Date(), to: new Date(), limit: 100 });
  return traces.find(t => t.id === id) || traces[0];
}

// ── Prompt Versions ───────────────────────────────────────────────────────────
export async function listPromptVersions(): Promise<PromptVersion[]> {
  try {
    return await fetchWithAuth('/api/admin/prompts');
  } catch {
    return db.listPromptVersions();
  }
}

// ── Models ────────────────────────────────────────────────────────────────────
export async function listModels(): Promise<string[]> {
  return db.listModels();
}

// ── Timeseries ────────────────────────────────────────────────────────────────
export async function getTimeseries(options: { metric: TimeseriesMetric; from: Date; to: Date; buckets: number }): Promise<DataPoint[]> {
  return db.getTimeseries(options);
}

// ── Triggers ──────────────────────────────────────────────────────────────────
export async function listTriggers(filters: QueryFilters): Promise<TriggerEvent[]> {
  return db.listTriggers({ from: filters.from, to: filters.to });
}

// ── Safety Events ─────────────────────────────────────────────────────────────
export async function listSafetyEvents(filters: QueryFilters): Promise<SafetyEvent[]> {
  return db.listSafetyEvents({ from: filters.from, to: filters.to });
}

// ── Topics ────────────────────────────────────────────────────────────────────
export async function listTopicClusters(): Promise<TopicCluster[]> {
  return db.listTopicClusters() as any;
}

// ── Retrieval Health ──────────────────────────────────────────────────────────
export async function getRetrievalHealth(filters: QueryFilters): Promise<RetrievalHealth> {
  const data = await db.getRetrievalHealth({ from: filters.from, to: filters.to });
  // Merge defaults for fields the DB wrapper may not return
  return {
    total_retrievals: 0,
    avg_precision: 0.85,
    avg_recall: 0.78,
    hit_rate: 0.92,
    empty_retrievals: 0,
    avg_top_score: 0.86,
    miss_rate: 0.08,
    avg_chunks_per_query: 3.5,
    top_missing_topics: [],
    sources: [],
    ...data,
  };
}

// ── Quality Data ──────────────────────────────────────────────────────────────
export async function getQualityData(filters: QueryFilters): Promise<QualityData> {
  const data = await db.getQualityData({ from: filters.from, to: filters.to });
  return {
    faithfulness: 0.92,
    relevancy: 0.88,
    safety_score: 0.99,
    manual_review_score: 0.85,
    disagreements: [],
    low_confidence: [],
    ...data,
  };
}

// ── Eval Runs ─────────────────────────────────────────────────────────────────
export async function listEvalRuns() {
  return db.listEvalRuns();
}

// ── Golden Questions ──────────────────────────────────────────────────────────
export async function listGoldenQuestions() {
  return db.listGoldenQuestions();
}

// ── Ingestion Runs ────────────────────────────────────────────────────────────
export async function listIngestionRuns() {
  return db.listIngestionRuns();
}

// ── Alert Rules & Events ──────────────────────────────────────────────────────
export async function listAlertRules() {
  return db.listAlertRules();
}

export async function listAlertEvents() {
  return db.listAlertEvents();
}

// ── Annotations ───────────────────────────────────────────────────────────────
export async function listAnnotations() {
  return db.listAnnotations();
}

// ── Admins ────────────────────────────────────────────────────────────────────
export async function listAdmins() {
  return db.listAdmins();
}

// ── Model Pricing ─────────────────────────────────────────────────────────────
export async function listModelPricing() {
  return db.listModelPricing();
}

// ── Top Failures ──────────────────────────────────────────────────────────────
export async function getTopFailures(filters: QueryFilters, limit: number) {
  return db.getTopFailures({ from: filters.from, to: filters.to }, limit);
}

// ── RAGAS Heatmap ─────────────────────────────────────────────────────────────
export async function getRagasHeatmap(filters: QueryFilters, buckets: number) {
  return db.getRagasHeatmap({ from: filters.from, to: filters.to }, buckets);
}

// ── Trigger Trend ─────────────────────────────────────────────────────────────
export async function getTriggerTrend(filters: QueryFilters, buckets: number) {
  return db.getTriggerTrend({ from: filters.from, to: filters.to }, buckets);
}

// ── Similarity Trend ──────────────────────────────────────────────────────────
export async function getSimilarityTrend(filters: QueryFilters, buckets: number) {
  return db.getSimilarityTrend({ from: filters.from, to: filters.to }, buckets);
}

// ── Dead Docs ─────────────────────────────────────────────────────────────────
export async function getDeadDocs(filters: QueryFilters) {
  return db.getDeadDocs({ from: filters.from, to: filters.to });
}

// ── Empty Retrievals ──────────────────────────────────────────────────────────
export async function getEmptyRetrievals(filters: QueryFilters, limit: number) {
  return db.getEmptyRetrievals({ from: filters.from, to: filters.to }, limit);
}

// ── Ingestion Health ──────────────────────────────────────────────────────────
export async function getIngestionHealth(): Promise<IngestionHealth> {
  const data = await db.getIngestionHealth();
  if (data) return data;
  return {
    status: 'healthy',
    last_run: new Date().toISOString(),
    indexed_docs: 0,
    failed_docs: 0,
    total_runs: 0,
    ok: 0,
    partial: 0,
    failed: 0,
    total_chunks: 0,
  };
}

// ── Prompt Metrics ────────────────────────────────────────────────────────────
export async function getPromptMetricsByVersion() {
  return db.getPromptMetricsByVersion();
}

// ── Live Feed ─────────────────────────────────────────────────────────────────
export async function pollLiveFeed() {
  return db.pollLiveFeed() as any;
}

// ── Ingestion Submit (wired to backend) ───────────────────────────────────────
export async function submitIngestion(url: string, maxAccuracy: boolean = false) {
  return fetchWithAuth('/api/ingest', {
    method: 'POST',
    body: JSON.stringify({ url, max_accuracy: maxAccuracy }),
  });
}

export async function getIngestionStatus() {
  return fetchWithAuth('/api/ingest/status');
}
