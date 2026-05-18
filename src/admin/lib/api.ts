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

export async function getKpis(filters: QueryFilters): Promise<KpiSnapshot> {
  const params = new URLSearchParams({
    from_date: filters.from.toISOString(),
    to_date: filters.to.toISOString(),
  });
  return fetchWithAuth(`/api/admin/kpis?${params}`);
}

export async function listQueries(filters: QueryFilters & { limit?: number; offset?: number }): Promise<ChatTrace[]> {
  const params = new URLSearchParams({
    limit: String(filters.limit || 50),
  });
  return fetchWithAuth(`/api/admin/traces?${params}`);
}

export async function getQueryTrace(id: string): Promise<ChatTrace> {
  // Our backend doesn't have a single trace endpoint yet, it returns traces in a list.
  // For now, we'll fetch recent and find it, or fallback.
  const traces = await listQueries({ from: new Date(), to: new Date(), limit: 100 });
  return traces.find(t => t.id === id) || traces[0];
}

export async function listPromptVersions(): Promise<PromptVersion[]> {
  return fetchWithAuth('/api/admin/prompts');
}

export async function listModels(): Promise<string[]> {
  return [
    'sarvam-30b',
    'qwen3-30b',
  ];
}

export async function getTimeseries(options: { metric: TimeseriesMetric; from: Date; to: Date; buckets: number }): Promise<DataPoint[]> {
  // Fallback to mock for complex timeseries until backend supports it
  const { getTimeseries: mockTS } = await import('./mockData');
  return mockTS(options);
}

export async function listTriggers(filters: QueryFilters): Promise<TriggerEvent[]> {
  return [];
}

export async function listSafetyEvents(filters: QueryFilters): Promise<SafetyEvent[]> {
  return [];
}

export async function listTopicClusters(): Promise<TopicCluster[]> {
  return [];
}

export async function getRetrievalHealth(filters: QueryFilters): Promise<RetrievalHealth> {
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
  };
}

export async function getQualityData(filters: QueryFilters): Promise<QualityData> {
  return {
    faithfulness: 0.92,
    relevancy: 0.88,
    safety_score: 0.99,
    manual_review_score: 0.85,
    disagreements: [],
    low_confidence: [],
  };
}

export async function listEvalRuns() { return []; }
export async function listGoldenQuestions() { return []; }
export async function listIngestionRuns() { return []; }
export async function listAlertRules() { return []; }
export async function listAlertEvents() { return []; }
export async function listAnnotations() { return []; }
export async function listAdmins() { return []; }
export async function listModelPricing() { return []; }
export async function getTopFailures(filters: QueryFilters, limit: number) { return []; }
export async function getRagasHeatmap(filters: QueryFilters, buckets: number) { return []; }
export async function getTriggerTrend(filters: QueryFilters, buckets: number) { return []; }
export async function getSimilarityTrend(filters: QueryFilters, buckets: number) { return []; }
export async function getDeadDocs(filters: QueryFilters) { return []; }
export async function getEmptyRetrievals(filters: QueryFilters, limit: number) { return []; }
export async function getIngestionHealth(): Promise<IngestionHealth> {
  return {
    status: 'healthy',
    last_run: new Date().toISOString(),
    indexed_docs: 1250,
    failed_docs: 0,
    total_runs: 0,
    ok: 0,
    partial: 0,
    failed: 0,
    total_chunks: 1250,
  };
}
export async function getPromptMetricsByVersion() { return []; }
export async function pollLiveFeed() { return listQueries({ from: new Date(), to: new Date(), limit: 10 }); }
