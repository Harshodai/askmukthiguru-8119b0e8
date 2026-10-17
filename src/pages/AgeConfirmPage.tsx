import { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ShieldCheck, AlertCircle, Loader2 } from 'lucide-react';

/**
 * RP-D1: post-login 18+ confirmation. OAuth and Google One Tap complete
 * without touching our signup UI, so the stored `age_confirmed` metadata is
 * the authority — `useRequireAuth` sends any signed-in user lacking it here.
 * Confirming writes the metadata and continues to the stored redirect path.
 */

const FALLBACK_DEST = '/chat';

// Same predicate as AuthPage's isSafeRelativePath: sessionStorage is
// attacker-writable (XSS or a crafted link), so a stored redirect must be a
// same-origin relative path before we navigate to it.
const isSafeDest = (url: string | null): url is string =>
  Boolean(url && url.startsWith('/') && !url.startsWith('//') && !url.includes('\\'));

function consumeDest(): string {
  const raw = sessionStorage.getItem('auth_redirect_path');
  sessionStorage.removeItem('auth_redirect_path');
  return isSafeDest(raw) ? raw : FALLBACK_DEST;
}
export default function AgeConfirmPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  useEffect(() => {
    let cancelled = false;
    supabase.auth
      .getSession()
      .then(({ data: { session } }) => {
        if (cancelled) return;
        if (!session?.user) {
          navigate('/auth', { replace: true });
        } else if (session.user.user_metadata?.age_confirmed) {
          navigate(consumeDest(), { replace: true });
        }
      })
      .catch(() => {
        if (!cancelled) {
          navigate('/auth', { replace: true });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  const onContinue = async () => {
    if (!confirmed) {
      setError(t('auth.ageConfirmRequired', { defaultValue: 'Please confirm you are 18 years of age or older to continue.' }));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const { error: updateError } = await supabase.auth.updateUser({
        data: { age_confirmed: true, age_confirmed_at: new Date().toISOString() },
      });
      if (updateError) {
        setError(updateError.message);
        return;
      }
      const dest = consumeDest();
      navigate(dest, { replace: true });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg || t('auth.ageConfirmFailed', { defaultValue: 'Failed to confirm age. Please try again.' }));
    } finally {
      setSaving(false);
    }
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
            <ShieldCheck className="w-6 h-6 text-ojas" />
          </div>
          <h1 className="text-xl font-sacred font-semibold text-foreground">
            {t('auth.ageConfirmTitle', { defaultValue: 'One quick check' })}
          </h1>
          <p className="text-sm text-muted-foreground italic">
            {t('auth.ageConfirmSubtitle', { defaultValue: 'AskMukthiGuru is for adults. Please confirm your age to continue.' })}
          </p>
        </div>

        {error && (
          <div ref={errorRef} tabIndex={-1} id="age-confirm-error" className="outline-none">
            <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-sm">{error}</AlertDescription>
            </Alert>
          </div>
        )}
        <div className="flex items-start gap-2.5 text-left rounded-xl ring-1 ring-border/40 bg-foreground/[0.03] p-3">
          <input
            id="age-confirm-checkbox"
            type="checkbox"
            checked={confirmed}
            onChange={(e) => { setConfirmed(e.target.checked); setError(null); }}
            className="mt-0.5 h-4 w-4 shrink-0 rounded border-border/60 text-ojas focus:ring-ojas"
            autoFocus
            aria-describedby={error ? 'age-confirm-error' : undefined}
          />
          <Label htmlFor="age-confirm-checkbox" className="text-sm text-foreground font-normal cursor-pointer">
            {t('auth.ageConfirm', { defaultValue: 'I confirm I am 18 years of age or older.' })}
          </Label>
        </div>
            <Button onClick={onContinue} disabled={saving} className="w-full h-10 bg-ojas hover:bg-ojas-light text-primary-foreground" aria-live="polite">
              {saving ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  {t('auth.pleaseWait')}
                </span>
              ) : (
                t('auth.continue', { defaultValue: 'Continue' })
              )}
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              <Link to="/auth" className="hover:text-foreground hover:underline">
                {t('auth.backToSignIn', { defaultValue: 'Back to sign in' })}
              </Link>
            </p>
      </div>
    </div>
  );
}
