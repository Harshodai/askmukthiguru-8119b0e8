import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';

const PROTECTED_PREFIXES = ['/chat', '/profile', '/admin'];

/**
 * Global handler for session expiry / sign-out events.
 * Listens to Supabase auth events and shows a toast + redirect when the
 * user is on a protected route.
 */
export const SessionExpiredHandler = () => {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const { data: sub } = supabase.auth.onAuthStateChange((event) => {
      const onProtected = PROTECTED_PREFIXES.some((p) => location.pathname.startsWith(p));
      if (!onProtected) return;

      if (event === 'TOKEN_REFRESHED') return;

      if (event === 'SIGNED_OUT') {
        toast.error('Your session has ended', {
          description: 'Please sign in again to continue.',
        });
        sessionStorage.setItem('auth_redirect_path', location.pathname + location.search);
        navigate('/auth', { replace: true });
      }
    });
    return () => sub.subscription.unsubscribe();
  }, [navigate, location.pathname, location.search]);

  return null;
};
