import { FormEvent, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PublicShell } from '@/components/layout/PublicShell';
import { usePageMeta } from '@/hooks/usePageMeta';
import { buildCanonical } from '@/lib/domain';
import { sanitizeLaunchEmail, submitLaunchErase } from '@/lib/launchUpdates';

type Status = 'idle' | 'working' | 'done' | 'error';

/** Withdraw consent and erase a launch-list address (DPDP). Not indexed. */
const UnsubscribePage = () => {
  const { t } = useTranslation();
  const emailId = useId();
  const [params] = useSearchParams();
  const token = params.get('token');
  const [email, setEmail] = useState(params.get('email') ?? '');
  const [status, setStatus] = useState<Status>('idle');

  usePageMeta({
    title: t('unsubscribe.pageTitle', { defaultValue: 'Unsubscribe from launch updates — AskMukthiGuru' }),
    description: t('unsubscribe.intro', {
      defaultValue: 'Enter the email address you signed up with. If it is on the launch list, it is erased now.',
    }),
    canonical: buildCanonical('/unsubscribe'),
    noindex: true,
  });

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (status === 'working') return;
    if (!sanitizeLaunchEmail(email)) {
      setStatus('error');
      return;
    }
    setStatus('working');
    const result = await submitLaunchErase(email, token);
    setStatus(result.status === 'accepted' ? 'done' : 'error');
  };

  return (
    <PublicShell>
      <main className="max-w-xl mx-auto px-4 sm:px-6 py-12 space-y-4">
        <h1 className="text-2xl font-semibold text-foreground">
          {t('unsubscribe.title', { defaultValue: 'Unsubscribe from launch updates' })}
        </h1>
        {status === 'done' ? (
          <p role="status" className="text-sm text-foreground">
            {t('unsubscribe.done', {
              defaultValue: 'If that address was on the launch list, it has been erased. Nothing else is kept.',
            })}
          </p>
        ) : (
          <form onSubmit={submit} className="space-y-3" noValidate>
            <p className="text-sm text-muted-foreground">
              {t('unsubscribe.intro', {
                defaultValue:
                  'Enter the email address you signed up with. If it is on the launch list, it is erased now.',
              })}
            </p>
            <div className="space-y-1.5">
              <Label htmlFor={emailId}>{t('launchUpdates.emailLabel', { defaultValue: 'Email address' })}</Label>
              <Input
                id={emailId}
                type="email"
                autoComplete="email"
                inputMode="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={status === 'working'}
              />
            </div>
            <Button type="submit" disabled={status === 'working'} aria-busy={status === 'working'}>
              {status === 'working'
                ? t('unsubscribe.working', { defaultValue: 'Erasing…' })
                : t('unsubscribe.button', { defaultValue: 'Erase my email' })}
            </Button>
            {status === 'error' ? (
              <p role="alert" className="text-sm text-destructive">
                {t('unsubscribe.error', {
                  defaultValue: 'We could not process that. Check the address and try again.',
                })}
              </p>
            ) : null}
          </form>
        )}
        <Link to="/privacy" className="inline-flex text-sm underline underline-offset-2">
          {t('launchUpdates.privacyLink', { defaultValue: 'Privacy' })}
        </Link>
      </main>
    </PublicShell>
  );
};

export default UnsubscribePage;
