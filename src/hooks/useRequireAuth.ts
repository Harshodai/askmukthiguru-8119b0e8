import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase, isEmailAllowed } from '@/integrations/supabase/client';
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
    let initialCheckDone = false;

    const handleInvalidSession = async () => {
      if (cancelled) return;
      initialCheckDone = true;
      try {
        await supabase.auth.signOut();
      } catch (err) {
        console.error('[useRequireAuth] signOut failed:', err);
      }
      navigate('/auth', { replace: true });
    };

    const handleNoSession = () => {
      if (cancelled) return;
      initialCheckDone = true;
      if (window.location.pathname !== '/auth') {
        sessionStorage.setItem('auth_redirect_path', window.location.pathname + window.location.search);
      }
      navigate('/auth', { replace: true });
    };

    const requiresMfaStepUp = async (): Promise<boolean> => {
      try {
        const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
        return !!aal && aal.nextLevel === 'aal2' && aal.currentLevel !== 'aal2';
      } catch (err) {
        console.error('[useRequireAuth] AAL check failed:', err);
        return false;
      }
    };

    const validateAndSetSession = async (session: any) => {
      if (!session?.user) {
        handleNoSession();
        return;
      }

      const email = session.user.email;
      const isAllowed = isEmailAllowed(email);
      const isExplicitLogin = sessionStorage.getItem('auth_explicit_login') === 'true';

      if (!isAllowed || (email === 'test@example.com' && !isExplicitLogin)) {
        await handleInvalidSession();
        return;
      }

      // Enforce 2FA step-up on every session load, not just at interactive login.
      if (await requiresMfaStepUp()) {
        if (cancelled) return;
        initialCheckDone = true;
        if (window.location.pathname !== '/auth/mfa') {
          sessionStorage.setItem('auth_redirect_path', window.location.pathname + window.location.search);
          navigate('/auth/mfa', { replace: true });
        }
        return;
      }

      if (cancelled) return;
      setUser(session.user);
      setLoading(false);
      initialCheckDone = true;
    };


    const check = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        if (cancelled) return;
        await validateAndSetSession(session);
      } catch (err) {
        console.error('[useRequireAuth] getSession crashed:', err);
        if (cancelled) return;
        handleNoSession();
      }
    };

    check();

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (cancelled) return;

      if (!session?.user) {
        // Prevent race condition: ignore early SIGNED_OUT events before getSession settles
        if (!initialCheckDone) return;
        handleNoSession();
        return;
      }

      await validateAndSetSession(session);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, [navigate]);

  return { user, loading };
}

