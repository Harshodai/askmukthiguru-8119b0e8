/**
 * useBreathTeaching
 *
 * Fetches an approved, integrity-checked recorded passage for a breathing
 * technique through the first-person serving endpoint. The API never invents
 * a substitute teaching when verified source evidence is unavailable.
 *
 * The first-person pipeline owns safe cache reuse and revalidates source eligibility
 * on every request; this hook deliberately does not cache quotes across rights changes.
 */

import { useState, useEffect } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { BACKEND_URL } from '@/lib/backendUrl';

interface TeachingState {
  teaching: string | null;
  loading: boolean;
  error: boolean;
}

export const useBreathTeaching = (techniqueId: string): TeachingState => {
  const [state, setState] = useState<TeachingState>({
    teaching: null,
    loading: true,
    error: false,
  });

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    // Depend only on the technique. Depending on state.loading here would
    // rerun the effect after setState(true) and can duplicate requests.

    setState({ teaching: null, loading: true, error: false });

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
        const json: unknown = await res.json();
        if (
          !json ||
          typeof json !== 'object' ||
          !('teaching' in json) ||
          typeof json.teaching !== 'string' ||
          !json.teaching.trim()
        ) {
          throw new Error('API response did not contain a verified teaching');
        }
        const teaching = json.teaching.trim();

        if (!cancelled) {
          setState({ teaching, loading: false, error: false });
        }
      } catch (err) {
        if (cancelled) return;
        console.warn(`useBreathTeaching: fetch failed for ${techniqueId}`, err);
        setState({ teaching: null, loading: false, error: true });
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [techniqueId]);

  return state;
};
