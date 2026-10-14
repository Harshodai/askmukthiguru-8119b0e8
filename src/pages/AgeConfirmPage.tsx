import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';

/**
 * RP-D1: post-login 18+ confirmation. OAuth and Google One Tap complete
 * without touching our signup UI, so the stored `age_confirmed` metadata is
 * the authority — `useRequireAuth` sends any signed-in user lacking it here.
 * Confirming writes the metadata and continues to the stored redirect path.
 */
export default function AgeConfirmPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session?.user) {
        navigate('/auth', { replace: true });
      } else if (session.user.user_metadata?.age_confirmed) {
        const dest = sessionStorage.getItem('auth_redirect_path') || '/chat';
        sessionStorage.removeItem('auth_redirect_path');
        navigate(dest, { replace: true });
      }
    });
  }, [navigate]);

  const onContinue = async () => {
    if (!confirmed) {
      setError(t('auth.ageConfirmRequired', { defaultValue: 'Please confirm you are 18 years of age or older to continue.' }));
      return;
    }
    setSaving(true);
    setError(null);
    const { error: updateError } = await supabase.auth.updateUser({
      data: { age_confirmed: true, age_confirmed_at: new Date().toISOString() },
    });
    setSaving(false);
    if (updateError) {
      setError(updateError.message);
      return;
    }
    const dest = sessionStorage.getItem('auth_redirect_path') || '/chat';
    sessionStorage.removeItem('auth_redirect_path');
    navigate(dest, { replace: true });
  };

  return (
    <div className="min-h-dvh flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-md space-y-4 rounded-2xl shadow-sm p-6 bg-card">
        <h1 className="text-xl font-semibold">
          {t('auth.ageConfirmTitle', { defaultValue: 'One quick check' })}
        </h1>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
            className="mt-1"
          />
          {t('auth.ageConfirm', { defaultValue: 'I confirm I am 18 years of age or older.' })}
        </label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button onClick={onContinue} disabled={saving} className="w-full h-10">
          {t('auth.continue', { defaultValue: 'Continue' })}
        </Button>
      </div>
    </div>
  );
}
