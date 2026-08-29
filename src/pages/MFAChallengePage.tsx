import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ShieldCheck, Loader2 } from 'lucide-react';

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
  const navigate = useNavigate();
  const [factorId, setFactorId] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        setError('Could not load MFA factors.');
        return;
      }

      navigate('/chat', { replace: true });
    })();

    return () => {
      cancelled = true;
    };
  }, [navigate]);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!factorId) {
      setError('MFA is not ready. Please refresh and try again.');
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
      const safeRedirect = redirectPath && redirectPath.startsWith('/') && !redirectPath.startsWith('//') && !redirectPath.includes('\\')
        ? redirectPath
        : '/chat';
      navigate(safeRedirect, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    await supabase.auth.signOut();
    navigate('/auth', { replace: true });
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-6 rounded-lg border bg-card p-8 shadow-sm">
        <div className="flex flex-col items-center text-center space-y-2">
          <ShieldCheck className="h-10 w-10 text-primary" />
          <h1 className="text-2xl font-semibold">Two-factor authentication</h1>
          <p className="text-sm text-muted-foreground">
            Enter the 6-digit code from your authenticator app.
          </p>
        </div>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <form onSubmit={handleVerify} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="mfa-code">Verification code</Label>
            <Input
              id="mfa-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              placeholder="123456"
              required
            />
          </div>
          <Button type="submit" className="w-full" disabled={loading || code.length !== 6}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Verify'}
          </Button>
          <Button type="button" variant="ghost" className="w-full" onClick={handleCancel}>
            Cancel and sign out
          </Button>
        </form>
      </div>
    </div>
  );
};

export default MFAChallengePage;
