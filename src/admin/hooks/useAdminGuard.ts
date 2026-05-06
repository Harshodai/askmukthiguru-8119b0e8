import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { verifyAdminSession } from '@/admin/lib/adminAuth';

export function useAdminGuard(): { ready: boolean } {
  const nav = useNavigate();
  const loc = useLocation();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    verifyAdminSession().then(({ authenticated }) => {
      if (cancelled) return;
      if (!authenticated) {
        nav(`/admin/login?redirect=${encodeURIComponent(loc.pathname)}`, {
          replace: true,
        });
      } else {
        setReady(true);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [nav, loc.pathname]);

  return { ready };
}
