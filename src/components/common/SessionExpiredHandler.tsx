import { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { supabase, isEmailAllowed } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import type { User } from '@supabase/supabase-js';
import { clearMeditationResume } from '@/lib/meditationResume';
import { clearLocalChatData } from '@/lib/chatStorage';
import { PUSH_DEVICE_STORAGE_KEY } from '@/components/common/PushNotificationsManager';
import { BACKEND_URL } from '@/lib/backendUrl';

const PROTECTED_PREFIXES = ['/chat', '/profile', '/admin'];

// Deactivate this device's push token server-side before the session is
// revoked (OH-P1-02 follow-up) — otherwise a logged-out user keeps receiving
// pushes addressed to them on a device someone else may pick up next.
// Best-effort: a failure here must never block sign-out itself.
const unregisterPushDevice = async (): Promise<void> => {
  const raw = localStorage.getItem(PUSH_DEVICE_STORAGE_KEY);
  if (!raw || !BACKEND_URL) return;
  try {
    const { token } = JSON.parse(raw) as { platform: string; token: string };
    const { data: { session } } = await supabase.auth.getSession();
    if (!session?.access_token) return;
    await fetch(`${BACKEND_URL}/api/push/unregister`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ token }),
    });
    localStorage.removeItem(PUSH_DEVICE_STORAGE_KEY);
  } catch (error) {
    console.warn('[SessionExpiredHandler] push unregister failed:', error);
  }
};

// Monkey-patch signOut to track explicit signout events across the app and
// purge per-user local state (meditation resume payload — P1-FE-15).
const originalSignOut = supabase.auth.signOut;
supabase.auth.signOut = async function (...args) {
  sessionStorage.setItem('auth_explicit_signout', 'true');
  clearMeditationResume();
  void clearLocalChatData().catch((error) => {
    console.warn('[SessionExpiredHandler] local chat purge failed:', error);
  });
  await unregisterPushDevice();
  return originalSignOut.apply(this, args);
};

/**
 * Global handler for session expiry / sign-out events.
 * Listens to Supabase auth events and shows a toast + redirect when the
 * user is on a protected route.
 */
export const SessionExpiredHandler = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const lastUserRef = useRef<User | null>(null);

  useEffect(() => {
    const { data: sub } = supabase.auth.onAuthStateChange(async (event, session) => {
      const onProtected = PROTECTED_PREFIXES.some((p) => location.pathname.startsWith(p));

      if (session?.user) {
        lastUserRef.current = session.user;

        // Auto-signout check
        const email = session.user.email;
        const isAllowed = isEmailAllowed(email);
        const isExplicitLogin = sessionStorage.getItem('auth_explicit_login') === 'true';

        if (!isAllowed || (email === 'test@example.com' && !isExplicitLogin)) {
          console.info('[SessionExpiredHandler] Auto-signing out disallowed user:', email);
          await supabase.auth.signOut();
          if (onProtected) {
            navigate('/auth', { replace: true });
          }
          return;
        }
      }

      if (event === 'TOKEN_REFRESHED') return;

      if (event === 'SIGNED_OUT') {
        const isExplicit = sessionStorage.getItem('auth_explicit_signout') === 'true';
        void clearLocalChatData().catch((error) => {
          console.warn('[SessionExpiredHandler] local chat purge failed:', error);
        });
        // Clear the explicit flag
        sessionStorage.removeItem('auth_explicit_signout');

        const wasSignedIn = lastUserRef.current !== null;
        lastUserRef.current = null;

        // Show toast only if there was a previous session AND it wasn't an explicit signout
        if (wasSignedIn && !isExplicit) {
          toast.error('Your session has ended', {
            description: 'Please sign in again to continue.',
          });
          sessionStorage.setItem('auth_redirect_path', location.pathname + location.search);
        }

        // Only redirect to /auth if there was a session that ended, or a signout was explicitly triggered
        if (onProtected && (wasSignedIn || isExplicit)) {
          navigate('/auth', { replace: true });
        }
      }
    });

    return () => sub.subscription.unsubscribe();
  }, [navigate, location.pathname, location.search]);

  return null;
};
