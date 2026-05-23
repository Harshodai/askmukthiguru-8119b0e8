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
  QueryTrace,
  ChatQuery,
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
    () => db.listQueries(filters) as Promise<ChatTrace[]>,
  );
}

export async function getQueryTrace(id: string): Promise<QueryTrace> {
  return withDevFallback(
    'getQueryTrace',
    async () => {
      return await fetchWithAuth(`/api/admin/traces/${id}`);
    },
    async () => {
      const trace = await db.getQueryTrace(id);
      if (!trace) throw new Error(`Trace ${id} not found in mock data`);
      return trace;
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
  return withDevFallback(
    'listModels',
    () => fetchWithAuth('/api/admin/models'),
    () => db.listModels(),
  );
}

// ── Timeseries ──────────────────────────────────────────────────────────────
export async function getTimeseries(options: {
  metric: TimeseriesMetric;
  from: Date;
  to: Date;
  buckets: number;
}): Promise<DataPoint[]> {
  return withDevFallback(
    'getTimeseries',
    async () => {
      const params = new URLSearchParams({
        metric: options.metric,
        from_date: options.from.toISOString(),
        to_date: options.to.toISOString(),
        buckets: String(options.buckets),
      });
      return await fetchWithAuth(`/api/admin/timeseries?${params}`);
    },
    () => db.getTimeseries(options),
  );
}

// ── Triggers ────────────────────────────────────────────────────────────────
export async function listTriggers(filters: QueryFilters): Promise<TriggerEvent[]> {
  return withDevFallback(
    'listTriggers',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
      });
      return await fetchWithAuth(`/api/admin/triggers?${params}`);
    },
    () => db.listTriggers({ from: filters.from, to: filters.to }),
  );
}

// ── Safety Events ───────────────────────────────────────────────────────────
export async function listSafetyEvents(filters: QueryFilters): Promise<SafetyEvent[]> {
  return withDevFallback(
    'listSafetyEvents',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
      });
      return await fetchWithAuth(`/api/admin/safety-events?${params}`);
    },
    () => db.listSafetyEvents({ from: filters.from, to: filters.to }),
  );
}

// ── Topics ──────────────────────────────────────────────────────────────────
export async function listTopicClusters(): Promise<TopicCluster[]> {
  return withDevFallback(
    'listTopicClusters',
    () => fetchWithAuth('/api/admin/topic-clusters'),
    () => db.listTopicClusters() as Promise<TopicCluster[]>,
  );
}

// ── Retrieval Health ────────────────────────────────────────────────────────
export async function getRetrievalHealth(filters: QueryFilters): Promise<RetrievalHealth> {
  return withDevFallback(
    'getRetrievalHealth',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
      });
      return await fetchWithAuth(`/api/admin/retrieval-health?${params}`);
    },
    async () => {
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
    },
  );
}

// ── Quality Data ────────────────────────────────────────────────────────────
export async function getQualityData(filters: QueryFilters): Promise<QualityData> {
  return withDevFallback(
    'getQualityData',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
      });
      return await fetchWithAuth(`/api/admin/quality-data?${params}`);
    },
    async () => {
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
    },
  );
}

// ── Eval Runs ───────────────────────────────────────────────────────────────
export async function listEvalRuns() {
  return withDevFallback(
    'listEvalRuns',
    () => fetchWithAuth('/api/admin/eval-runs'),
    () => db.listEvalRuns(),
  );
}

// ── Golden Questions ────────────────────────────────────────────────────────
export async function listGoldenQuestions() {
  return withDevFallback(
    'listGoldenQuestions',
    () => fetchWithAuth('/api/admin/golden-questions'),
    () => db.listGoldenQuestions(),
  );
}

// ── Ingestion Runs ──────────────────────────────────────────────────────────
export async function listIngestionRuns() {
  return withDevFallback(
    'listIngestionRuns',
    () => fetchWithAuth('/api/admin/ingestion-runs'),
    () => db.listIngestionRuns(),
  );
}

// ── Alert Rules & Events ──────────────────────────────────────────────────────
export async function listAlertRules() {
  return withDevFallback(
    'listAlertRules',
    () => fetchWithAuth('/api/admin/alert-rules'),
    () => db.listAlertRules(),
  );
}

export async function listAlertEvents() {
  return withDevFallback(
    'listAlertEvents',
    () => fetchWithAuth('/api/admin/alert-events'),
    () => db.listAlertEvents(),
  );
}

