import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { verifyAdminSession } from '@/admin/lib/adminAuth';
import { supabase } from '@/integrations/supabase/client';

// Backend admin routes hard-require aal2 (require_aal2 in auth_service.py) —
// there is no bypass. A superuser session that is merely aal1 must reach
// aal2 before any /api/admin/* call will succeed, and getting there needs a
// *verified TOTP factor* to exist first. currentLevel/nextLevel alone can't
// tell "already enrolled, just re-verify this session" apart from "nothing
// enrolled, nowhere to step up to" — for the latter, nextLevel === currentLevel
// (both aal1), which used to read as "no step-up needed" and let a user with
// zero factors past this guard into a dashboard where every tile 403s.
async function classifyMfaState(): Promise<'ok' | 'needs_step_up' | 'needs_enrollment'> {
  try {
    const { data: aal, error: aalError } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    if (aalError) throw aalError;
    if (aal?.currentLevel === 'aal2') return 'ok';
    if (aal?.nextLevel === 'aal2') return 'needs_step_up';

    const { data, error } = await supabase.auth.mfa.listFactors();
    if (error) throw error;
    const hasVerifiedTotp = (data?.totp ?? []).some((f) => f.status === 'verified');
    return hasVerifiedTotp ? 'needs_step_up' : 'needs_enrollment';
  } catch {
    throw new Error('Could not verify security settings. Please retry.');
  }
}

export function useAdminGuard(): { ready: boolean; error: string | null; retry: () => void } {
  const nav = useNavigate();
  const loc = useLocation();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // Not reset to false here: re-verifying on a pathname change must not unmount the admin
    // outlet (and lose page state) on every navigation. Failures below flip `ready` off.
    setError(null);
    const timeout = window.setTimeout(() => {
      cancelled = true;
      setReady(false);
      setError("Access verification timed out. Please retry.");
    }, 10000);

    verifyAdminSession().then(async ({ authenticated }) => {
      if (cancelled) return;
      if (!authenticated) {
        nav(`/admin/login?redirect=${encodeURIComponent(loc.pathname)}`, {
          replace: true,
        });
        return;
      }
      const mfaState = await classifyMfaState();
      if (cancelled) return;
      if (mfaState === 'needs_step_up') {
        sessionStorage.setItem('auth_redirect_path', loc.pathname);
        nav('/auth/mfa', { replace: true });
        return;
      }
      if (mfaState === 'needs_enrollment') {
        nav(`/profile?tab=settings&setup_mfa=1&redirect=${encodeURIComponent(loc.pathname)}`, {
          replace: true,
        });
        return;
      }
      setReady(true);
    }).catch(() => {
      if (!cancelled) {
        setReady(false);
        setError("Could not verify admin access. Please retry.");
      }
    }).finally(() => window.clearTimeout(timeout));


    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [nav, loc.pathname, attempt]);

  return {
    ready,
    error,
    retry: () => {
      setReady(false);
      setAttempt((value) => value + 1);
    },
  };
}
