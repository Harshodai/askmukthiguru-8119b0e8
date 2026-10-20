/**
 * useBreathTeaching
 *
 * Fetches an approved, integrity-checked recorded passage for a breathing
 * technique through the first-person serving endpoint. The API never invents
 * a substitute teaching when verified source evidence is unavailable.
 *
 * Results are cached for the browser session so repeated technique switches
 * do not repeat the retrieval request.
 */

import { useState, useEffect, useRef } from 'react';
import { supabase } from '@/integrations/supabase/client';

interface TeachingState {
  teaching: string | null;
  loading: boolean;
  error: boolean;
}

// Browser-session cache: technique_id → teaching string
const _cache = new Map<string, string>();

import { BACKEND_URL } from '@/lib/backendUrl';

export const useBreathTeaching = (techniqueId: string): TeachingState => {
  const [state, setState] = useState<TeachingState>({
    teaching: _cache.get(techniqueId) ?? null,
    loading: !_cache.has(techniqueId),
    error: false,
  });

  const lastFetchedId = useRef<string | null>(null);

  useEffect(() => {
    if (lastFetchedId.current === techniqueId && !state.loading) return;

    // Use cache if available
    if (_cache.has(techniqueId)) {
      setState({ teaching: _cache.get(techniqueId)!, loading: false, error: false });
      lastFetchedId.current = techniqueId;
      return;
    }

    setState((s) => ({ ...s, loading: true, error: false }));
    lastFetchedId.current = techniqueId;

    let cancelled = false;
    const controller = new AbortController();

    (async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        if (cancelled) return;
        const token = session?.access_token;

        if (!token) {
          if (!cancelled) setState({ teaching: null, loading: false, error: false });
          return;
        }

        const res = await fetch(`${BACKEND_URL}/api/breath-teaching/${techniqueId}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        const teaching: string = json.teaching ?? '';

        _cache.set(techniqueId, teaching);

        if (!cancelled) {
          setState({ teaching, loading: false, error: false });
        }
      } catch (err) {
        console.warn(`useBreathTeaching: fetch failed for ${techniqueId}`, err);
        if (!cancelled) {
          setState({ teaching: null, loading: false, error: true });
        }
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [techniqueId, state.loading]);

  return state;
};
