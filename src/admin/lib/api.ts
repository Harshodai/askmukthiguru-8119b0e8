import { supabase } from '@/integrations/supabase/client';
import type {
  KpiSnapshot,
  QueryFilters,
  ChatTrace,
  QueryTrace,
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

/* ── Explicit NODE_ENV check for mock-data guard ─────────────────────────── */
const ALLOW_MOCK = import.meta.env.DEV;

/* ── Auth helper ─────────────────────────────────────────────────────────── */
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
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

/* ── Helper: backend-first with dev-only mock fallback ───────────────────── */
function withDevFallback<T>(
  label: string,
  backendFn: () => Promise<T>,
  mockFn: () => T | Promise<T>,
): Promise<T> {
  return backendFn().catch((err) => {
    if (ALLOW_MOCK) {
      console.warn(`[api] ${label} backend failed, using DEV mock fallback`);
      return Promise.resolve(mockFn());
    }
    throw err;
  });
}

/* ── Helper: throw in production, allow mock only in dev ───────────────── */
function prodRequired<T>(label: string, mockFn: () => T | Promise<T>): Promise<T> {
  if (ALLOW_MOCK) {
    return Promise.resolve(mockFn());
  }
  throw new Error(`${label}: backend endpoint not implemented. Mock data is disallowed in production.`);
}

// ── KPIs ────────────────────────────────────────────────────────────────────
export async function getKpis(filters: QueryFilters): Promise<KpiSnapshot> {
  return withDevFallback(
    'getKpis',
    async () => {
      const params = new URLSearchParams({
        from_date: (filters.from ?? new Date(0)).toISOString(),
        to_date: (filters.to ?? new Date()).toISOString(),
      });
      return await fetchWithAuth(`/api/admin/kpis?${params}`);
    },
    () => db.getKpis({ from: filters.from, to: filters.to }),
  );
}

// ── Queries & Traces ────────────────────────────────────────────────────────
export async function listQueries(
  filters: QueryFilters & { limit?: number; offset?: number },
): Promise<ChatTrace[]> {
  return withDevFallback(
    'listQueries',
    async () => {
      const params = new URLSearchParams({ limit: String(filters.limit || 50) });
      return await fetchWithAuth(`/api/admin/traces?${params}`);
    },
    () => db.listQueries(filters) as any,
  );
}

export async function getQueryTrace(id: string): Promise<QueryTrace> {
  return withDevFallback(
    'getQueryTrace',
    async () => {
      const traces = await listQueries({ from: new Date(), to: new Date(), limit: 100 });
      const trace = traces.find((t) => t.id === id);
      if (!trace) throw new Error(`Trace ${id} not found`);
      return trace as unknown as QueryTrace;
    },
    () => {
      const trace = db.getQueryTrace(id);
      if (trace) return trace as unknown as QueryTrace;
      throw new Error(`Trace ${id} not found in mock data`);
    },
  );
}

// ── Prompt Versions ─────────────────────────────────────────────────────────
export async function listPromptVersions(): Promise<PromptVersion[]> {
  return withDevFallback(
    'listPromptVersions',
    () => fetchWithAuth('/api/admin/prompts'),
    () => db.listPromptVersions(),
  );
}

// ── Models ─────────────────────────────────────────────────────────────────
export async function listModels(): Promise<string[]> {
  return prodRequired('listModels', () => db.listModels());
}

// ── Timeseries ──────────────────────────────────────────────────────────────
export async function getTimeseries(options: {
  metric: TimeseriesMetric;
  from: Date;
  to: Date;
  buckets: number;
}): Promise<DataPoint[]> {
  return prodRequired('getTimeseries', () => db.getTimeseries(options));
}

// ── Triggers ────────────────────────────────────────────────────────────────
export async function listTriggers(filters: QueryFilters): Promise<TriggerEvent[]> {
  return prodRequired('listTriggers', () => db.listTriggers({ from: filters.from, to: filters.to }));
}

// ── Safety Events ───────────────────────────────────────────────────────────
export async function listSafetyEvents(filters: QueryFilters): Promise<SafetyEvent[]> {
  return prodRequired('listSafetyEvents', () => db.listSafetyEvents({ from: filters.from, to: filters.to }));
}

// ── Topics ──────────────────────────────────────────────────────────────────
export async function listTopicClusters(): Promise<TopicCluster[]> {
  return prodRequired('listTopicClusters', () => db.listTopicClusters() as any);
}

// ── Retrieval Health ────────────────────────────────────────────────────────
export async function getRetrievalHealth(filters: QueryFilters): Promise<RetrievalHealth> {
  return prodRequired('getRetrievalHealth', async () => {
    const data = await db.getRetrievalHealth({ from: filters.from, to: filters.to });
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
  });
}

// ── Quality Data ────────────────────────────────────────────────────────────
export async function getQualityData(filters: QueryFilters): Promise<QualityData> {
  return prodRequired('getQualityData', async () => {
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
  });
}

// ── Eval Runs ───────────────────────────────────────────────────────────────
export async function listEvalRuns() {
  return prodRequired('listEvalRuns', () => db.listEvalRuns());
}

// ── Golden Questions ────────────────────────────────────────────────────────
export async function listGoldenQuestions() {
  return prodRequired('listGoldenQuestions', () => db.listGoldenQuestions());
}

// ── Ingestion Runs ──────────────────────────────────────────────────────────
export async function listIngestionRuns() {
  return prodRequired('listIngestionRuns', () => db.listIngestionRuns());
}

// ── Alert Rules & Events ──────────────────────────────────────────────────────
export async function listAlertRules() {
  return prodRequired('listAlertRules', () => db.listAlertRules());
}

export async function listAlertEvents() {
  return prodRequired('listAlertEvents', () => db.listAlertEvents());
}

// ── Annotations ─────────────────────────────────────────────────────────────
export async function listAnnotations() {
  return prodRequired('listAnnotations', () => db.listAnnotations());
}

// ── Admins ────────────────────────────────────────────────────────────────────
export async function listAdmins() {
  return prodRequired('listAdmins', () => db.listAdmins());
}

// ── Model Pricing ───────────────────────────────────────────────────────────
export async function listModelPricing() {
  return prodRequired('listModelPricing', () => db.listModelPricing());
}

// ── Top Failures ──────────────────────────────────────────────────────────────
export async function getTopFailures(filters: QueryFilters, limit: number) {
  return prodRequired('getTopFailures', () => db.getTopFailures({ from: filters.from, to: filters.to }, limit));
}

// ── RAGAS Heatmap ───────────────────────────────────────────────────────────
export async function getRagasHeatmap(filters: QueryFilters, buckets: number) {
  return prodRequired('getRagasHeatmap', () => db.getRagasHeatmap({ from: filters.from, to: filters.to }, buckets));
}

// ── Trigger Trend ───────────────────────────────────────────────────────────
export async function getTriggerTrend(filters: QueryFilters, buckets: number) {
  return prodRequired('getTriggerTrend', () => db.getTriggerTrend({ from: filters.from, to: filters.to }, buckets));
}

// ── Similarity Trend ────────────────────────────────────────────────────────
export async function getSimilarityTrend(filters: QueryFilters, buckets: number) {
  return prodRequired('getSimilarityTrend', () => db.getSimilarityTrend({ from: filters.from, to: filters.to }, buckets));
}

// ── Dead Docs ─────────────────────────────────────────────────────────────────
export async function getDeadDocs(filters: QueryFilters) {
  return prodRequired('getDeadDocs', () => db.getDeadDocs({ from: filters.from, to: filters.to }));
}

// ── Empty Retrievals ────────────────────────────────────────────────────────
export async function getEmptyRetrievals(filters: QueryFilters, limit: number) {
  return prodRequired('getEmptyRetrievals', () => db.getEmptyRetrievals({ from: filters.from, to: filters.to }, limit));
}

// ── Ingestion Health ──────────────────────────────────────────────────────────
export async function getIngestionHealth(): Promise<IngestionHealth> {
  return prodRequired('getIngestionHealth', async () => {
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
  });
}

// ── Prompt Metrics ────────────────────────────────────────────────────────────
export async function getPromptMetricsByVersion() {
  return prodRequired('getPromptMetricsByVersion', () => db.getPromptMetricsByVersion());
}

// ── Live Feed ─────────────────────────────────────────────────────────────────
export async function pollLiveFeed() {
  return prodRequired('pollLiveFeed', () => db.pollLiveFeed() as any);
}

// ── Ingestion Submit (wired to backend) ─────────────────────────────────────
export async function submitIngestion(url: string, maxAccuracy: boolean = false) {
  return fetchWithAuth('/api/ingest', {
    method: 'POST',
    body: JSON.stringify({ url, max_accuracy: maxAccuracy }),
  });
}

export async function getIngestionStatus() {
  return fetchWithAuth('/api/ingest/status');
}
