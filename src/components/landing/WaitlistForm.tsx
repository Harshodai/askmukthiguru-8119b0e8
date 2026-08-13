import { FormEvent, useState } from 'react';
import { BACKEND_URL } from '@/lib/backendUrl';

export const isWaitlistBuildEnabled = (value?: string): boolean =>
  (value ?? import.meta.env.VITE_WAITLIST_ENABLED)?.trim().toLowerCase() === 'true';

type FormStatus = 'idle' | 'submitting' | 'success' | 'error';

export function WaitlistForm() {
  const [email, setEmail] = useState('');
  const [consented, setConsented] = useState(false);
  const [formStatus, setFormStatus] = useState<FormStatus>('idle');
  const [error, setError] = useState('');

  if (!isWaitlistBuildEnabled()) return null;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!consented) {
      setError('Please confirm that we may contact you about early access.');
      return;
    }
    if (!BACKEND_URL) {
      setError('Early access is not available in this environment.');
      return;
    }
    setFormStatus('submitting');
    setError('');
    try {
      const response = await fetch(`${BACKEND_URL}/api/waitlist/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, consent_to_contact: true, source: 'landing_hero' }),
      });
      if (!response.ok) throw new Error('Waitlist request failed');
      setFormStatus('success');
    } catch {
      setFormStatus('error');
      setError('We could not save your request just now. Please try again shortly.');
    }
  };

  if (formStatus === 'success') {
    return <p role="status" className="mt-4 text-sm text-emerald-200">Thank you. We will let you know when early access opens.</p>;
  }

  return (
    <form onSubmit={submit} className="mx-auto mt-5 max-w-md rounded-xl bg-black/30 p-3 text-left ring-1 ring-white/15 backdrop-blur-sm" aria-label="Join early access">
      <p className="mb-2 text-center text-sm font-medium text-white">Join early access</p>
      <div className="flex gap-2">
        <label className="sr-only" htmlFor="waitlist-email">Email address</label>
        <input id="waitlist-email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" className="min-w-0 flex-1 rounded-md border border-white/20 bg-white/10 px-3 py-2 text-sm text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-ojas-gold" />
        <button type="submit" disabled={formStatus === 'submitting'} className="rounded-md bg-ojas px-3 py-2 text-sm font-semibold text-ojas-foreground disabled:cursor-not-allowed disabled:opacity-70">{formStatus === 'submitting' ? 'Joining…' : 'Join'}</button>
      </div>
      <label className="mt-2 flex items-start gap-2 text-xs leading-5 text-white/75">
        <input type="checkbox" checked={consented} onChange={(event) => setConsented(event.target.checked)} className="mt-1" />
        <span>I agree that AskMukthiGuru may retain my email to contact me about early access. <a href="/privacy" className="underline hover:text-white">Privacy</a>.</span>
      </label>
      {error && <p role="alert" className="mt-2 text-xs text-amber-200">{error}</p>}
    </form>
  );
}
