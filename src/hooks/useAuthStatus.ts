import { useEffect, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';

export type AuthStatus = 'loading' | 'signed_in' | 'session_expired' | 'anonymous';

export interface AuthStatusState {
  status: AuthStatus;
  email?: string | null;
}

/** Tracks the current Supabase auth session and surfaces `session_expired` on token-refresh failures. */
export function useAuthStatus(): AuthStatusState {
  const [state, setState] = useState<AuthStatusState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (cancelled) return;
      setState({
        status: session?.user ? 'signed_in' : 'anonymous',
        email: session?.user?.email ?? null,
      });
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (cancelled) return;
      if (event === 'TOKEN_REFRESHED' && !session) {
        setState({ status: 'session_expired' });
        return;
      }
      if (event === 'SIGNED_OUT') {
        // Distinguish a real sign-out from expiry: if we previously had a user, treat as expired.
        setState((prev) => ({ status: prev.status === 'signed_in' ? 'session_expired' : 'anonymous' }));
        return;
      }
      setState({
        status: session?.user ? 'signed_in' : 'anonymous',
        email: session?.user?.email ?? null,
      });
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, []);

  return state;
}
