import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, Link } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ShieldCheck, Loader2, AlertCircle } from 'lucide-react';

/**
 * Extract a verified TOTP factor from the current Supabase session.
 * Used as a fallback when listFactors() fails in environments with mocked
 * auth endpoints or partial network coverage.
 */
async function getVerifiedFactorFromSession(): Promise<{ id: string } | null> {
  try {
    const { data } = await supabase.auth.getSession();
    const factors = data.session?.user?.factors ?? [];
    const verified = factors.find(
      (f: { status?: string; factor_type?: string }) =>
        f.status === 'verified' && f.factor_type === 'totp'
    );
    return verified ? { id: verified.id } : null;
  } catch {
    return null;
  }
}

const MFAChallengePage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [factorId, setFactorId] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
      if (!aal || aal.currentLevel === 'aal2' || aal.nextLevel !== 'aal2') {
        navigate('/chat', { replace: true });
        return;
      }

      const { data, error: fErr } = await supabase.auth.mfa.listFactors();
      if (cancelled) return;

      const verified = data?.totp?.find((f) => f.status === 'verified');

      if (verified) {
        setFactorId(verified.id);
        return;
      }

      // listFactors can fail in mocked test environments. Fall back to the
      // factors embedded in the signed JWT/session so the challenge can still
      // proceed and the user sees a real verification error instead of a blank
      // failure state.
      const sessionFactor = await getVerifiedFactorFromSession();
      if (sessionFactor) {
        setFactorId(sessionFactor.id);
        return;
      }

      if (fErr) {
        setError(t('auth.mfaLoadFailed', { defaultValue: 'Could not load MFA factors.' }));
        return;
      }

      navigate('/chat', { replace: true });
    })();

    return () => {
      cancelled = true;
    };
  }, [navigate, t]);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!factorId) {
      setError(t('auth.mfaNotReady', { defaultValue: 'MFA is not ready. Please refresh and try again.' }));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { data: challenge, error: cErr } = await supabase.auth.mfa.challenge({ factorId });
      if (cErr) throw cErr;
      const { error: vErr } = await supabase.auth.mfa.verify({
        factorId,
        challengeId: challenge.id,
        code: code.trim(),
      });
      if (vErr) throw vErr;
      const redirectPath = sessionStorage.getItem('auth_redirect_path');
      sessionStorage.removeItem('auth_redirect_path');
      const safeRedirect =
        redirectPath &&
        redirectPath.startsWith('/') &&
        !redirectPath.startsWith('//') &&
        !redirectPath.startsWith('/@') &&
        !redirectPath.includes('\\') &&
        !redirectPath.includes('@') &&
        !redirectPath.includes('://')
          ? redirectPath
          : '/chat';
      navigate(safeRedirect, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('auth.mfaVerifyFailed', { defaultValue: 'Verification failed.' }));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    await supabase.auth.signOut();
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
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="w-12 h-12 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center shadow-[0_0_24px_hsl(var(--ojas-gold)/0.35)]">
            <ShieldCheck className="w-6 h-6 text-ojas" />
          </div>
          <h1 className="text-xl font-sacred font-semibold text-foreground">{t('auth.twoFactorTitle')}</h1>
          <p className="text-sm text-muted-foreground italic">
            {t('auth.mfaPrompt', { defaultValue: 'Enter the 6-digit code from your authenticator app.' })}
          </p>
        </div>
        {error && (
          <div ref={errorRef} tabIndex={-1} id="mfa-error" className="outline-none">
            <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-sm">{error}</AlertDescription>
            </Alert>
          </div>
        )}
        <form onSubmit={handleVerify} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="mfa-code" className="text-xs text-muted-foreground">{t('auth.verificationCode')}</Label>
            <Input
              id="mfa-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              placeholder="123456"
              aria-invalid={!!error}
              aria-describedby={error ? 'mfa-error' : undefined}
              autoFocus
              required
            />
          </div>
          <Button type="submit" className="w-full h-10 bg-ojas hover:bg-ojas-light text-primary-foreground" disabled={loading || code.length !== 6} aria-live="polite">
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                {t('auth.pleaseWait')}
              </span>
            ) : (
              t('auth.verify', { defaultValue: 'Verify' })
            )}
          </Button>
          <Button type="button" variant="ghost" className="w-full text-xs text-muted-foreground hover:text-foreground" onClick={handleCancel}>
            {t('auth.mfaCancel', { defaultValue: 'Cancel and sign out' })}
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

export default MFAChallengePage;