// ── Annotations ─────────────────────────────────────────────────────────────
export async function listAnnotations() {
  return withDevFallback(
    'listAnnotations',
    () => fetchWithAuth('/api/admin/annotations'),
    () => db.listAnnotations(),
  );
}

// ── Admins ────────────────────────────────────────────────────────────────────
export async function listAdmins() {
  return withDevFallback(
    'listAdmins',
    () => fetchWithAuth('/api/admin/admins'),
    () => db.listAdmins(),
  );
}

// ── Model Pricing ───────────────────────────────────────────────────────────
export async function listModelPricing() {
  return withDevFallback(
    'listModelPricing',
    () => fetchWithAuth('/api/admin/model-pricing'),
    () => db.listModelPricing(),
  );
}

// ── Top Failures ──────────────────────────────────────────────────────────────
export async function getTopFailures(filters: QueryFilters, limit: number) {
  return withDevFallback(
    'getTopFailures',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
        limit: String(limit),
      });
      return await fetchWithAuth(`/api/admin/top-failures?${params}`);
    },
    () => db.getTopFailures({ from: filters.from, to: filters.to }, limit),
  );
}

// ── RAGAS Heatmap ───────────────────────────────────────────────────────────
export async function getRagasHeatmap(filters: QueryFilters, buckets: number) {
  return withDevFallback(
    'getRagasHeatmap',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
        buckets: String(buckets),
      });
      return await fetchWithAuth(`/api/admin/ragas-heatmap?${params}`);
    },
    () => db.getRagasHeatmap({ from: filters.from, to: filters.to }, buckets),
  );
}

// ── Trigger Trend ───────────────────────────────────────────────────────────
export async function getTriggerTrend(filters: QueryFilters, buckets: number) {
  return withDevFallback(
    'getTriggerTrend',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
        buckets: String(buckets),
      });
      return await fetchWithAuth(`/api/admin/trigger-trend?${params}`);
    },
    () => db.getTriggerTrend({ from: filters.from, to: filters.to }, buckets),
  );
}

// ── Similarity Trend ────────────────────────────────────────────────────────
export async function getSimilarityTrend(filters: QueryFilters, buckets: number) {
  return withDevFallback(
    'getSimilarityTrend',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
        buckets: String(buckets),
      });
      return await fetchWithAuth(`/api/admin/similarity-trend?${params}`);
    },
    () => db.getSimilarityTrend({ from: filters.from, to: filters.to }, buckets),
  );
}

// ── Dead Docs ─────────────────────────────────────────────────────────────────
export async function getDeadDocs(filters: QueryFilters) {
  return withDevFallback(
    'getDeadDocs',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
      });
      return await fetchWithAuth(`/api/admin/dead-docs?${params}`);
    },
    () => db.getDeadDocs({ from: filters.from, to: filters.to }),
  );
}

// ── Empty Retrievals ────────────────────────────────────────────────────────
export async function getEmptyRetrievals(filters: QueryFilters, limit: number) {
  return withDevFallback(
    'getEmptyRetrievals',
    async () => {
      const params = new URLSearchParams({
        from_date: filters.from.toISOString(),
        to_date: filters.to.toISOString(),
        limit: String(limit),
      });
      return await fetchWithAuth(`/api/admin/empty-retrievals?${params}`);
    },
    () => db.getEmptyRetrievals({ from: filters.from, to: filters.to }, limit),
  );
}

// ── Ingestion Health ──────────────────────────────────────────────────────────
export async function getIngestionHealth(): Promise<IngestionHealth> {
  return withDevFallback(
    'getIngestionHealth',
    () => fetchWithAuth('/api/admin/ingestion-health'),
    async () => {
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
    },
  );
}

// ── Prompt Metrics ────────────────────────────────────────────────────────────
export async function getPromptMetricsByVersion() {
  return withDevFallback(
    'getPromptMetricsByVersion',
    () => fetchWithAuth('/api/admin/prompt-metrics'),
    () => db.getPromptMetricsByVersion(),
  );
}

// ── Live Feed ─────────────────────────────────────────────────────────────────
export async function pollLiveFeed(): Promise<ChatTrace[]> {
  return withDevFallback(
    'pollLiveFeed',
    () => fetchWithAuth('/api/admin/live-feed'),
    () => db.pollLiveFeed() as Promise<ChatTrace[]>,
  );
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
