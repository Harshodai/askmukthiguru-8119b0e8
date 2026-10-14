import { describe, it, expect, vi, beforeEach } from 'vitest';

// jsdom is a top-level frame, which renders the GSI container instead of the
// fallback OAuth button. `isTopLevelFrame` is a module-level const in
// AuthPage.tsx, so the frame must differ BEFORE the module imports.
Object.defineProperty(window, 'top', {
  writable: true,
  configurable: true,
  value: {} as unknown as Window & typeof globalThis,
});

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
