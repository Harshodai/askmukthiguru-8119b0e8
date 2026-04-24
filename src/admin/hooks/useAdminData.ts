import { useQuery } from "@tanstack/react-query";
import * as api from "@/admin/lib/mockData";
import { useAdminFilters } from "@/admin/lib/filtersStore";
import type { QueryFilters, TimeseriesMetric } from "@/admin/types";

const useRangeKey = () => {
  const { filters, refreshKey } = useAdminFilters();
  return [filters.from.toISOString(), filters.to.toISOString(), refreshKey] as const;
};

export function useKpis() {
  const { filters } = useAdminFilters();
  const key = useRangeKey();
  return useQuery({
    queryKey: ["admin", "kpis", ...key],
    queryFn: () => api.getKpis({ from: filters.from, to: filters.to }),
  });
}

export function useTimeseries(metric: TimeseriesMetric, buckets = 24) {
  const { filters } = useAdminFilters();
  const key = useRangeKey();
  return useQuery({
    queryKey: ["admin", "ts", metric, buckets, ...key],
    queryFn: () =>
      api.getTimeseries({ metric, from: filters.from, to: filters.to, buckets }),
  });
}

export function useQueries(extra: Omit<QueryFilters, "from" | "to"> = {}) {
  const { filters } = useAdminFilters();
  const key = useRangeKey();
  return useQuery({
    queryKey: ["admin", "queries", JSON.stringify(extra), ...key],
    queryFn: () =>
      api.listQueries({ from: filters.from, to: filters.to, ...extra }),
  });
}

export function useQueryTrace(queryId: string | null) {
  return useQuery({
    queryKey: ["admin", "trace", queryId],
    queryFn: () => (queryId ? api.getQueryTrace(queryId) : Promise.resolve(null)),
    enabled: !!queryId,
  });
}

export function usePromptVersions() {
  return useQuery({
    queryKey: ["admin", "prompts"],
    queryFn: api.listPromptVersions,
  });
}

export function useModels() {
  return useQuery({ queryKey: ["admin", "models"], queryFn: api.listModels });
}

export function useTriggers() {
  const { filters } = useAdminFilters();
  const key = useRangeKey();
  return useQuery({
    queryKey: ["admin", "triggers", ...key],
    queryFn: () => api.listTriggers({ from: filters.from, to: filters.to }),
  });
}

export function useSafetyEvents() {
  const { filters } = useAdminFilters();
  const key = useRangeKey();
  return useQuery({
    queryKey: ["admin", "safety", ...key],
    queryFn: () => api.listSafetyEvents({ from: filters.from, to: filters.to }),
  });
}

export function useTopics() {
  return useQuery({ queryKey: ["admin", "topics"], queryFn: api.listTopicClusters });
}

export function useRetrievalHealth() {
  const { filters } = useAdminFilters();
  const key = useRangeKey();
  return useQuery({
    queryKey: ["admin", "retr-health", ...key],
    queryFn: () => api.getRetrievalHealth({ from: filters.from, to: filters.to }),
  });
}

export function useQuality() {
  const { filters } = useAdminFilters();
  const key = useRangeKey();
  return useQuery({
    queryKey: ["admin", "quality", ...key],
    queryFn: () => api.getQualityData({ from: filters.from, to: filters.to }),
  });
}

export function useEvalRuns() {
  return useQuery({ queryKey: ["admin", "eval-runs"], queryFn: api.listEvalRuns });
}

export function useGoldenQuestions() {
  return useQuery({ queryKey: ["admin", "golden"], queryFn: api.listGoldenQuestions });
}

export function useIngestionRuns() {
  return useQuery({ queryKey: ["admin", "ingestion"], queryFn: api.listIngestionRuns });
}

export function useAlertRules() {
  return useQuery({ queryKey: ["admin", "alert-rules"], queryFn: api.listAlertRules });
}

export function useAlertEvents() {
  return useQuery({ queryKey: ["admin", "alert-events"], queryFn: api.listAlertEvents });
}

export function useAnnotations() {
  return useQuery({ queryKey: ["admin", "annotations"], queryFn: api.listAnnotations });
}

export function useAdmins() {
  return useQuery({ queryKey: ["admin", "admins"], queryFn: api.listAdmins });
}

export function useModelPricing() {
  return useQuery({ queryKey: ["admin", "model-pricing"], queryFn: api.listModelPricing });
}
