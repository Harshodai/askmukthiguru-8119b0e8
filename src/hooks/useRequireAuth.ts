import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import type { User } from '@supabase/supabase-js';

/**
 * Requires an authenticated session. Redirects to /auth if none found.
 * Returns { user, loading } so the component can show a loading state.
 */
export function useRequireAuth() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        console.log('[useRequireAuth] localStorage keys:', Object.keys(localStorage));
        const { data: { session }, error } = await supabase.auth.getSession();
        console.log('[useRequireAuth] session:', session, 'error:', error);
      } catch (err) {
        console.error('[useRequireAuth] getSession crashed:', err);
      }
      const { data: { session } } = await supabase.auth.getSession();
      if (cancelled) return;
      if (!session?.user) {
        // Save current path for post-login redirect
        if (window.location.pathname !== '/auth') {
          sessionStorage.setItem('auth_redirect_path', window.location.pathname + window.location.search);
        }
        navigate('/auth', { replace: true });
        return;
      }
      setUser(session.user);
      setLoading(false);
    };

    check();

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (cancelled) return;
      if (!session?.user) {
        if (window.location.pathname !== '/auth') {
          sessionStorage.setItem('auth_redirect_path', window.location.pathname + window.location.search);
        }
        navigate('/auth', { replace: true });
        return;
      }
      setUser(session.user);
      setLoading(false);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, [navigate]);

  return { user, loading };
}
