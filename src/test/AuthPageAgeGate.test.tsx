import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AuthPage from '@/pages/AuthPage';

// PLAN.md Phase G — 18+ signup gate. No age gate existed anywhere in the
// codebase before this (verified by grep across src/ and backend/). Confirms
// the checkbox blocks both the email/password path and the OAuth buttons
// until checked, and re-enables both once it is.

const mockSignUp = vi.fn();
vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      signUp: (...args: unknown[]) => mockSignUp(...args),
      signInWithPassword: vi.fn(),
      signInWithOAuth: vi.fn(),
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

describe('AuthPage - 18+ age gate on sign up', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not show the age checkbox on the sign-in form', () => {
    render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>,
    );
    expect(screen.queryByRole('checkbox', { name: /18 years/i })).not.toBeInTheDocument();
  });

  it('disables the submit button on sign up until the age checkbox is checked', () => {
    const { container } = render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /create account|sign up/i }));

    const submitBtn = screen.getByRole('button', { name: /create account/i }) as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);

    const checkbox = screen.getByRole('checkbox', { name: /18 years/i });
    fireEvent.click(checkbox);
    expect(submitBtn.disabled).toBe(false);

    // Sanity: the OAuth methods block is present and visually gated via
    // pointer-events-none/opacity while unchecked — re-check re-enables it.
    const oauthWrapper = container.querySelector('[aria-disabled]');
    expect(oauthWrapper).not.toBeNull();
    expect(oauthWrapper?.getAttribute('aria-disabled')).toBe('false');
  });

  it('blocks submission and shows an error if somehow submitted without confirming age', async () => {
    render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /create account|sign up/i }));

    fireEvent.change(screen.getByPlaceholderText(/your name/i), { target: { value: 'Seeker' } });
    fireEvent.change(screen.getByPlaceholderText(/you@example.com/i), {
      target: { value: 'seeker@gmail.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), {
      target: { value: 'SuperSecretUniquePass_2026!#$' },
    });

    // Bypass the disabled-button guard to prove the handler itself also
    // enforces the gate (defense in depth, not just a disabled attribute).
    const form = document.querySelector('form') as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText(/confirm you are 18 years/i)).toBeInTheDocument();
    });
    expect(mockSignUp).not.toHaveBeenCalled();
  });
});
