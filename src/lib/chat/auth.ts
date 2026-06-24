import { supabase } from '@/integrations/supabase/client';

let isRefreshingToken = false;
let refreshTokenPromise: Promise<string | null> | null = null;

export async function refreshAccessToken(): Promise<string | null> {
  if (isRefreshingToken && refreshTokenPromise) {
    return refreshTokenPromise;
  }

  isRefreshingToken = true;
  refreshTokenPromise = (async () => {
    try {
      const { data, error } = await supabase.auth.refreshSession();
      if (error || !data.session?.access_token) {
        console.error('Token refresh failed:', error);
        return null;
      }
      return data.session.access_token;
    } catch (err) {
      console.error('Token refresh error:', err);
      return null;
    } finally {
      isRefreshingToken = false;
      refreshTokenPromise = null;
    }
  })();
  return refreshTokenPromise;
}

export async function getAccessToken(): Promise<string | undefined> {
  const { data: { session } } = await supabase.auth.getSession();
  return session?.access_token;
}
