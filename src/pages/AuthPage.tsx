import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
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
const GOOGLE_STEP_KEY = 'askmukthiguru_google_step';

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
    typeof window !== 'undefined' && sessionStorage.getItem(GOOGLE_STEP_KEY) === '1'
      ? 'returning'
      : 'idle',
  );
  const [showLanguageStep, setShowLanguageStep] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();
  const redirectingRef = useRef(false);
  const sessionHandleTimeoutRef = useRef<NodeJS.Timeout | null>(null);


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

    const handleSession = async (session: import('@supabase/supabase-js').Session) => {
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

      const redirectPath = sessionStorage.getItem('auth_redirect_path');
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
      sessionStorage.setItem(GOOGLE_STEP_KEY, '1');

      const initT0 = performance.now();
      const { error: supabaseError } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.origin,
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
      sessionStorage.removeItem(GOOGLE_STEP_KEY);
      setGoogleStep('idle');
      endAuthRun('error', message);
    } finally {
      window.clearTimeout(redirectTimer);
      setLoading(false);
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
      sessionStorage.setItem('askmukthiguru_facebook_step', '1');

      const initT0 = performance.now();
      const { error: supabaseError } = await supabase.auth.signInWithOAuth({
        provider: 'facebook',
        options: {
          redirectTo: window.location.origin,
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
      title: t('auth.resetComplete'),
      description: t('auth.tryAgain'),
    });
  }, [toast, t]);
  
  useEffect(() => {
    if (loading || isSignUp) return;
    
    const initializeGoogleOneTap = () => {
      const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
      if (!clientId) {
        console.warn('[Google One Tap] VITE_GOOGLE_CLIENT_ID not configured');
        return;
      }
      
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
          
          window.google.accounts.id.prompt((notification: { isNotDisplayed: () => boolean; isSkippedMoment: () => boolean; getNotDisplayedReason: () => string; getSkippedReason: () => string }) => {
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
  
  const handleGoogleOneTapResponse = useCallback(async (response: { credential: string }) => {
    try {
      setLoading(true);
      startAuthRun('google_one_tap');
      
      const { data, error } = await supabase.auth.signInWithIdToken({
        provider: 'google',
        token: response.credential,
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
      setError(t('auth.oneTapFailed'));
      endAuthRun('error', err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [toast, t]);

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
    <div className="min-h-dvh flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
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
          
          {showResetButton && (googleBusy || facebookBusy) && (
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
          
{/*
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
               {facebookStepLabel}
             </span>
             {facebookBusy && (
               <span
                 aria-hidden="true"
                 className="absolute bottom-0 left-0 h-0.5 bg-[#1877F2]/70 transition-all duration-500 ease-out"
                 style={{ width: '50%' }}
               />
             )}
           </Button>
           */}
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

        <p className="text-center text-xs text-muted-foreground">
          {isSignUp ? t('auth.alreadyAccount') : t('auth.noAccount')}{' '}
          <button
            onClick={() => { setIsSignUp(!isSignUp); setError(null); }}
            className="text-ojas hover:underline font-medium"
          >
            {isSignUp ? t('auth.signInBtn') : t('auth.signUpBtn')}
          </button>
        </p>

        <p className="text-center text-[11px] text-muted-foreground/70 pt-2">
          {t('auth.byContinuing')}{' '}
          <a href="/terms" className="hover:text-ojas hover:underline">{t('auth.terms')}</a>{t('auth.and')}{' '}
          <a href="/privacy" className="hover:text-ojas hover:underline">{t('auth.privacyPolicy')}</a>.
        </p>

        <p className="text-center text-[11px] text-muted-foreground/60 pt-1">
          {t('auth.troubleSigningIn')}{' '}
          <a href="/auth/diagnostics" className="text-ojas hover:underline">
            {t('auth.runDiagnostics')}
          </a>
        </p>
      </div>
    </div>
  );
};

export default AuthPage;
