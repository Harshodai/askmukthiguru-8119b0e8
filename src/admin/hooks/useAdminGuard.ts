import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { verifyAdminSession } from '@/admin/lib/adminAuth';
import { supabase } from '@/integrations/supabase/client';

async function needsMfaStepUp(): Promise<boolean> {
  try {
    const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    return !!aal && aal.nextLevel === 'aal2' && aal.currentLevel !== 'aal2';
  } catch {
    return false;
  }
}

export function useAdminGuard(): { ready: boolean } {
  const nav = useNavigate();
  const loc = useLocation();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    verifyAdminSession().then(async ({ authenticated }) => {
      if (cancelled) return;
      if (!authenticated) {
        nav(`/admin/login?redirect=${encodeURIComponent(loc.pathname)}`, {
          replace: true,
        });
        return;
      }
      if (await needsMfaStepUp()) {
        if (cancelled) return;
        sessionStorage.setItem('auth_redirect_path', loc.pathname);
        nav('/auth/mfa', { replace: true });
        return;
      }
      if (!cancelled) setReady(true);
    });


    return () => {
      cancelled = true;
    };
  }, [nav, loc.pathname]);

  return { ready };
}
