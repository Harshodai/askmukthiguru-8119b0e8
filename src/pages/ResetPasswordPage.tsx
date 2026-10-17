import { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { AuthApiError } from '@supabase/supabase-js';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { Sparkles, Lock, AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react';
import { usePageMeta } from '@/hooks/usePageMeta';
import { useTranslation } from 'react-i18next';
import { buildCanonical } from '@/lib/domain';
import { checkPasswordBreached, BREACHED_PASSWORD_MESSAGE } from '@/lib/passwordBreachCheck';

const ResetPasswordPage = () => {
  usePageMeta({
    title: 'Reset your password — AskMukthiGuru',
    description: 'Set a new password for your AskMukthiGuru account.',
    canonical: buildCanonical('/reset-password'),
  });
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t } = useTranslation();
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  // The recovery flow lands here two ways: legacy implicit tokens in the hash
  // (#access_token=...&type=recovery) or PKCE `?code=` in the query string.
  // (Hash check reads window.location.hash directly: under native HashRouter
  // the route itself lives in the hash, so query params are checked too.)
  // Supabase auto-exchanges either form; we just wait for a session to appear.
  useEffect(() => {
    const looksLikeRecovery = () =>
      window.location.hash.includes('type=recovery') ||
      new URLSearchParams(window.location.search).has('code');
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY' || (session?.user && looksLikeRecovery())) {
        setReady(true);
      }
    });
    // The onAuthStateChange handler above flips ready when the exchange
    // lands; this covers the already-exchanged case.
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) setReady(true);
    });
    return () => subscription.unsubscribe();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 12) return setError(t('auth.resetMinLength', { defaultValue: 'Password must be at least 12 characters.' }));
    if (password !== confirm) return setError(t('auth.resetMismatch', { defaultValue: 'Passwords do not match.' }));

    setLoading(true);
    const breachCheck = await checkPasswordBreached(password);
    if (breachCheck.breached) {
      setLoading(false);
      const msg = t('auth.passwordBreached', BREACHED_PASSWORD_MESSAGE);
      setError(msg);
      toast({
        title: t('auth.passwordInsecure', { defaultValue: 'Password Insecure' }),
        description: msg,
        variant: 'destructive',
      });
      return;
    }
    try {
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) throw updateError;
    } catch (error: unknown) {
      setLoading(false);
      const msg = error instanceof AuthApiError
        ? (error.message.includes('expired')
          ? t('auth.resetLinkExpired', { defaultValue: 'Password reset link has expired. Please request a new one.' })
          : error.message)
        : t('auth.resetFailed', { defaultValue: 'Failed to reset password. Please try again.' });
      setError(msg);
      toast({
        title: t('auth.resetFailedTitle', { defaultValue: 'Password Reset Failed' }),
        description: msg,
        variant: 'destructive',
      });
      return;
    }
    setLoading(false);
    toast({ title: t('auth.resetDoneTitle', { defaultValue: 'Password updated' }), description: t('auth.resetDoneDesc', { defaultValue: 'You can now sign in with your new password.' }) });
    navigate('/auth', { replace: true });
  };

  return (
    <div className="min-h-dvh flex items-center justify-center bg-gradient-to-br from-background via-ojas/5 to-background px-4 py-10 relative overflow-hidden">
      {/* Ambient radial glow — same Sacred Minimal auth shell as AuthPage */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 40% at 50% 0%, hsl(var(--ojas-gold) / 0.10), transparent 70%)',
        }}
      />
      <div className="relative w-full max-w-[400px] mx-4 sm:mx-auto space-y-5 rounded-2xl backdrop-blur-2xl bg-card/60 ring-1 ring-border/40 shadow-2xl shadow-foreground/10 p-6 sm:p-8">
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center mx-auto shadow-[0_0_24px_hsl(var(--ojas-gold)/0.35)]">
            <Sparkles className="w-6 h-6 text-ojas" />
          </div>
          <h1 className="text-xl font-sacred font-semibold text-foreground">
            {t('auth.resetTitle', { defaultValue: 'Set a new password' })}
          </h1>
          <p className="text-sm text-muted-foreground italic">
            {t('auth.resetSubtitle', { defaultValue: 'Choose something memorable, dear seeker.' })}
          </p>
        </div>

        {!ready && (
          <Alert className="border-border/50">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-sm">
              {t('auth.resetVerifying', { defaultValue: 'Verifying your reset link… If nothing happens, request a new link from the sign-in page.' })}{' '}
              <Link to="/auth" className="text-foreground hover:underline font-medium">
                {t('auth.backToSignIn', { defaultValue: 'Back to sign in' })}
              </Link>
            </AlertDescription>
          </Alert>
        )}

        {error && (
          <div ref={errorRef} tabIndex={-1} id="reset-error" className="outline-none">
            <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-sm">{error}</AlertDescription>
            </Alert>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="pw" className="text-xs text-muted-foreground">
              {t('auth.resetNewPassword', { defaultValue: 'New password' })}
            </Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="pw"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="pl-9 pr-9 h-10"
                autoComplete="new-password"
                aria-invalid={!!error}
                aria-describedby={error ? 'reset-error' : undefined}
                autoFocus
                required
                minLength={12}
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
          <div className="space-y-2">
            <Label htmlFor="pw2" className="text-xs text-muted-foreground">
              {t('auth.resetConfirmPassword', { defaultValue: 'Confirm password' })}
            </Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="pw2"
                type={showConfirm ? 'text' : 'password'}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="pl-9 pr-9 h-10"
                autoComplete="new-password"
                aria-invalid={!!error}
                aria-describedby={error ? 'reset-error' : undefined}
                required
                minLength={12}
              />
              <button
                type="button"
                onClick={() => setShowConfirm(!showConfirm)}
                aria-label={showConfirm ? t('auth.hidePassword') : t('auth.showPassword')}
                aria-pressed={showConfirm}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <Button type="submit" className="w-full h-10 bg-ojas hover:bg-ojas-light text-primary-foreground" disabled={loading || !ready} aria-live="polite">
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                {t('auth.resetUpdating', { defaultValue: 'Updating…' })}
              </span>
            ) : (
              t('auth.resetUpdateBtn', { defaultValue: 'Update password' })
            )}
          </Button>
        </form>
        <p className="text-center text-xs text-muted-foreground">
          <Link to="/auth" className="hover:text-foreground hover:underline">
            {t('auth.backToSignIn', { defaultValue: 'Back to sign in' })}
          </Link>
        </p>
      </div>
    </div>
  );
};

export default ResetPasswordPage;
