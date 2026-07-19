import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { supabase, isEmailAllowed } from '@/integrations/supabase/client';
import { lovable } from '@/integrations/lovable/index';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Sparkles, Mail, Lock, Eye, EyeOff, AlertCircle, User as UserIcon, Loader2, Check } from 'lucide-react';
import { setLanguage } from '@/lib/chat/config';
import { LanguageOnboardingStep } from '@/components/onboarding/LanguageOnboardingStep';
import { Capacitor } from '@capacitor/core';
import type { PluginListenerHandle } from '@capacitor/core';
import { App as CapacitorApp } from '@capacitor/app';
import { Preferences } from '@capacitor/preferences';
import {
  startAuthRun,
  recordStep,
  timeStep,
  endAuthRun,
  getActiveRun,
} from '@/lib/authTelemetry';
import {
  GOOGLE_STEP_KEY,
  ONBOARDED_FLAG_KEY,
  NATIVE_REDIRECT,
  GOOGLE_GSI_SDK_URL,
} from '@/lib/authConstants';

const isNativePlatform = Capacitor.isNativePlatform();

const PREFERENCES_TIMEOUT = 5000;

const nativeWithTimeout = async <T,>(promise: Promise<T>, key: string): Promise<T> => {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`Preferences '${key}' timed out`)), PREFERENCES_TIMEOUT),
    ),
  ]);
};

const getSessionItem = async (key: string): Promise<string | null> => {
  if (isNativePlatform) return nativeWithTimeout(Preferences.get({ key }), key).then(r => r?.value ?? null).catch(() => null);
  return Promise.resolve(sessionStorage.getItem(key));
};
const setSessionItem = async (key: string, value: string): Promise<void> => {
  if (isNativePlatform) { await nativeWithTimeout(Preferences.set({ key, value }), key).catch(() => {}); return; }
  sessionStorage.setItem(key, value);
};
const removeSessionItem = async (key: string): Promise<void> => {
  if (isNativePlatform) { await nativeWithTimeout(Preferences.remove({ key }), key).catch(() => {}); return; }
  sessionStorage.removeItem(key);
};
const removeSessionItems = async (keys: string[]): Promise<void> => {
  await Promise.allSettled(keys.map(k => removeSessionItem(k)));
};
// Sync-only wrapper for useState initializer (never hits async on browser)
const getSessionItemSync = (key: string): string | null => {
  if (isNativePlatform) return null;
  return sessionStorage.getItem(key);
};
// GSI's iframe (accounts.google.com/gsi/iframe) gets "Refused to frame" when
// this page itself is embedded in another iframe (e.g. the Lovable builder
// preview) — same nested-iframe case main.tsx already special-cases for the
// service worker. One Tap/renderButton only run at top level; the plain
// redirect button (handleGoogleSignIn) covers the embedded-preview case.
const isTopLevelFrame = typeof window !== 'undefined' && window.self === window.top;

/** Map Supabase error messages/codes to user-friendly descriptions */
const friendlyError = (err: Error | { message: string }): string => {
  const msg = err.message?.toLowerCase() ?? '';
  if (msg.includes('email rate limit') || msg.includes('over_email_send_rate_limit'))
    return 'Too many attempts. Please wait a few minutes before trying again.';
  if (msg.includes('user already registered') || msg.includes('already exists'))
    return 'An account with this email already exists. Try signing in instead.';
  if (msg.includes('invalid login credentials') || msg.includes('invalid_credentials'))
    return 'Incorrect email or password. Please check and try again.';
  if (msg.includes('email not confirmed'))
    return 'Please verify your email before signing in. Check your inbox for a confirmation link.';
  if (msg.includes('network') || msg.includes('fetch'))
    return 'Network error — please check your connection and try again.';
  if (msg.includes('database') || msg.includes('timeout'))
    return 'Database timeout. Please try again in a moment.';
  if (msg.includes('weak_password') || msg.includes('password'))
    return 'Password must be at least 6 characters long.';
  return err.message || 'Something went wrong. Please try again.';
};

const generateNonce = (): string => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let nonce = '';
  if (typeof window !== 'undefined' && window.crypto) {
    const values = new Uint32Array(16);
    window.crypto.getRandomValues(values);
    for (let i = 0; i < values.length; i++) {
      nonce += chars[values[i] % chars.length];
    }
  } else {
    for (let i = 0; i < 16; i++) {
      nonce += chars.charAt(Math.floor(Math.random() * chars.length));
    }
  }
  return nonce;
};

type GoogleStep = 'idle' | 'connecting' | 'redirecting' | 'returning' | 'finalizing';

