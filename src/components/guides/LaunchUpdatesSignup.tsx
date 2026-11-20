import { FormEvent, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  isPlausibleLaunchEmail,
  sanitizeLaunchEmail,
  submitLaunchSignup,
  type LaunchSignupSource,
} from '@/lib/launchUpdates';

type FormStatus = 'idle' | 'submitting' | 'success' | 'error';

const REQUEST_FAILED =
  'We could not save your request just now. Please check your connection and try again.';

/**
 * Consent-first launch update signup shared by the public guides.
 *
 * - The email label is visible, not screen-reader only.
 * - Contact consent starts unchecked and is required before any request.
 * - Pending, success and error states are announced.
 * - The typed address is kept when a request fails so retry is one click.
 * - Nothing here claims an email is being sent: this only stores the opt-in.
 */
export function LaunchUpdatesSignup({ source }: { source: LaunchSignupSource }) {
  const { t } = useTranslation();
  const titleId = useId();
  const emailId = useId();
  const consentId = useId();
  const errorId = useId();

  const [email, setEmail] = useState('');
  const [consented, setConsented] = useState(false);
  const [status, setStatus] = useState<FormStatus>('idle');
  const [error, setError] = useState('');

  const pending = status === 'submitting';

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) return;

    const normalized = sanitizeLaunchEmail(email);
    if (!normalized) {
      setStatus('error');
      setError('Enter your email address.');
      return;
    }
    if (!isPlausibleLaunchEmail(normalized)) {
      setStatus('error');
      setError('Enter a valid email address.');
      return;
    }
    if (!consented) {
      setStatus('error');
      setError('Please confirm that AskMukthiGuru may email you about launch updates.');
      return;
    }

    setStatus('submitting');
    setError('');
    const result = await submitLaunchSignup({ email: normalized, source });
    if (result.status === 'accepted') {
      setStatus('success');
      return;
    }
    setStatus('error');
    setError(REQUEST_FAILED);
  };

  return (
    <section
      aria-labelledby={titleId}
      className="space-y-3 rounded-xl border border-border bg-card/60 p-4 sm:p-6"
    >
      <div className="space-y-1">
        <h2 id={titleId} className="text-lg font-semibold text-foreground">
          Launch updates by email
        </h2>
        <p className="text-sm text-muted-foreground">
          Occasional email when new guides or practices are ready. No account needed.
        </p>
      </div>

      {status === 'success' ? (
        <p role="status" className="text-sm text-foreground">
          You are on the launch list. We will contact you only about launch updates.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-3" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor={emailId}>{t('launchUpdates.emailLabel', { defaultValue: 'Email address' })}</Label>
            <Input
              id={emailId}
              type="email"
              name="email"
              autoComplete="email"
              inputMode="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={status === 'error' ? true : undefined}
              aria-describedby={status === 'error' && error ? errorId : undefined}
              disabled={pending}
            />
          </div>

          <div className="flex items-start gap-2">
            <Checkbox
              id={consentId}
              checked={consented}
              onCheckedChange={(checked) => setConsented(checked === true)}
              disabled={pending}
              aria-describedby={status === 'error' && error ? errorId : undefined}
              className="mt-0.5"
            />
            <Label
              htmlFor={consentId}
              className="text-sm font-normal leading-5 text-muted-foreground"
            >
              {t('launchUpdates.consentLabel', {
                defaultValue:
                  'I agree that AskMukthiGuru may keep this email to contact me about launch updates.',
              })}
            </Label>
          </div>
          <p className="text-xs text-muted-foreground">
            {t('launchUpdates.notice', {
              defaultValue:
                'Used only for launch updates. Kept for up to 12 months, then deleted. You can withdraw and erase it at any time.',
            })}{' '}
            <Link to="/privacy" className="underline underline-offset-2 hover:text-foreground">
              {t('launchUpdates.privacyLink', { defaultValue: 'Privacy' })}
            </Link>
            {' · '}
            <Link to="/unsubscribe" className="underline underline-offset-2 hover:text-foreground">
              {t('launchUpdates.unsubscribeLink', { defaultValue: 'Unsubscribe and erase my email' })}
            </Link>
          </p>

          <Button type="submit" disabled={pending} aria-busy={pending}>
            {pending ? 'Joining…' : 'Join launch list'}
          </Button>

          {status === 'error' && error ? (
            <p id={errorId} role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
        </form>
      )}
    </section>
  );
}
