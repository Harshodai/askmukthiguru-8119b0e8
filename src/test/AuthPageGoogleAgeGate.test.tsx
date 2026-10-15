import { describe, it, expect, vi, beforeEach } from 'vitest';

// jsdom starts as a top-level frame (self === top), which renders the GSI
// container instead of the fallback OAuth button. `isTopLevelFrame` is a
// module-level const in AuthPage.tsx, so the frame must differ BEFORE the
// module imports.
//
// Seam notes (verified 2026-10-15 on this repo's vitest 4.1.11 + jsdom
// 20.0.3): `globalThis.jsdom.reconfigure({ windowTop })` exists but only
// mutates dom.window._top while test code reads a snapshot copy on the
// global, so it does NOT flip `window.self === window.top` here and is not
// usable alone. `Object.defineProperty(window, 'top', ...)` DOES flip the
// global copy (window.top is configurable in jsdom 20) and is the working
// seam. Real browsers mark window.top [LegacyUnforgeable]
// (non-configurable), so if a future jsdom follows suit the defineProperty
// throws — and the loud assertions below fail instead of silently asserting
// the GSI branch. (An injectable frame check in AuthPage.tsx would remove
// this coupling, but that source is out of scope for this test-only fix.)
try {
  Object.defineProperty(window, 'top', {
    writable: true,
    configurable: true,
    value: {} as unknown as Window & typeof globalThis,
  });
} catch {
  throw new Error(
    'AuthPageGoogleAgeGate: cannot simulate an embedded frame — window.top ' +
      'is non-configurable in this jsdom. AuthPage needs an injectable frame ' +
      'check before this test can run.',
  );
}

if (window.self === (window.top as unknown)) {
  throw new Error(
    'AuthPageGoogleAgeGate: embedded-frame seam did not take (self === top); ' +
      'aborting instead of asserting the wrong branch.',
  );
}

const { render, screen, fireEvent, waitFor } = await import('@testing-library/react');
const { MemoryRouter } = await import('react-router-dom');
const { default: AuthPage } = await import('@/pages/AuthPage');

const mockOAuth = vi.fn().mockResolvedValue({ data: null, error: null });

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      signUp: vi.fn(),
      signInWithPassword: vi.fn(),
      signInWithOAuth: (...args: unknown[]) => mockOAuth(...args),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
      mfa: {
        getAuthenticatorAssuranceLevel: vi.fn().mockResolvedValue({ data: null, error: null }),
      },
    },
    rpc: vi.fn().mockResolvedValue({ data: null, error: null }),
  },
  isEmailAllowed: vi.fn((email: string) => email.endsWith('@gmail.com')),
}));

vi.mock('@/hooks/usePageMeta', () => ({ usePageMeta: () => {} }));
vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));
vi.mock('@/lib/passwordBreachCheck', () => ({
  checkPasswordBreached: vi.fn().mockResolvedValue({ breached: false, count: 0 }),
  BREACHED_PASSWORD_MESSAGE: 'breached',
}));

// RP-D1: the Google OAuth button carries the same 18+ gate as email signup.
describe('AuthPage - 18+ age gate on Google sign up', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('blocks the Google button on sign up until the age checkbox is checked', async () => {
    render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /create account|sign up/i }));

    const googleBtn = screen.getByRole('button', { name: /google/i });
    fireEvent.click(googleBtn);

    await waitFor(() => {
      expect(screen.getByText(/confirm you are 18 years/i)).toBeInTheDocument();
    });
    expect(mockOAuth).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('checkbox', { name: /18 years/i }));
    fireEvent.click(googleBtn);
    await waitFor(() => {
      expect(mockOAuth).toHaveBeenCalledTimes(1);
    });
  });
});
