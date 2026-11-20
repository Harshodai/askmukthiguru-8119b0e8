import { useEffect, useState } from 'react';
import type { SupabaseClient } from '@supabase/supabase-js';
import { supabase } from '@/integrations/supabase/client';

export interface UpcomingEvent {
  id: string;
  title: string;
  description: string | null;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  link_url: string | null;
  image_url: string | null;
  media_url: string | null;
  media_path: string | null;
  media_type: 'audio' | 'video' | null;
}

export const EVENT_COLUMNS = 'id, title, description, starts_at, ends_at, location, link_url, image_url, media_url, media_path, media_type';
const MAX_EVENTS = 5;

// The generated Supabase types predate this table, so query it through an untyped client.
export const eventsTable = () => (supabase as unknown as SupabaseClient).from('upcoming_events');

/** Next few events that have not finished. Row-level security already hides finished ones. */
export function useUpcomingEvents() {
  const [events, setEvents] = useState<UpcomingEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data, error } = await eventsTable()
          .select(EVENT_COLUMNS)
          .order('starts_at', { ascending: true })
          .limit(MAX_EVENTS);
        if (error) {
          console.warn('[useUpcomingEvents] Fetch error:', error.message);
          return;
        }
        if (!cancelled) setEvents((data ?? []) as UpcomingEvent[]);
      } catch (err) {
        console.warn('[useUpcomingEvents] Unexpected error:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { events, loading };
}
