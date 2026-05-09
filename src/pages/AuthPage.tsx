import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { lovable } from '@/integrations/lovable/index';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { Sparkles, Mail, Lock, Eye, EyeOff, AlertCircle } from 'lucide-react';

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

const AuthPage = () => {
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  // If already signed in, redirect to /chat
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) navigate('/chat', { replace: true });
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) navigate('/chat', { replace: true });
    });

    return () => subscription.unsubscribe();
  }, [navigate]);

  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (isSignUp) {
        const { error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: window.location.origin },
        });
        if (signUpError) throw signUpError;
        toast({
          title: 'Check your email',
          description: 'We sent you a verification link to complete sign-up.',
        });
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
        if (signInError) throw signInError;
        navigate('/chat');
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
    try {
      // Configuration toggle: Use native Supabase OAuth for local Docker, 
      // Lovable OAuth wrapper for Lovable Cloud deployments.
      const useNativeOAuth = import.meta.env.VITE_USE_NATIVE_OAUTH === 'true';

      if (useNativeOAuth) {
        const { error: supabaseError } = await supabase.auth.signInWithOAuth({
          provider: 'google',
          options: {
            redirectTo: `${window.location.origin}/chat`,
          },
        });
        if (supabaseError) throw supabaseError;
        // The browser will redirect to the Google consent screen.
        return;
      }

      // Lovable Cloud wrapped OAuth path
      const result = await lovable.auth.signInWithOAuth('google', {
        redirect_uri: window.location.origin,
      });
      
      if (result.error) {
        const message = result.error instanceof Error ? result.error.message : 'Google sign-in failed. Please try again.';
        setError(message);
        return;
      }
      if (result.redirected) return; // browser will redirect
      
      // Tokens set — navigate
      navigate('/chat');
    } catch (err) {
      console.error('[Google Auth Error]', err);
      setError('Could not connect to Google. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        {/* Brand */}
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center mx-auto">
            <Sparkles className="w-6 h-6 text-ojas" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">AskMukthiGuru</h1>
          <p className="text-sm text-muted-foreground">
            {isSignUp ? 'Create your account' : 'Welcome back, dear seeker'}
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-sm">{error}</AlertDescription>
          </Alert>
        )}

        {/* Google */}
        <Button
          variant="outline"
          className="w-full h-11 gap-2"
          onClick={handleGoogleSignIn}
          disabled={loading}
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24">
            <path
              fill="currentColor"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
            />
            <path
              fill="currentColor"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="currentColor"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            />
            <path
              fill="currentColor"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            />
          </svg>
          Continue with Google
        </Button>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border/50" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-background px-2 text-muted-foreground">or</span>
          </div>
        </div>

        {/* Email form */}
        <form onSubmit={handleEmailAuth} className="space-y-4">
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
          <Button type="submit" className="w-full h-10 bg-ojas hover:bg-ojas-light text-primary-foreground" disabled={loading}>
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
      </div>
    </div>
  );
};

export default AuthPage;
