import type { Session, User } from '@supabase/supabase-js';
import { useEffect, useState } from 'react';
import { supabase, isEmailAllowed } from '@/integrations/supabase/client';
import { getAnonSessionToken } from '@/lib/chat/anonSession';

export type AuthMode = 'authenticated' | 'anonymous' | 'loading';

export interface OptionalAuthResult {
  user: User | null;
  loading: boolean;
  mode: AuthMode;
  /** Resolved session id: signed anon token for anonymous users, legacy id otherwise. */
  anonToken: string | null;
}

/**
 * Same session validation as useRequireAuth, but does NOT redirect.
 * Anonymous users are recognised when Supabase has no session and the
 * backend is able to mint a signed anon session token. This lets public
 * routes like /chat render the full UI while still distinguishing auth
 * state for feature gating and quota enforcement.
 */
export function useOptionalAuth(): OptionalAuthResult {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [anonToken, setAnonToken] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Bumped on every session validation so stale async resolutions (e.g. a
    // slow getAnonSessionToken() from a previous onAuthStateChange event) never
    // overwrite state set by a newer one.
    let generation = 0;

    const validateAndSetSession = async (session: Session | null) => {
      const myGeneration = ++generation;
      if (!session?.user) {
        // No Supabase session — try to mint an anonymous session token.
        const token = await getAnonSessionToken();
        if (cancelled || myGeneration !== generation) return;
        setAnonToken(token);
        setUser(null);
        setLoading(false);
        return;
      }

      const email = session.user.email;
      const isAllowed = isEmailAllowed(email);
      const isExplicitLogin = sessionStorage.getItem('auth_explicit_login') === 'true';

      if (!isAllowed || (email === 'test@example.com' && !isExplicitLogin)) {
        // Treat invalid/disallowed sessions as anonymous rather than forcing a redirect.
        const token = await getAnonSessionToken();
        if (cancelled || myGeneration !== generation) return;
        setAnonToken(token);
        setUser(null);
        setLoading(false);
        return;
      }

      if (cancelled || myGeneration !== generation) return;
      setUser(session.user);
      setAnonToken(null);
      setLoading(false);
    };

    const check = async () => {
      const generationAtStart = generation;
      try {
        const { data: { session } } = await supabase.auth.getSession();
        if (cancelled || generation !== generationAtStart) return;
        await validateAndSetSession(session);
      } catch (err) {
        console.error('[useOptionalAuth] getSession crashed:', err);
        if (cancelled || generation !== generationAtStart) return;
        const myGeneration = ++generation;
        const token = await getAnonSessionToken();
        if (cancelled || myGeneration !== generation) return;
        setAnonToken(token);
        setUser(null);
        setLoading(false);
      }
    };

    check();

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (cancelled) return;
      await validateAndSetSession(session);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, []);

  const mode: AuthMode = loading ? 'loading' : user ? 'authenticated' : 'anonymous';
  return { user, loading, mode, anonToken };
}
