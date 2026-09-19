import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AuthPage from '@/pages/AuthPage';

/**
 * Regression for the "Google sign-in happens twice" report (2026-09-19).
 *
 * GSI can invoke its callback twice for one real sign-in (the auto-prompt
 * corner popup and the rendered button both funnel into the same handler).
 * The existing in-flight guard only stops a CONCURRENT duplicate. A second,
 * SEQUENTIAL callback arriving after the first has already resolved hits a
 * stale, single-use nonce, falls into the catch block's "Nonces mismatch"
 * branch, and used a single immediate getSession() check to decide whether
 * the user is already signed in -- a lost race there fired a second,
 * visible signInWithOAuth redirect, which is the "authorize Supabase" prompt
 * users were seeing on top of the completed Google sign-in.
 */

const mockSignInWithIdToken = vi.fn();
const mockSignInWithOAuth = vi.fn();
const mockGetSession = vi.fn();

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      signUp: vi.fn(),
      signInWithPassword: vi.fn(),
      signInWithIdToken: (...args: unknown[]) => mockSignInWithIdToken(...args),
      signInWithOAuth: (...args: unknown[]) => mockSignInWithOAuth(...args),
      getSession: (...args: unknown[]) => mockGetSession(...args),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      mfa: {
        getAuthenticatorAssuranceLevel: vi.fn().mockResolvedValue({ data: null, error: null }),
      },
    },
    rpc: vi.fn().mockResolvedValue({ data: null, error: null }),
  },
  isEmailAllowed: vi.fn(() => true),
}));

vi.mock('@/hooks/usePageMeta', () => ({ usePageMeta: () => {} }));
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));

/** Renders AuthPage and returns the GSI callback Google's SDK would invoke. */
async function renderAndCaptureGsiCallback(): Promise<(res: { credential: string }) => void> {
  let capturedCallback: ((res: { credential: string }) => void) | null = null;

  (window as unknown as { google: unknown }).google = {
    accounts: {
      id: {
        initialize: (opts: { callback: (res: { credential: string }) => void }) => {
          capturedCallback = opts.callback;
        },
        renderButton: vi.fn(),
        prompt: vi.fn(),
      },
    },
  };
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
  vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id.apps.googleusercontent.com');

  render(
    <MemoryRouter>
      <AuthPage />
    </MemoryRouter>,
  );

  await waitFor(() => expect(capturedCallback).not.toBeNull());
  return capturedCallback as unknown as (res: { credential: string }) => void;
}

describe('AuthPage - Google One Tap sequential double-callback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSession.mockResolvedValue({ data: { session: null }, error: null });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    delete (window as unknown as { google?: unknown }).google;
  });

  it('does not fire a second visible OAuth redirect when a sequential duplicate callback arrives after the first already succeeded', async () => {
    const gsiCallback = await renderAndCaptureGsiCallback();

    // First callback: succeeds.
    mockSignInWithIdToken.mockResolvedValueOnce({
      data: { session: { user: { id: 'u1' } } },
      error: null,
    });
    gsiCallback({ credential: 'first-credential' });
    await waitFor(() => expect(mockSignInWithIdToken).toHaveBeenCalledTimes(1));

    // Second, SEQUENTIAL callback (not concurrent -- the first has already
    // resolved and cleared its in-flight ref by the time this runs): its
    // nonce is stale and Supabase rejects it.
    mockSignInWithIdToken.mockResolvedValueOnce({
      data: { session: null },
      error: new Error('Nonces mismatch'),
    });
    gsiCallback({ credential: 'second-credential' });
    await waitFor(() => expect(mockSignInWithIdToken).toHaveBeenCalledTimes(2));

    // Give the catch block's synchronous "just succeeded" check a tick.
    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(mockSignInWithOAuth).not.toHaveBeenCalled();
  });

  it('negative control: falls back to a visible OAuth redirect when neither the just-succeeded flag nor getSession show a session', async () => {
    const gsiCallback = await renderAndCaptureGsiCallback();

    // A callback whose nonce is stale but which did NOT follow a real,
    // just-completed sign-in in this tab (both signals say "not signed in"):
    // the fallback redirect is the correct, intended behavior here.
    mockSignInWithIdToken.mockResolvedValueOnce({
      data: { session: null },
      error: new Error('Nonces mismatch'),
    });
    mockSignInWithOAuth.mockResolvedValueOnce({ data: {}, error: null });

    gsiCallback({ credential: 'orphan-credential' });
    // The retry loop intentionally waits 0+150+400ms before falling back.
    await waitFor(() => expect(mockSignInWithOAuth).toHaveBeenCalledTimes(1), {
      timeout: 2000,
    });
  });
});
