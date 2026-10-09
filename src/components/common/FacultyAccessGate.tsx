import { useState, type FormEvent, type ReactNode } from 'react';
import {
  checkFacultyCode,
  facultyGateEnabled,
  getFacultyCode,
  installFacultyFetchHeader,
  setFacultyCode,
} from '@/lib/facultyAccess';

installFacultyFetchHeader();

/** Blocks the app behind a passcode during the faculty preview. Renders children untouched when the gate is off. */
export function FacultyAccessGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(() => !facultyGateEnabled() || getFacultyCode() !== '');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (unlocked) return <>{children}</>;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const entered = code.trim();
    if (!entered) return;
    setBusy(true);
    setError('');
    const result = await checkFacultyCode(entered);
    setBusy(false);
    if (result === 'ok') {
      setFacultyCode(entered);
      setUnlocked(true);
    } else {
      setError(result === 'wrong' ? 'That code is not right. Please try again.' : 'Could not reach the server. Please try again shortly.');
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4" aria-labelledby="faculty-gate-title">
        <h1 id="faculty-gate-title" className="text-xl font-semibold">Faculty preview</h1>
        <p className="text-sm opacity-80">This preview is limited to invited reviewers. Enter the access code you were given.</p>
        <label className="block text-sm">
          Access code
          <input
            type="password"
            autoComplete="off"
            value={code}
            onChange={(ev) => setCode(ev.target.value)}
            className="mt-1 w-full rounded border px-3 py-2 bg-transparent"
          />
        </label>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button type="submit" disabled={busy || !code.trim()} className="w-full rounded px-3 py-2 border font-medium disabled:opacity-50">
          {busy ? 'Checking…' : 'Continue'}
        </button>
      </form>
    </main>
  );
}
