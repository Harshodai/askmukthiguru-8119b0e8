import { useCallback, useEffect, useRef, useState } from 'react';
import { BACKEND_URL } from '@/lib/backendUrl';
import { userMetricsSchema, type UserMetrics } from '@/lib/metricsSchema';
import { supabase } from '@/integrations/supabase/client';

/** TTL for the module-level metrics cache (skips redundant refetches on remount). */
const CACHE_TTL_MS = 60_000;

/** Zeroed payload — mirrors what the backend returns for anonymous users. */
export const ZEROED_METRICS: UserMetrics = {
  totalConversations: 0,
  totalMessages: 0,
  totalMeditationMinutes: 0,
  averageDistressLevel: null,
  distressTrend: 'flat',
  activeHealingCourse: null,
  courseCompletionPercent: 0,
  lastActiveAt: null,
};

let metricsCache: { data: UserMetrics; ts: number } | null = null;

const freshCacheData = (): UserMetrics | null => {
  if (metricsCache && Date.now() - metricsCache.ts < CACHE_TTL_MS) {
    return metricsCache.data;
  }
  return null;
};

async function getToken(): Promise<string | null> {
  try {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}

/** Backend serializes `UserMetrics` with snake_case keys (pydantic default);
 * the zod schema is camelCase — normalize before parsing. */
function toCamelCase(key: string): string {
  return key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
}

function normalizePayload(data: unknown): unknown {
  if (typeof data !== 'object' || data === null || Array.isArray(data)) return data;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(data)) {
    out[toCamelCase(key)] = value;
  }
  return out;
}

/**
 * Fetches the seeker's `UserMetrics` from `GET /api/metrics` (Supabase JWT).
 *
 * - Parses the payload with `userMetricsSchema` (zod) — mismatches surface as
 *   an `error` instead of corrupt UI.
 * - Caches the latest payload in a module-level TTL cache.
 * - Anonymous users get the zeroed payload (no auth header, or a 401) instead
 *   of an error — the journey card must degrade gracefully.
 * - Refetches on mount and whenever `conversation:updated` fires.
 */
export function useMetrics() {
  const [metrics, setMetrics] = useState<UserMetrics | null>(() => freshCacheData());
  const [loading, setLoading] = useState(() => metricsCache === null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const fetchMetrics = useCallback(async () => {
    const cached = freshCacheData();
    if (cached) {
      setMetrics(cached);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const token = await getToken();
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(`${BACKEND_URL}/api/metrics`, { credentials: 'include', headers });
      if (res.status === 401) {
        // No valid session — backend's anonymous answer is a zeroed payload.
        if (mounted.current) {
          metricsCache = { data: ZEROED_METRICS, ts: Date.now() };
          setMetrics(ZEROED_METRICS);
        }
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: unknown = await res.json();
      const parsed = userMetricsSchema.safeParse(normalizePayload(data));
      if (!parsed.success) throw new Error('Unexpected metrics response');
      if (mounted.current) {
        metricsCache = { data: parsed.data, ts: Date.now() };
        setMetrics(parsed.data);
      }
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : 'Failed to load metrics');
      }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void fetchMetrics();
    const onUpdate = () => {
      void fetchMetrics();
    };
    window.addEventListener('conversation:updated', onUpdate);
    return () => {
      mounted.current = false;
      window.removeEventListener('conversation:updated', onUpdate);
    };
  }, [fetchMetrics]);

  return { metrics, loading, error, refetch: fetchMetrics };
}

/** Test helper — clears the module-level cache between test cases. */
export const resetMetricsCache = (): void => {
  metricsCache = null;
};