const AuthPage = () => {
  const { t } = useTranslation();
  usePageMeta({
    title: t('auth.pageTitle'),
    description: t('auth.pageDescription'),
    canonical: 'https://askmukthiguru.lovable.app/auth',
  });
  const [isSignUp, setIsSignUp] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [googleStep, setGoogleStep] = useState<GoogleStep>(() =>
    typeof window !== 'undefined' && getSessionItemSync(GOOGLE_STEP_KEY) === '1'
      ? 'returning'
      : 'idle',
  );
  const [showLanguageStep, setShowLanguageStep] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();
  const redirectingRef = useRef(false);
  const oauthInFlightRef = useRef(false);
  const processingAuthRef = useRef(false);
  const sessionHandleTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const googleButtonRef = useRef<HTMLDivElement>(null);
  const googleInitializedRef = useRef(false);
  const nonceRef = useRef<string | null>(null);
  const handleCallbackRef = useRef<any>(null);

  useEffect(() => {
    if (!isNativePlatform) return;
    let listenerHandle: PluginListenerHandle | null = null;
    let disposed = false;
    CapacitorApp.addListener('appUrlOpen', ({ url }) => {
      if (!url || !url.startsWith(NATIVE_REDIRECT)) return;
      try {
        const parsed = new URL(url);
        // Complete the OAuth flow explicitly. Supabase v2 uses PKCE by default
        // (code + state in query); legacy implicit flow puts tokens in the hash.
        const code = parsed.searchParams.get('code');
        const hashParams = new URLSearchParams(parsed.hash.replace(/^#/, ''));
        const accessToken = hashParams.get('access_token');
        const refreshToken = hashParams.get('refresh_token');

        if (code) {
          // PKCE flow — exchange the authorization code (not the full URL) for a session.
          supabase.auth
            .exchangeCodeForSession(code)
            .catch((e) => console.warn('[Auth] deep-link code exchange failed:', e));
        } else if (accessToken && refreshToken) {
          // Implicit flow — install the session from the tokens.
          supabase.auth
            .setSession({ access_token: accessToken, refresh_token: refreshToken })
            .catch((e) => console.warn('[Auth] deep-link setSession failed:', e));
        } else {
          console.warn('[Auth] deep-link URL has no code or tokens — ignoring:', url);
        }
      } catch (e) {
        console.warn('[Auth] deep-link URL parse failed:', e);
      }
    })
      .then((handle) => {
        if (disposed) handle.remove();
        else listenerHandle = handle;
      })
      .catch((e) => console.warn('[Auth] appUrlOpen listener registration failed:', e));
    return () => {
      disposed = true;
      listenerHandle?.remove();
    };
  }, []);


  useEffect(() => {
    const ensureInBackground = async () => {
      try {
        const { data: ensured, error: ensureErr } = await (supabase.rpc as unknown as (
          fn: string,
        ) => Promise<{ data: { ok: boolean; profile_created: boolean; role_created: boolean } | null; error: { message: string; code?: string } | null }>)(
          'ensure_profile_and_role',
        );
        if (ensureErr) {
          const msg = (ensureErr.message ?? '').toLowerCase();
          const isSchemaGap = msg.includes('404') || msg.includes('does not exist') || msg.includes('could not find') || msg.includes('function');
          if (!isSchemaGap) {
            console.error('[Auth] ensure_profile_and_role failed', ensureErr);
            toast({
              title: t('auth.profileSetupIncomplete'),
              description: t('auth.profileSetupIncompleteDesc'),
              variant: 'destructive',
              duration: 6000,
            });
          }
        } else {
          console.info('[Auth] ensure_profile_and_role', ensured);
        }
      } catch (rpcErr) {
        console.error('[Auth] ensure_profile_and_role threw', rpcErr);
        toast({
          title: t('auth.profileSetupIncomplete'),
          description: t('auth.profileSetupServerError'),
          variant: 'destructive',
          duration: 6000,
        });
      }
    };

    const handleSession = async (session: import('@supabase/supabase-js').Session, intendedPathParam?: string | null) => {
      if (redirectingRef.current) {
        console.log('[Auth] handleSession blocked - already redirecting');
        return;
      }
      redirectingRef.current = true;
      console.log('[Auth] handleSession starting', { userId: session.user.id });
      
      if (sessionHandleTimeoutRef.current) {
        clearTimeout(sessionHandleTimeoutRef.current);
      }
      sessionHandleTimeoutRef.current = setTimeout(() => {
        console.error('[Auth] Session handling timed out after 15s');
        redirectingRef.current = false;
        setGoogleStep('idle');
        setFacebookStep('idle');
        setLoading(false);
        setError(t('auth.authTimeout'));
        toast({
          title: t('auth.connectionTimeout'),
          description: t('auth.tryAgain'),
          variant: 'destructive'
        });
      }, 15000);
      
      try {
        if (!isEmailAllowed(session.user.email)) {
          console.warn('[Auth] Non-allowed email domain blocked:', session.user.email);
          if (sessionHandleTimeoutRef.current) {
            clearTimeout(sessionHandleTimeoutRef.current);
            sessionHandleTimeoutRef.current = null;
          }
          await supabase.auth.signOut();
          toast({
            title: "Access Denied",
            description: "Registration/Login is restricted to verified @gmail.com or @hotmail.com/@outlook.com accounts.",
            variant: "destructive"
          });
          setError("Access restricted to verified @gmail.com or @hotmail.com/@outlook.com accounts.");
          redirectingRef.current = false;
          setGoogleStep('idle');
          setFacebookStep('idle');
          setLoading(false);
          return;
        }

        // Enforce MFA: if user has a verified TOTP factor and current AAL is
        // aal1, require step-up to aal2 before granting access to the app.
        try {
          const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
          if (aal && aal.nextLevel === 'aal2' && aal.currentLevel !== 'aal2') {
            console.info('[Auth] MFA step-up required for user', session.user.id);
            if (sessionHandleTimeoutRef.current) {
              clearTimeout(sessionHandleTimeoutRef.current);
              sessionHandleTimeoutRef.current = null;
            }
            redirectingRef.current = false;
            setGoogleStep('idle');
            setFacebookStep('idle');
            setLoading(false);
            navigate('/auth/mfa', { replace: true });
            return;
          }
        } catch (mfaErr) {
          console.warn('[Auth] MFA assurance level check failed', mfaErr);
        }


        const [googleKey, fbKey] = await Promise.all([
          getSessionItem(GOOGLE_STEP_KEY),
          getSessionItem('askmukthiguru_facebook_step'),
        ]);
        const isGoogleReturn = googleKey === '1' || getActiveRun()?.provider === 'google';
      const isFacebookReturn = fbKey === '1' || getActiveRun()?.provider === 'facebook';

      if (isGoogleReturn) {
        console.log('[Auth] Detected Google OAuth return');
        setGoogleStep('finalizing');
      }
      if (isFacebookReturn) {
        console.log('[Auth] Detected Facebook OAuth return');
        setFacebookStep('finalizing');
      }

      await Promise.all([
        removeSessionItem(GOOGLE_STEP_KEY),
        removeSessionItem('askmukthiguru_facebook_step'),
      ]);

      const active = getActiveRun();
      if (active && !active.steps.some((s) => s.name === 'provider_return')) {
        recordStep('provider_return', 'ok', Date.now() - active.startedAt, {
          meta: { user_id: session.user.id },
        });
      }
      const hydrateT0 = performance.now();

      const meta = session.user.user_metadata ?? {};
      const metaName: string = meta.full_name || meta.name || '';
      const metaAvatar: string = meta.avatar_url || meta.picture || '';
      try {
        const { loadProfile, updateProfile } = await import('@/lib/profileStorage');
        const local = loadProfile();
        const patch: Record<string, string> = {};
        if (metaName && (local.displayName === 'Seeker' || local.displayName === '')) {
          patch.displayName = metaName.trim().slice(0, 40);
        }
        if (metaAvatar && !local.avatarDataUrl) {
          patch.avatarUrl = metaAvatar;
        }
        if (Object.keys(patch).length > 0) {
          updateProfile(patch as Parameters<typeof updateProfile>[0]);
        }
      } catch { /* non-fatal */ }
      recordStep('session_hydrate', 'ok', Math.round(performance.now() - hydrateT0));

      const redirectPath = intendedPathParam || sessionStorage.getItem('auth_redirect_path');
      if (redirectPath) {
        sessionStorage.removeItem('auth_redirect_path');
        recordStep('navigate', 'ok', 0, { meta: { to: redirectPath } });
        navigate(redirectPath, { replace: true });
        endAuthRun('ok');
        ensureInBackground();
        return;
      }

      const onboardedCached = localStorage.getItem(ONBOARDED_FLAG_KEY) === '1';
      if (onboardedCached) {
        recordStep('navigate', 'ok', 0, { meta: { to: '/chat', cached: true } });
        navigate('/chat', { replace: true });
        endAuthRun('ok');
        ensureInBackground();
        import('@/lib/profileStorage').then(({ fetchProfileFromServer }) => {
          fetchProfileFromServer().catch(() => {});
        });
        return;
      }

      const [, serverProfile] = await Promise.all([
        timeStep('profile_ensure', ensureInBackground),
        timeStep('profile_fetch', async () => {
          try {
            const { fetchProfileFromServer } = await import('@/lib/profileStorage');
            return await fetchProfileFromServer();
          } catch {
            return null;
          }
        }),
      ]);

      const { loadProfile } = await import('@/lib/profileStorage');
      const profile = serverProfile || loadProfile();

      if (profile.displayName === 'Seeker' || !profile.bio) {
        recordStep('navigate', 'ok', 0, { meta: { to: '/profile?onboarding=true' } });
        navigate('/profile?onboarding=true', { replace: true });
      } else {
        recordStep('navigate', 'ok', 0, { meta: { to: '/chat' } });
        setShowLanguageStep(true);
      }
      endAuthRun('ok');
      
      if (sessionHandleTimeoutRef.current) {
        clearTimeout(sessionHandleTimeoutRef.current);
        sessionHandleTimeoutRef.current = null;
      }
      } catch (err) {
        console.error('[Auth] handleSession failed', err);
        
        if (sessionHandleTimeoutRef.current) {
          clearTimeout(sessionHandleTimeoutRef.current);
          sessionHandleTimeoutRef.current = null;
        }
        
        setGoogleStep('idle');
        setFacebookStep('idle');
        setLoading(false);
        setError(t('auth.authFailed'));
        redirectingRef.current = false;
        endAuthRun('error', err instanceof Error ? err.message : String(err));
        
        toast({
          title: t('auth.signInFailed'),
          description: err instanceof Error ? err.message : t('auth.tryAgain'),
          variant: 'destructive'
        });
      }
    };

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (processingAuthRef.current) return;
      processingAuthRef.current = true;
      try {
        if (session?.user && (event === 'SIGNED_IN' || event === 'INITIAL_SESSION' || event === 'TOKEN_REFRESHED')) {
          const intended = await getSessionItem('intendedPath');
          if (intended && intended !== '/auth') {
            await removeSessionItem('intendedPath');
          }
          handleSession(session, intended && intended !== '/auth' ? intended : null);
        }
      } finally {
        processingAuthRef.current = false;
      }
    });

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) handleSession(session, null);
    });

    return () => {
      subscription.unsubscribe();
      if (sessionHandleTimeoutRef.current) {
        clearTimeout(sessionHandleTimeoutRef.current);
      }
    };
  }, [navigate, toast, t]);


  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    startAuthRun('email');
    try {
      if (isSignUp) {
        const trimmedName = fullName.trim();
        if (!trimmedName) {
          setError(t('auth.enterName'));
          setLoading(false);
          return;
        }
        if (!isEmailAllowed(email)) {
          setError("Registration is only allowed for verified @gmail.com or @hotmail.com/@outlook.com emails.");
          setLoading(false);
          return;
        }
        console.info('[Auth] signUp start', { email, hasName: true });
        const signUpT0 = performance.now();
        const { data: signUpData, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: window.location.origin,
            data: { full_name: trimmedName },
          },
        });
        recordStep('email_signup', signUpError ? 'error' : 'ok', Math.round(performance.now() - signUpT0), {
          error: signUpError?.message,
        });
        if (signUpError) {
          console.error('[Auth] signUp failed', { code: (signUpError as { code?: string }).code, status: (signUpError as { status?: number }).status, message: signUpError.message });
          throw signUpError;
        }
        console.info('[Auth] signUp success', {
          user_id: signUpData.user?.id,
          identities: signUpData.user?.identities?.length ?? 0,
          needs_confirmation: !signUpData.session,
        });
        try {
          const { updateProfile } = await import('@/lib/profileStorage');
          updateProfile({ displayName: trimmedName });
        } catch { /* non-fatal */ }
        toast({
          title: t('auth.checkEmail'),
          description: t('auth.verificationSent'),
        });
        endAuthRun('ok');
      } else {
        console.info('[Auth] signIn start', { email });
        const signInT0 = performance.now();
        sessionStorage.setItem('auth_explicit_login', 'true');
        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
        recordStep('email_signin', signInError ? 'error' : 'ok', Math.round(performance.now() - signInT0), {
          error: signInError?.message,
        });
        if (signInError) {
          console.error('[Auth] signIn failed', { code: (signInError as { code?: string }).code, status: (signInError as { status?: number }).status, message: signInError.message });
          throw signInError;
        }
        console.info('[Auth] signIn success');
      }
    } catch (err: unknown) {
      const message = friendlyError(err as Error);
      setError(message);
      console.error('[Auth Error]', err);
      endAuthRun('error', message);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    if (oauthInFlightRef.current) {
      console.warn('[Auth] OAuth already in flight — suppressed');
      return;
    }
    oauthInFlightRef.current = true;
    const lastRedirect = await getSessionItem('lastOAuthRedirect').finally(() => {});
    if (lastRedirect && Date.now() - Number(lastRedirect) < 5000) {
      console.warn('[Auth] Duplicate OAuth redirect suppressed');
      setError(t('auth.authTimeout'));
      oauthInFlightRef.current = false;
      return;
    }
    await setSessionItem('lastOAuthRedirect', String(Date.now()));
    setLoading(true);
    setError(null);
    setGoogleStep('connecting');
    startAuthRun('google');
    const clickT0 = performance.now();
    recordStep('click_google', 'ok', 0);
    const redirectTimer = window.setTimeout(() => {
      setGoogleStep((s) => (s === 'connecting' ? 'redirecting' : s));
    }, 400);
    try {
      await setSessionItem(GOOGLE_STEP_KEY, '1');
      const existingPath = await getSessionItem('intendedPath');
      if (!existingPath || existingPath === '/auth') {
        await setSessionItem('intendedPath', window.location.pathname);
      }

      const initT0 = performance.now();
      const { error: supabaseError } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: isNativePlatform ? NATIVE_REDIRECT : window.location.origin + '/auth',
        },
      });
      recordStep('oauth_init', supabaseError ? 'error' : 'ok', Math.round(performance.now() - initT0), {
        error: supabaseError?.message,
        meta: { mode: 'native', provider: 'google' },
      });
      if (supabaseError) throw supabaseError;
      recordStep('provider_redirect', 'pending', Math.round(performance.now() - clickT0));
      return;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('auth.couldNotConnectGoogle');
      console.error('[Google Auth Error]', err);
      setError(t('auth.couldNotConnectGoogleRetry'));
      await removeSessionItems(['lastOAuthRedirect', GOOGLE_STEP_KEY]);
      setGoogleStep('idle');
      endAuthRun('error', message);
    } finally {
      window.clearTimeout(redirectTimer);
      setLoading(false);
      oauthInFlightRef.current = false;
    }
  };

  const [facebookStep, setFacebookStep] = useState<'idle' | 'connecting' | 'redirecting' | 'finalizing'>('idle');
  
  const handleFacebookSignIn = async () => {
    setLoading(true);
    setError(null);
    setFacebookStep('connecting');
    startAuthRun('facebook');
    const clickT0 = performance.now();
    recordStep('click_facebook', 'ok', 0);
    
    const redirectTimer = window.setTimeout(() => {
      setFacebookStep((s) => (s === 'connecting' ? 'redirecting' : s));
    }, 400);
    
    try {
      await setSessionItem('askmukthiguru_facebook_step', '1');

      const initT0 = performance.now();
      const { error: supabaseError } = await supabase.auth.signInWithOAuth({
        provider: 'facebook',
        options: {
          redirectTo: isNativePlatform ? NATIVE_REDIRECT : window.location.origin,
        },
      });
      recordStep('oauth_init', supabaseError ? 'error' : 'ok', Math.round(performance.now() - initT0), {
        error: supabaseError?.message,
        meta: { provider: 'facebook' },
      });
      if (supabaseError) throw supabaseError;
      recordStep('provider_redirect', 'pending', Math.round(performance.now() - clickT0));
      return;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('auth.couldNotConnectFacebook');
      console.error('[Facebook Auth Error]', err);
      setError(t('auth.couldNotConnectFacebookRetry'));
      await removeSessionItems(['askmukthiguru_facebook_step']);
      setFacebookStep('idle');
      endAuthRun('error', message);
    } finally {
      window.clearTimeout(redirectTimer);
      setLoading(false);
    }
  };

  const [appleStep, setAppleStep] = useState<'idle' | 'connecting' | 'redirecting' | 'finalizing'>('idle');
  const handleAppleSignIn = async () => {
    setLoading(true);
    setError(null);
    setAppleStep('connecting');
    startAuthRun('apple');
    const clickT0 = performance.now();
    recordStep('click_apple', 'ok', 0);
    const redirectTimer = window.setTimeout(() => {
      setAppleStep((s) => (s === 'connecting' ? 'redirecting' : s));
    }, 400);
    try {
      await setSessionItem('askmukthiguru_apple_step', '1');
      const initT0 = performance.now();
      const { error: supabaseError } = await supabase.auth.signInWithOAuth({
        provider: 'apple',
        options: {
          redirectTo: isNativePlatform ? NATIVE_REDIRECT : window.location.origin,
        },
      });
      recordStep('oauth_init', supabaseError ? 'error' : 'ok', Math.round(performance.now() - initT0), {
        error: supabaseError?.message,
        meta: { provider: 'apple' },
      });
      if (supabaseError) throw supabaseError;
      recordStep('provider_redirect', 'pending', Math.round(performance.now() - clickT0));
      return;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not connect to Apple. Please try again.';
      console.error('[Apple Auth Error]', err);
      setError('Could not connect to Apple. Please try again.');
      await removeSessionItems(['askmukthiguru_apple_step']);
      setAppleStep('idle');
      endAuthRun('error', message);
    } finally {
      window.clearTimeout(redirectTimer);
      setLoading(false);
    }
  };

  const googleBusy = googleStep !== 'idle';
  const facebookBusy = facebookStep !== 'idle';
  const appleBusy = appleStep !== 'idle';
  const [showResetButton, setShowResetButton] = useState(false);
  
  useEffect(() => {
    if (googleBusy || facebookBusy || appleBusy) {
      const timer = setTimeout(() => {
        setShowResetButton(true);
      }, 5000);
      return () => clearTimeout(timer);
    } else {
      setShowResetButton(false);
    }
  }, [googleBusy, facebookBusy, appleBusy]);
  
  const handleResetAuth = useCallback(async () => {
    console.log('[Auth] Manual reset triggered');
    redirectingRef.current = false;
    setGoogleStep('idle');
    setFacebookStep('idle');
    setAppleStep('idle');
    setLoading(false);
    setError(null);
    await removeSessionItems([
      GOOGLE_STEP_KEY,
      'askmukthiguru_facebook_step',
      'askmukthiguru_apple_step',
    ]);
    if (sessionHandleTimeoutRef.current) {
      clearTimeout(sessionHandleTimeoutRef.current);
      sessionHandleTimeoutRef.current = null;
    }
    toast({
      title: t('auth.resetComplete'),
      description: t('auth.tryAgain'),
      variant: 'success',
    });
  }, [toast, t]);
  
  const handleGoogleOneTapResponse = useCallback(async (response: { credential: string }) => {
    try {
      setLoading(true);
      startAuthRun('google_one_tap');

      const { data, error } = await supabase.auth.signInWithIdToken({
        provider: 'google',
        token: response.credential,
        nonce: nonceRef.current || undefined,
      });

      if (error) throw error;

      recordStep('google_one_tap', 'ok', 0);
      endAuthRun('ok');

      toast({
        title: t('auth.welcomeBack'),
        description: t('auth.signedInOneTap'),
      });
    } catch (err) {
      console.error('[Google One Tap Error]', err);
      const msg = err instanceof Error ? err.message : 'Unknown error';
      if (msg.includes('Nonces mismatch') || msg.includes('nonce')) {
        const { error: oauthError } = await supabase.auth.signInWithOAuth({
          provider: 'google',
          options: { redirectTo: window.location.origin },
        });
        if (!oauthError) return;
      }
      setError(t('auth.oneTapFailed'));
      endAuthRun('error', msg);
    } finally {
      setLoading(false);
    }
  }, [toast, t]);

  // Keep stable callback ref to avoid re-initializing GSI SDK on tab changes
  useEffect(() => {
    handleCallbackRef.current = handleGoogleOneTapResponse;
  }, [handleGoogleOneTapResponse]);

  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId || isNativePlatform || !isTopLevelFrame) return;

    // Load GIS script if not already present
    let script = document.querySelector(`script[src="${GOOGLE_GSI_SDK_URL}"]`) as HTMLScriptElement;
    if (!script) {
      script = document.createElement('script');
      script.src = GOOGLE_GSI_SDK_URL;
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
    }

    const initGoogleSDK = () => {
      if (typeof window.google !== 'undefined') {
        if (!googleInitializedRef.current) {
          nonceRef.current = generateNonce();

          const allowedOrigins = [
            window.location.origin,
            'https://askmukthiguru.lovable.app',
          ].filter(Boolean);

          window.google.accounts.id.initialize({
            client_id: clientId,
            callback: (res) => handleCallbackRef.current?.(res),
            auto_select: false,
            cancel_on_tap_outside: true,
            nonce: nonceRef.current,
            data_fedcm: true,
            allowed_parent_origin: allowedOrigins,
          });
          googleInitializedRef.current = true;
        }

        // Prompt One Tap only on the Sign In tab
        if (!isSignUp && !loading) {
          window.google.accounts.id.prompt((notification: { isNotDisplayed: () => boolean; isSkippedMoment: () => boolean; getNotDisplayedReason: () => string; getSkippedReason: () => string }) => {
            if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
              console.log('[Google One Tap]', notification.getNotDisplayedReason() || notification.getSkippedReason());
            }
          });
        }

        // Render the Google Sign In button if the ref container is present
        if (googleButtonRef.current) {
          window.google.accounts.id.renderButton(googleButtonRef.current, {
            type: 'standard',
            theme: 'outline',
            size: 'large',
            text: 'continue_with',
            shape: 'rectangular',
            width: googleButtonRef.current.clientWidth || 340,
          });
        }
      }
    };

    if (typeof window.google !== 'undefined') {
      const timer = setTimeout(initGoogleSDK, 100);
      return () => clearTimeout(timer);
    } else {
      script.addEventListener('load', initGoogleSDK);
      return () => {
        script.removeEventListener('load', initGoogleSDK);
      };
    }
  }, [isSignUp, loading]);

  const googleStepLabel: Record<GoogleStep, string> = {
    idle: t('auth.continueWithGoogle'),
    connecting: t('auth.connectingToGoogle'),
    redirecting: t('auth.redirectingToGoogle'),
    returning: t('auth.returningFromGoogle'),
    finalizing: t('auth.signingYouIn'),
  };
  const googleProgressSteps: Array<{ key: GoogleStep; label: string }> = [
    { key: 'connecting', label: t('auth.stepConnect') },
    { key: 'redirecting', label: t('auth.stepAuthorize') },
    { key: 'finalizing', label: t('auth.stepSignIn') },
  ];
  const stepOrder: GoogleStep[] = ['idle', 'connecting', 'redirecting', 'returning', 'finalizing'];
  const currentStepIdx = stepOrder.indexOf(googleStep);

  const facebookStepLabel = facebookBusy ? t('auth.connectingToFacebook') : t('auth.continueWithFacebook');

  const handleLanguageComplete = (code: string) => {
    setLanguage(code);
    localStorage.setItem(ONBOARDED_FLAG_KEY, '1');
    endAuthRun('ok');
    if (sessionHandleTimeoutRef.current) {
      clearTimeout(sessionHandleTimeoutRef.current);
      sessionHandleTimeoutRef.current = null;
    }
    navigate('/chat', { replace: true });
  };

  if (showLanguageStep) {
    return <LanguageOnboardingStep onComplete={handleLanguageComplete} />;
  }

  return (
    <div className="min-h-dvh flex items-center justify-center bg-gradient-to-br from-background via-ojas/5 to-background px-4">
      <div className="w-full max-w-[400px] mx-4 sm:mx-auto space-y-6 shadow-xl shadow-foreground/5 border border-border/40 p-6 sm:p-8">
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center mx-auto">
            <Sparkles className="w-6 h-6 text-ojas" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">{t('auth.signInTitle')}</h1>
          <p className="text-sm text-muted-foreground">
            {isSignUp ? t('auth.createAccount') : t('auth.welcomeBack')}
          </p>
        </div>

        {error && (
          <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-sm">{error}</AlertDescription>
          </Alert>
        )}

        <div className="space-y-3">
          <p className="text-xs text-muted-foreground text-center">{t('auth.continueWith', { defaultValue: 'Continue with' })}</p>

          {isNativePlatform && (
            <Button
              variant="outline"
              className="w-full h-11 sm:h-12 gap-2.5 rounded-xl relative overflow-hidden bg-black text-white hover:bg-black/90 border-black"
              onClick={handleAppleSignIn}
              disabled={loading || appleBusy}
              aria-live="polite"
            >
              {appleBusy ? (
                <Loader2 className="w-4 h-4 animate-spin shrink-0" />
              ) : (
                <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09l.01-.01zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
                </svg>
              )}
              <span className="text-sm">
                {appleStep === 'idle' && t('auth.continueWithApple')}
                {appleStep === 'connecting' && t('auth.appleConnecting')}
                {appleStep === 'redirecting' && t('auth.appleRedirecting')}
                {appleStep === 'finalizing' && t('auth.appleFinalizing')}
              </span>
            </Button>
          )}

          {!isNativePlatform && import.meta.env.VITE_GOOGLE_CLIENT_ID && isTopLevelFrame ? (
            <div
              ref={googleButtonRef}
              className="w-full flex justify-center min-h-[44px]"
              data-testid="google-gsi-container"
            />
          ) : !isNativePlatform && (
            <Button
              variant="outline"
              className="w-full h-11 sm:h-12 gap-2.5 rounded-xl relative overflow-hidden"
              onClick={handleGoogleSignIn}
              disabled={loading || googleBusy}
              aria-live="polite"
            >
              {googleBusy && <Loader2 className="w-4 h-4 animate-spin shrink-0" />}
              <svg className="w-4 h-4 shrink-0" viewBox="0 0 48 48" aria-hidden="true">
                <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.7-6.1 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>
                <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
                <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.3l-6.2-5.2c-2 1.4-4.5 2.3-7.2 2.3-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
                <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.3-4.1 5.6l6.2 5.2C40.8 35.4 44 30.1 44 24c0-1.3-.1-2.4-.4-3.5z"/>
              </svg>
              <span className="text-sm">{googleStepLabel[googleStep]}</span>
              {googleBusy && (
                <span
                  aria-hidden="true"
                  className="absolute bottom-0 left-0 h-0.5 bg-ojas/70 transition-all duration-500 ease-out"
                  style={{ width: `${Math.max(15, currentStepIdx * 25)}%` }}
                />
              )}
            </Button>
          )}

          {googleBusy && (
            <ol
              className="flex items-center justify-between text-[11px] text-muted-foreground px-1"
              aria-label={t('auth.signInProgress')}
            >
              {googleProgressSteps.map((step) => {
                const stepIdx = stepOrder.indexOf(step.key);
                const effectiveIdx =
                  googleStep === 'returning' ? stepOrder.indexOf('finalizing') : currentStepIdx;
                const done = effectiveIdx > stepIdx;
                const active = effectiveIdx === stepIdx;
                return (
                  <li key={step.key} className="flex items-center gap-1.5">
                    <span
                      className={`flex items-center justify-center w-4 h-4 rounded-full border transition-colors ${
                        done
                          ? 'bg-ojas border-ojas text-primary-foreground'
                          : active
                          ? 'border-ojas text-ojas'
                          : 'border-border/60'
                      }`}
                    >
                      {done ? (
                        <Check className="w-2.5 h-2.5" />
                      ) : active ? (
                        <Loader2 className="w-2.5 h-2.5 animate-spin" />
                      ) : null}
                    </span>
                    <span className={active || done ? 'text-foreground' : ''}>{step.label}</span>
                  </li>
                );
              })}
            </ol>
          )}

          {showResetButton && (googleBusy || facebookBusy || appleBusy) && (
            <div className="text-center pt-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleResetAuth}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                {t('auth.takingTooLong')}
              </Button>
            </div>
          )}
        </div>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border/50" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-background px-2 text-muted-foreground">{t('auth.or')}</span>
          </div>
        </div>

        <form onSubmit={handleEmailAuth} className="space-y-4">
          {isSignUp && (
            <div className="space-y-2">
              <Label htmlFor="fullName" className="text-xs text-muted-foreground">{t('auth.fullName')}</Label>
              <div className="relative">
                <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="fullName"
                  type="text"
                  value={fullName}
                  onChange={(e) => { setFullName(e.target.value); setError(null); }}
                  placeholder={t('auth.yourName')}
                  className="pl-9 h-10"
                  autoComplete="name"
                  required
                />
              </div>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="email" className="text-xs text-muted-foreground">{t('auth.email')}</Label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setError(null); }}
                placeholder={t('auth.emailPlaceholder')}
                className="pl-9 h-10"
                required
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="password" className="text-xs text-muted-foreground">{t('auth.password')}</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(null); }}
                placeholder={t('auth.passwordPlaceholder')}
                className="pl-9 pr-9 h-10"
                required
                minLength={6}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
                aria-pressed={showPassword}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <Button type="submit" className="w-full h-10 bg-ojas hover:bg-ojas-light text-primary-foreground" disabled={loading || googleBusy}>
            {loading ? t('auth.pleaseWait') : isSignUp ? t('auth.createAccountBtn') : t('auth.signInBtn')}
          </Button>
        </form>

        {!isSignUp && (
          <div className="text-center">
            <button
              type="button"
              onClick={async () => {
                if (!email) return setError(t('auth.enterEmailFirst'));
                setLoading(true);
                setError(null);
                const { error: resetErr } = await supabase.auth.resetPasswordForEmail(email, {
                  redirectTo: `${window.location.origin}/reset-password`,
                });
                setLoading(false);
                if (resetErr) setError(friendlyError(resetErr));
                else toast({ title: t('auth.checkEmail'), description: t('auth.passwordResetSent') });
              }}
              className="text-xs text-muted-foreground hover:text-ojas hover:underline"
            >
              {t('auth.forgotPassword')}
            </button>
          </div>
        )}

        <div className="text-center space-y-1 pt-2 border-t border-border/30">
          <p className="text-xs text-muted-foreground">
            {isSignUp ? t('auth.alreadyAccount') : t('auth.noAccount')}{' '}
            <button
              onClick={() => { setIsSignUp(!isSignUp); setError(null); }}
              className="text-ojas hover:underline font-medium"
            >
              {isSignUp ? t('auth.signInBtn') : t('auth.signUpBtn')}
            </button>
          </p>
          <p className="text-[11px] text-muted-foreground/60">
            {t('auth.troubleSigningIn')}{' '}
            <a href="/auth/diagnostics" className="text-ojas hover:underline">
              {t('auth.runDiagnostics')}
            </a>
          </p>
          <p className="text-[11px] text-muted-foreground/50">
            {t('auth.byContinuing')}{' '}
            <a href="/terms" className="hover:text-ojas hover:underline">{t('auth.terms')}</a>{t('auth.and')}{' '}
            <a href="/privacy" className="hover:text-ojas hover:underline">{t('auth.privacyPolicy')}</a>.
          </p>
        </div>
      </div>
    </div>
  );
};

export default AuthPage;
