import { supabase } from '@/integrations/supabase/client';

export interface WaitlistSubscriber {
  id: string;
  email: string;
  source: string | null;
  consented_at: string;
}

/**
 * Owner-only subscriber read, newest first.
 *
 * Row access is granted by the `waitlist_entries` RLS policy, which requires an
 * authenticated `admin` role at AAL2. A caller without that gets no rows, not a
 * leak. Errors stay generic so no address can travel in an error string.
 */
export async function listWaitlistSubscribers(limit = 200): Promise<WaitlistSubscriber[]> {
  const { data, error } = await supabase
    .from('waitlist_entries')
    .select('id,email,source,consented_at')
    .order('consented_at', { ascending: false })
    .limit(limit);

  if (error) {
    throw new Error('Could not load launch subscribers. Retry, or confirm admin MFA is active.');
  }
  return data ?? [];
}
