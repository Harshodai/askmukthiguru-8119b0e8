import { useCallback, useEffect, useRef, useState } from 'react';
import { BACKEND_URL } from '@/lib/backendUrl';
import { userMetricsSchema, type UserMetrics } from '@/lib/metricsSchema';
import { supabase } from '@/integrations/supabase/client';

/** TTL for the metrics cache (15 minutes; persists to localStorage to protect Serverless backends). */
export const METRICS_STORAGE_KEY = 'askmukthiguru_user_metrics_v1';
export const CACHE_TTL_MS = 15 * 60_000;

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

interface CacheEntry {
  data: UserMetrics;
  ts: number;
  userId: string | null;
}

let metricsCache: CacheEntry | null = null;
let currentUserId: string | null = null;

export const getMetricsStorageKey = (userId?: string | null): string => {
  return `${METRICS_STORAGE_KEY}_${userId || 'anon'}`;
};

const readPersistedMetrics = (userId?: string | null): CacheEntry | null => {
  if (typeof window === 'undefined') return null;
  try {
    const storage = window.localStorage;
    if (!storage) return null;
    const raw = storage.getItem(getMetricsStorageKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<CacheEntry>;
    if (parsed && typeof parsed.ts === 'number' && parsed.data) {
      if (Date.now() - parsed.ts < CACHE_TTL_MS) {
        return {
          data: parsed.data,
          ts: parsed.ts,
          userId: parsed.userId ?? (userId ?? null),
        };
      }
    }
  } catch {
    // Ignore corrupt storage or storage access errors
  }
  return null;
};

const persistMetrics = (payload: CacheEntry, userId?: string | null): void => {
  metricsCache = payload;
  if (typeof window === 'undefined') return;
  try {
    const storage = window.localStorage;
    storage?.setItem(getMetricsStorageKey(userId), JSON.stringify(payload));
  } catch {
    // Ignore quota or access errors
  }
};

const freshCacheData = (userId?: string | null): UserMetrics | null => {
  if (metricsCache && Date.now() - metricsCache.ts < CACHE_TTL_MS) {
    if (userId === undefined || metricsCache.userId === (userId ?? null)) {
      return metricsCache.data;
    }
  }
  const persisted = readPersistedMetrics(userId ?? null);
  if (persisted && (userId === undefined || persisted.userId === (userId ?? null))) {
    metricsCache = persisted;
    return persisted.data;
  }
  return null;
};

async function getSessionInfo(): Promise<{ token: string | null; userId: string | null }> {
  try {
    const { data } = await supabase.auth.getSession();
    const session = data?.session;
    return {
      token: session?.access_token ?? null,
      userId: session?.user?.id ?? (session?.access_token ? 'authenticated' : null),
    };
  } catch {
    return { token: null, userId: null };
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

// Invalidate in-memory and persisted caches on authentication state transition
if (typeof supabase?.auth?.onAuthStateChange === 'function') {
  try {
    supabase.auth.onAuthStateChange((_event, session) => {
      const nextId = session?.user?.id ?? (session?.access_token ? 'authenticated' : null);
      if (nextId !== currentUserId) {
        currentUserId = nextId;
        resetMetricsCache();
      }
    });
  } catch {
    // Auth client not available or mock environment
  }
}

/**
 * Fetches the seeker's `UserMetrics` from `GET /api/metrics` (Supabase JWT).
 *
 * - Parses the payload with `userMetricsSchema` (zod) — mismatches surface as
 *   an `error` instead of corrupt UI.
 * - Caches the latest payload in a user-scoped TTL cache (memory + localStorage).
 * - Anonymous users get the zeroed payload (no auth header, or a 401) instead
 *   of an error — the journey card must degrade gracefully.
 * - Refetches on mount and whenever `conversation:updated` fires (bypassing TTL cache).
 */
export function useMetrics() {
  const [metrics, setMetrics] = useState<UserMetrics | null>(() => freshCacheData());
  const [loading, setLoading] = useState(() => metricsCache === null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const fetchMetrics = useCallback(async (force = false) => {
    const { token, userId } = await getSessionInfo();
    currentUserId = userId;

    if (!force) {
      const cached = freshCacheData(userId);
      if (cached) {
        setMetrics(cached);
        setLoading(false);
        return;
      }
    }
    try {
      setLoading(true);
      setError(null);
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(`${BACKEND_URL}/api/metrics`, { credentials: 'include', headers });
      if (res.status === 401) {
        // No valid session — backend's anonymous answer is a zeroed payload.
        if (mounted.current) {
          persistMetrics({ data: ZEROED_METRICS, ts: Date.now(), userId }, userId);
          setMetrics(ZEROED_METRICS);
        }
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: unknown = await res.json();
      const parsed = userMetricsSchema.safeParse(normalizePayload(data));
      if (!parsed.success) throw new Error('Unexpected metrics response');
      if (mounted.current) {
        persistMetrics({ data: parsed.data, ts: Date.now(), userId }, userId);
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
    void fetchMetrics(false);
    const onUpdate = () => {
      void fetchMetrics(true);
    };
    window.addEventListener('conversation:updated', onUpdate);
    return () => {
      mounted.current = false;
      window.removeEventListener('conversation:updated', onUpdate);
    };
  }, [fetchMetrics]);

  const refetch = useCallback(() => fetchMetrics(true), [fetchMetrics]);

  return { metrics, loading, error, refetch };
}

/** Test helper — clears the module-level and localStorage cache between test cases. */
export const resetMetricsCache = (): void => {
  metricsCache = null;
  currentUserId = null;
  if (typeof window === 'undefined') return;
  try {
    const storage = window.localStorage;
    if (storage) {
      storage.removeItem(METRICS_STORAGE_KEY);
      for (let i = storage.length - 1; i >= 0; i--) {
        const key = storage.key(i);
        if (key && key.startsWith(METRICS_STORAGE_KEY)) {
          storage.removeItem(key);
        }
      }
    }
  } catch {
    // Ignore
  }
};
