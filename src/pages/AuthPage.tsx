import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { lovable } from '@/integrations/lovable/index';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { Sparkles, Mail, Lock, Eye, EyeOff, AlertCircle, User as UserIcon, Loader2, Check } from 'lucide-react';
import {
  startAuthRun,
  recordStep,
  timeStep,
  endAuthRun,
  getActiveRun,
} from '@/lib/authTelemetry';

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

const ONBOARDED_FLAG_KEY = 'askmukthiguru_onboarded';
const GOOGLE_STEP_KEY = 'askmukthiguru_google_step'; // survives redirect roundtrip

type GoogleStep = 'idle' | 'connecting' | 'redirecting' | 'returning' | 'finalizing';

const AuthPage = () => {
  const [isSignUp, setIsSignUp] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // If we're coming back from a Google OAuth redirect, jump straight to "returning"
  // so the user sees an immediate spinner instead of the bare auth form.
  const [googleStep, setGoogleStep] = useState<GoogleStep>(() =>
    typeof window !== 'undefined' && sessionStorage.getItem(GOOGLE_STEP_KEY) === '1'
      ? 'returning'
      : 'idle',
  );
  const navigate = useNavigate();
  const { toast } = useToast();
  const redirectingRef = useRef(false);
  const sessionHandleTimeoutRef = useRef<NodeJS.Timeout | null>(null);


  useEffect(() => {
    // Background profile + role provisioning. Runs after navigation so it never
    // blocks the post-OAuth render. Safe to call multiple times.
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
          }
        } else {
          console.info('[Auth] ensure_profile_and_role', ensured);
        }
      } catch (rpcErr) {
        console.error('[Auth] ensure_profile_and_role threw', rpcErr);
      }
    };

    const handleSession = async (session: import('@supabase/supabase-js').Session) => {
      if (redirectingRef.current) {
        console.log('[Auth] handleSession blocked - already redirecting');
        return;
      }
      redirectingRef.current = true;
      console.log('[Auth] handleSession starting', { userId: session.user.id });
      
      // Set a timeout to recover from stuck states
      if (sessionHandleTimeoutRef.current) {
        clearTimeout(sessionHandleTimeoutRef.current);
      }
      sessionHandleTimeoutRef.current = setTimeout(() => {
        console.error('[Auth] Session handling timed out after 15s');
        redirectingRef.current = false;
        setGoogleStep('idle');
        setFacebookStep('idle');
        setLoading(false);
        setError('Authentication timeout. Please try again.');
        toast({
          title: 'Connection Timeout',
          description: 'Please try signing in again.',
          variant: 'destructive'
        });
      }, 15000); // 15 second timeout
      
      try {
      // Only show the Google "finalizing" step if a Google attempt is actually
      // in progress. Avoids a misleading "Signing you in…" flash for users who
      // land on /auth with an already-valid session.
      const isGoogleReturn =
        sessionStorage.getItem(GOOGLE_STEP_KEY) === '1' ||
        getActiveRun()?.provider === 'google';
      const isFacebookReturn = 
        sessionStorage.getItem('askmukthiguru_facebook_step') === '1' ||
        getActiveRun()?.provider === 'facebook';
        
      if (isGoogleReturn) {
        console.log('[Auth] Detected Google OAuth return');
        setGoogleStep('finalizing');
      }
      if (isFacebookReturn) {
        console.log('[Auth] Detected Facebook OAuth return');
        setFacebookStep('finalizing');
      }
      
      sessionStorage.removeItem(GOOGLE_STEP_KEY);
      sessionStorage.removeItem('askmukthiguru_facebook_step');


      // If this session is the tail end of a Google round-trip, record it.
      const active = getActiveRun();
      if (active && !active.steps.some((s) => s.name === 'provider_return')) {
        recordStep('provider_return', 'ok', Date.now() - active.startedAt, {
          meta: { user_id: session.user.id },
        });
      }
      const hydrateT0 = performance.now();

      // ── Seed local profile from OAuth metadata synchronously (localStorage only) ──
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

      const redirectPath = sessionStorage.getItem('auth_redirect_path');
      if (redirectPath) {
        sessionStorage.removeItem('auth_redirect_path');
        recordStep('navigate', 'ok', 0, { meta: { to: redirectPath } });
        navigate(redirectPath, { replace: true });
        endAuthRun('ok');
        ensureInBackground();
        return;
      }

      // Fast path: if this user has previously completed onboarding, navigate
      // immediately to /chat without waiting on a server profile fetch. The
      // server-side ensure + profile fetch run in the background.
      const onboardedCached = localStorage.getItem(ONBOARDED_FLAG_KEY) === '1';
      if (onboardedCached) {
        recordStep('navigate', 'ok', 0, { meta: { to: '/chat', cached: true } });
        navigate('/chat', { replace: true });
        endAuthRun('ok');
        ensureInBackground();
        // Refresh server profile lazily in the background.
        import('@/lib/profileStorage').then(({ fetchProfileFromServer }) => {
          fetchProfileFromServer().catch(() => {});
        });
        return;
      }

      // Slow path: run ensure + profile fetch in parallel, then decide.
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
        localStorage.setItem(ONBOARDED_FLAG_KEY, '1');
        recordStep('navigate', 'ok', 0, { meta: { to: '/chat' } });
        navigate('/chat', { replace: true });
      }
      endAuthRun('ok');
      
      // Clear timeout on success
      if (sessionHandleTimeoutRef.current) {
        clearTimeout(sessionHandleTimeoutRef.current);
        sessionHandleTimeoutRef.current = null;
      }
      } catch (err) {
        console.error('[Auth] handleSession failed', err);
        
        // Clear timeout on error
        if (sessionHandleTimeoutRef.current) {
          clearTimeout(sessionHandleTimeoutRef.current);
          sessionHandleTimeoutRef.current = null;
        }
        
        setGoogleStep('idle');
        setFacebookStep('idle');
        setLoading(false);
        setError('Authentication failed. Please try again.');
        redirectingRef.current = false;
        endAuthRun('error', err instanceof Error ? err.message : String(err));
        
        // Show user-friendly error toast
        toast({
          title: 'Sign-in Failed',
          description: err instanceof Error ? err.message : 'Please try signing in again.',
          variant: 'destructive'
        });
      }
    };


    // Set up auth listener FIRST, then check existing session.
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (session?.user && (event === 'SIGNED_IN' || event === 'INITIAL_SESSION' || event === 'TOKEN_REFRESHED')) {
        handleSession(session);
      }
    });

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) handleSession(session);
    });

    return () => {
      subscription.unsubscribe();
      if (sessionHandleTimeoutRef.current) {
        clearTimeout(sessionHandleTimeoutRef.current);
      }
    };
  }, [navigate, toast]);


  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    startAuthRun('email');
    try {
      if (isSignUp) {
        const trimmedName = fullName.trim();
        if (!trimmedName) {
          setError('Please enter your full name.');
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
        // Seed the local profile with the chosen name so the chat header / profile
        // page reflect it immediately, even before the email is confirmed.
        try {
          const { updateProfile } = await import('@/lib/profileStorage');
          updateProfile({ displayName: trimmedName });
        } catch { /* non-fatal */ }
        toast({
          title: 'Check your email',
          description: 'We sent you a verification link to complete sign-up. Tip: visit /auth/diagnostics after signing in to verify role + profile setup.',
        });
        endAuthRun('ok');
      } else {
        console.info('[Auth] signIn start', { email });
        const signInT0 = performance.now();
        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
        recordStep('email_signin', signInError ? 'error' : 'ok', Math.round(performance.now() - signInT0), {
          error: signInError?.message,
        });
        if (signInError) {
          console.error('[Auth] signIn failed', { code: (signInError as { code?: string }).code, status: (signInError as { status?: number }).status, message: signInError.message });
          throw signInError;
        }
        console.info('[Auth] signIn success');
        // Redirect logic is handled by onAuthStateChange effect
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
    setLoading(true);
    setError(null);
    // Optimistic: show "Connecting…" the instant the user clicks.
    setGoogleStep('connecting');
    // Start a fresh telemetry run for this Google attempt.
    startAuthRun('google');
    const clickT0 = performance.now();
    recordStep('click_google', 'ok', 0);
    // Promote to "Redirecting…" shortly after, so even slow networks feel responsive.
    const redirectTimer = window.setTimeout(() => {
      setGoogleStep((s) => (s === 'connecting' ? 'redirecting' : s));
    }, 400);
    try {
      // Always use Lovable Cloud managed Google OAuth. The native path was pointing
      // at a stale external Supabase project (causing "failed to exchange authorization code").
      sessionStorage.setItem(GOOGLE_STEP_KEY, '1');

      const initT0 = performance.now();
      const result = await lovable.auth.signInWithOAuth('google', {
        redirect_uri: window.location.origin,
      });
      recordStep('oauth_init', result.error ? 'error' : 'ok', Math.round(performance.now() - initT0), {
        error: result.error instanceof Error ? result.error.message : undefined,
        meta: { mode: 'lovable', redirected: !!result.redirected },
      });

      if (result.error) {
        const message = result.error instanceof Error ? result.error.message : 'Google sign-in failed. Please try again.';
        setError(message);
        sessionStorage.removeItem(GOOGLE_STEP_KEY);
        setGoogleStep('idle');
        endAuthRun('error', message);
        return;
      }
      if (result.redirected) {
        recordStep('provider_redirect', 'pending', Math.round(performance.now() - clickT0));
        return;
      }

      // No redirect needed (tokens already returned): show finalizing while
      // onAuthStateChange handles navigation.
      setGoogleStep('finalizing');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not connect to Google.';
      console.error('[Google Auth Error]', err);
      setError('Could not connect to Google. Please try again.');
      sessionStorage.removeItem(GOOGLE_STEP_KEY);
      setGoogleStep('idle');
      endAuthRun('error', message);
    } finally {
      window.clearTimeout(redirectTimer);
      setLoading(false);
    }
  };

  // Facebook OAuth handler
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
      const useNativeOAuth = import.meta.env.VITE_USE_NATIVE_OAUTH === 'true';
      sessionStorage.setItem('askmukthiguru_facebook_step', '1');
      
      if (useNativeOAuth) {
        const initT0 = performance.now();
        const { error: supabaseError } = await supabase.auth.signInWithOAuth({
          provider: 'facebook',
          options: {
            redirectTo: window.location.href,
          },
        });
        recordStep('oauth_init', supabaseError ? 'error' : 'ok', Math.round(performance.now() - initT0), {
          error: supabaseError?.message,
          meta: { mode: 'native', provider: 'facebook' },
        });
        if (supabaseError) throw supabaseError;
        recordStep('provider_redirect', 'pending', Math.round(performance.now() - clickT0));
        return;
      }
      
      // Lovable wrapper for Facebook
      const initT0 = performance.now();
      const result = await lovable.auth.signInWithOAuth('facebook' as any, {
        redirect_uri: window.location.origin,
      });
      recordStep('oauth_init', result.error ? 'error' : 'ok', Math.round(performance.now() - initT0), {
        error: result.error instanceof Error ? result.error.message : undefined,
        meta: { mode: 'lovable', provider: 'facebook', redirected: !!result.redirected },
      });
      
      if (result.error) {
        const message = result.error instanceof Error ? result.error.message : 'Facebook sign-in failed. Please try again.';
        setError(message);
        sessionStorage.removeItem('askmukthiguru_facebook_step');
        setFacebookStep('idle');
        endAuthRun('error', message);
        return;
      }
      if (result.redirected) {
        recordStep('provider_redirect', 'pending', Math.round(performance.now() - clickT0));
        return;
      }
      
      setFacebookStep('finalizing');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not connect to Facebook.';
      console.error('[Facebook Auth Error]', err);
      setError('Could not connect to Facebook. Please try again.');
      sessionStorage.removeItem('askmukthiguru_facebook_step');
      setFacebookStep('idle');
      endAuthRun('error', message);
    } finally {
      window.clearTimeout(redirectTimer);
      setLoading(false);
    }
  };

  const googleBusy = googleStep !== 'idle';
  const facebookBusy = facebookStep !== 'idle';
  const [showResetButton, setShowResetButton] = useState(false);
  
  // Show reset button after 5 seconds of being stuck
  useEffect(() => {
    if (googleBusy || facebookBusy) {
      const timer = setTimeout(() => {
        setShowResetButton(true);
      }, 5000);
      return () => clearTimeout(timer);
    } else {
      setShowResetButton(false);
    }
  }, [googleBusy, facebookBusy]);
  
  // Manual reset function for stuck states
  const handleResetAuth = useCallback(() => {
    console.log('[Auth] Manual reset triggered');
    redirectingRef.current = false;
    setGoogleStep('idle');
    setFacebookStep('idle');
    setLoading(false);
    setError(null);
    sessionStorage.removeItem(GOOGLE_STEP_KEY);
    sessionStorage.removeItem('askmukthiguru_facebook_step');
    if (sessionHandleTimeoutRef.current) {
      clearTimeout(sessionHandleTimeoutRef.current);
      sessionHandleTimeoutRef.current = null;
    }
    toast({
      title: 'Reset Complete',
      description: 'You can try signing in again.',
    });
  }, [toast]);
  
  // Google One Tap initialization
  useEffect(() => {
    // Skip if already authenticated or in sign-up mode
    if (loading || isSignUp) return;
    
    const initializeGoogleOneTap = () => {
      const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
      if (!clientId) {
        console.warn('[Google One Tap] VITE_GOOGLE_CLIENT_ID not configured');
        return;
      }
      
      // Load Google Identity Services script
      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      script.onload = () => {
        if (typeof window.google !== 'undefined') {
          window.google.accounts.id.initialize({
            client_id: clientId,
            callback: handleGoogleOneTapResponse,
            auto_select: false,
            cancel_on_tap_outside: true,
          });
          
          // Display the One Tap prompt
          window.google.accounts.id.prompt((notification: any) => {
            if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
              console.log('[Google One Tap]', notification.getNotDisplayedReason() || notification.getSkippedReason());
            }
          });
        }
      };
      document.body.appendChild(script);
      
      return () => {
        document.body.removeChild(script);
      };
    };
    
    const timer = setTimeout(initializeGoogleOneTap, 1000);
    return () => clearTimeout(timer);
  }, [loading, isSignUp]);
  
  const handleGoogleOneTapResponse = useCallback(async (response: any) => {
    try {
      setLoading(true);
      startAuthRun('google_one_tap');
      
      // Exchange the credential with Supabase
      const { data, error } = await supabase.auth.signInWithIdToken({
        provider: 'google',
        token: response.credential,
      });
      
      if (error) throw error;
      
      recordStep('google_one_tap', 'ok', 0);
      endAuthRun('ok');
      
      toast({
        title: 'Welcome back!',
        description: 'Signed in with Google One Tap',
      });
    } catch (err) {
      console.error('[Google One Tap Error]', err);
      setError('Google One Tap sign-in failed. Please try again.');
      endAuthRun('error', err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [toast]);
  const googleStepLabel: Record<GoogleStep, string> = {
    idle: 'Continue with Google',
    connecting: 'Connecting to Google…',
    redirecting: 'Redirecting to Google…',
    returning: 'Returning from Google…',
    finalizing: 'Signing you in…',
  };
  const googleProgressSteps: Array<{ key: GoogleStep; label: string }> = [
    { key: 'connecting', label: 'Connect' },
    { key: 'redirecting', label: 'Authorize' },
    { key: 'finalizing', label: 'Sign in' },
  ];
  const stepOrder: GoogleStep[] = ['idle', 'connecting', 'redirecting', 'returning', 'finalizing'];
  const currentStepIdx = stepOrder.indexOf(googleStep);


  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center mx-auto">
            <Sparkles className="w-6 h-6 text-ojas" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">Sign in to AskMukthiGuru</h1>
          <p className="text-sm text-muted-foreground">
            {isSignUp ? 'Create your account' : 'Welcome back, dear seeker'}
          </p>
        </div>

        {error && (
          <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-sm">{error}</AlertDescription>
          </Alert>
        )}

        <div className="space-y-2">
          <Button
            variant="outline"
            className="w-full h-11 gap-2 relative overflow-hidden"
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


          {googleBusy && (
            <ol
              className="flex items-center justify-between text-[11px] text-muted-foreground px-1"
              aria-label="Sign-in progress"
            >
              {googleProgressSteps.map((step) => {
                const stepIdx = stepOrder.indexOf(step.key);
                const done = currentStepIdx > stepIdx;
                const active = currentStepIdx === stepIdx || (step.key === 'redirecting' && googleStep === 'returning');
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
          
          {/* Reset button for stuck states */}
          {showResetButton && (googleBusy || facebookBusy) && (
            <div className="text-center pt-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleResetAuth}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Taking too long? Click here to reset and try again
              </Button>
            </div>
          )}
          
          {/* Facebook Sign-In Button */}
          <Button
            variant="outline"
            className="w-full h-11 gap-2 relative overflow-hidden"
            onClick={handleFacebookSignIn}
            disabled={loading || facebookBusy}
            aria-live="polite"
          >
            {facebookBusy && <Loader2 className="w-4 h-4 animate-spin shrink-0" />}
            <svg className="w-4 h-4 shrink-0" viewBox="0 0 48 48" aria-hidden="true">
              <path fill="#1877F2" d="M48 24C48 10.745 37.255 0 24 0S0 10.745 0 24c0 11.979 8.776 21.908 20.25 23.708v-16.77h-6.094V24h6.094v-5.288c0-6.014 3.583-9.337 9.065-9.337 2.625 0 5.372.469 5.372.469v5.906h-3.026c-2.981 0-3.911 1.850-3.911 3.75V24h6.656l-1.064 6.938H27.75v16.77C39.224 45.908 48 35.978 48 24z"/>
              <path fill="#fff" d="M33.342 30.938L34.406 24H27.75v-4.5c0-1.9.93-3.75 3.911-3.75h3.026V9.844s-2.747-.469-5.372-.469c-5.482 0-9.065 3.323-9.065 9.337V24h-6.094v6.938h6.094v16.77a24.175 24.175 0 007.5 0v-16.77h5.592z"/>
            </svg>
            <span className="text-sm">
              {facebookBusy ? 'Connecting to Facebook…' : 'Continue with Facebook'}
            </span>
            {facebookBusy && (
              <span
                aria-hidden="true"
                className="absolute bottom-0 left-0 h-0.5 bg-[#1877F2]/70 transition-all duration-500 ease-out"
                style={{ width: '50%' }}
              />
            )}
          </Button>
        </div>


        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border/50" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-background px-2 text-muted-foreground">or</span>
          </div>
        </div>

        <form onSubmit={handleEmailAuth} className="space-y-4">
          {isSignUp && (
            <div className="space-y-2">
              <Label htmlFor="fullName" className="text-xs text-muted-foreground">Full name</Label>
              <div className="relative">
                <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="fullName"
                  type="text"
                  value={fullName}
                  onChange={(e) => { setFullName(e.target.value); setError(null); }}
                  placeholder="Your name"
                  className="pl-9 h-10"
                  autoComplete="name"
                  required
                />
              </div>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="email" className="text-xs text-muted-foreground">Email</Label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setError(null); }}
                placeholder="you@example.com"
                className="pl-9 h-10"
                required
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="password" className="text-xs text-muted-foreground">Password</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(null); }}
                placeholder="••••••••"
                className="pl-9 pr-9 h-10"
                required
                minLength={6}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <Button type="submit" className="w-full h-10 bg-ojas hover:bg-ojas-light text-primary-foreground" disabled={loading || googleBusy}>
            {loading ? 'Please wait…' : isSignUp ? 'Create account' : 'Sign in'}
          </Button>
        </form>

        {!isSignUp && (
          <div className="text-center">
            <button
              type="button"
              onClick={async () => {
                if (!email) return setError('Enter your email above first, then tap Forgot password.');
                setLoading(true);
                setError(null);
                const { error: resetErr } = await supabase.auth.resetPasswordForEmail(email, {
                  redirectTo: `${window.location.origin}/reset-password`,
                });
                setLoading(false);
                if (resetErr) setError(friendlyError(resetErr));
                else toast({ title: 'Check your email', description: 'We sent you a link to reset your password.' });
              }}
              className="text-xs text-muted-foreground hover:text-ojas hover:underline"
            >
              Forgot your password?
            </button>
          </div>
        )}

        <p className="text-center text-xs text-muted-foreground">
          {isSignUp ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button
            onClick={() => { setIsSignUp(!isSignUp); setError(null); }}
            className="text-ojas hover:underline font-medium"
          >
            {isSignUp ? 'Sign in' : 'Sign up'}
          </button>
        </p>

        <p className="text-center text-[11px] text-muted-foreground/70 pt-2">
          By continuing you agree to our{' '}
          <a href="/terms" className="hover:text-ojas hover:underline">Terms</a> and{' '}
          <a href="/privacy" className="hover:text-ojas hover:underline">Privacy Policy</a>.
        </p>

        <p className="text-center text-[11px] text-muted-foreground/60 pt-1">
          Trouble signing in?{' '}
          <a href="/auth/diagnostics" className="text-ojas hover:underline">
            Run diagnostics
          </a>
        </p>
      </div>
    </div>
  );
};

export default AuthPage;
