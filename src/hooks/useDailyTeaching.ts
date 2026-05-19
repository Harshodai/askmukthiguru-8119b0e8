import { useState, useEffect, useCallback } from 'react';
import { supabase } from '@/integrations/supabase/client';

export interface DailyTeachingData {
  id: string;
  image_url: string;
  caption: string | null;
}

/**
 * Fetches the latest active (non-expired) daily teaching from Supabase.
 * Caches in-memory so multiple components on the same page share the result
 * without extra network calls.
 */
let _cachedTeaching: DailyTeachingData | null = null;
let _cacheExpiry = 0;

export function useDailyTeaching() {
  const [teaching, setTeaching] = useState<DailyTeachingData | null>(_cachedTeaching);
  const [loading, setLoading] = useState(!_cachedTeaching);

  const fetchTeaching = useCallback(async () => {
    // Use in-memory cache for 5 minutes
    if (_cachedTeaching && Date.now() < _cacheExpiry) {
      setTeaching(_cachedTeaching);
      setLoading(false);
      return;
    }

    try {
      const now = new Date().toISOString();
      const { data, error } = await supabase
        .from('daily_teachings')
        .select('id, image_url, caption')
        .or(`expires_at.is.null,expires_at.gte.${now}`)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle();

      if (error) {
        console.warn('[useDailyTeaching] Fetch error:', error.message);
        return;
      }

      if (data) {
        const typed = data as DailyTeachingData;
        _cachedTeaching = typed;
        _cacheExpiry = Date.now() + 5 * 60 * 1000; // 5 min
        setTeaching(typed);
      }
    } catch (err) {
      console.warn('[useDailyTeaching] Unexpected error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTeaching();
  }, [fetchTeaching]);

  return { teaching, loading };
}
