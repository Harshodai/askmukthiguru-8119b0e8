import { useState, useEffect, useRef } from 'react';
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
      if (redirectingRef.current) return;
      redirectingRef.current = true;
      // Visible progress while we hydrate profile + decide destination.
      setGoogleStep('finalizing');
      sessionStorage.removeItem(GOOGLE_STEP_KEY);

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

    return () => subscription.unsubscribe();
  }, [navigate, toast]);


  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (isSignUp) {
        const trimmedName = fullName.trim();
        if (!trimmedName) {
          setError('Please enter your full name.');
          setLoading(false);
          return;
        }
        console.info('[Auth] signUp start', { email, hasName: true });
        const { data: signUpData, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: window.location.origin,
            data: { full_name: trimmedName },
          },
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
      } else {
        console.info('[Auth] signIn start', { email });
        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
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
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setLoading(true);
    setError(null);
    // Optimistic: show "Connecting…" the instant the user clicks.
    setGoogleStep('connecting');
    // Promote to "Redirecting…" shortly after, so even slow networks feel responsive.
    const redirectTimer = window.setTimeout(() => {
      setGoogleStep((s) => (s === 'connecting' ? 'redirecting' : s));
    }, 400);
    try {
      const useNativeOAuth = import.meta.env.VITE_USE_NATIVE_OAUTH === 'true';

      // Mark that we initiated Google OAuth so that after the redirect roundtrip
      // we can show "Returning from Google…" immediately on mount.
      sessionStorage.setItem(GOOGLE_STEP_KEY, '1');

      if (useNativeOAuth) {
        const { error: supabaseError } = await supabase.auth.signInWithOAuth({
          provider: 'google',
          options: {
            redirectTo: window.location.href, // Return here to process saved redirect path
          },
        });
        if (supabaseError) throw supabaseError;
        return;
      }

      const result = await lovable.auth.signInWithOAuth('google', {
        redirect_uri: window.location.origin,
      });

      if (result.error) {
        const message = result.error instanceof Error ? result.error.message : 'Google sign-in failed. Please try again.';
        setError(message);
        sessionStorage.removeItem(GOOGLE_STEP_KEY);
        setGoogleStep('idle');
        return;
      }
      if (result.redirected) return;

      // No redirect needed (tokens already returned): show finalizing while
      // onAuthStateChange handles navigation.
      setGoogleStep('finalizing');
    } catch (err) {
      console.error('[Google Auth Error]', err);
      setError('Could not connect to Google. Please try again.');
      sessionStorage.removeItem(GOOGLE_STEP_KEY);
      setGoogleStep('idle');
    } finally {
      window.clearTimeout(redirectTimer);
      setLoading(false);
    }
  };

  const googleBusy = googleStep !== 'idle';
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
          <h1 className="text-xl font-semibold text-foreground">AskMukthiGuru</h1>
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
            {googleBusy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
            )}
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
