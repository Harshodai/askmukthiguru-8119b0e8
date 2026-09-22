import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AuthPage from '@/pages/AuthPage';
import * as passwordBreachModule from '@/lib/passwordBreachCheck';

// Mock Supabase client
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

describe('AuthPage - Leaked Password Protection on Sign Up', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('rejects sign up with known breached password ("password123") and does NOT call Supabase signUp', async () => {
    vi.spyOn(passwordBreachModule, 'checkPasswordBreached').mockResolvedValue({
      breached: true,
      count: 2266543,
    });

    const { container } = render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>,
    );

    // Switch to Sign Up tab
    const signUpTabButton = screen.getByRole('button', { name: /create account|sign up/i });
    fireEvent.click(signUpTabButton);

    // Fill form
    const nameInput = container.querySelector('#fullName') as HTMLInputElement;
    const emailInput = container.querySelector('#email') as HTMLInputElement;
    const passwordInput = container.querySelector('#password') as HTMLInputElement;

    expect(nameInput).toBeDefined();
    expect(emailInput).toBeDefined();
    expect(passwordInput).toBeDefined();

    fireEvent.change(nameInput, { target: { value: 'Seeker John' } });
    fireEvent.change(emailInput, { target: { value: 'seeker@gmail.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /18 years/i }));

    // Submit form
    const submitBtn = screen.getByRole('button', { name: /create account/i });
    fireEvent.click(submitBtn);

    // Verify breached message is displayed
    await waitFor(() => {
      expect(screen.getByText(/This password has appeared in a known data breach/i)).toBeInTheDocument();
    });

    // Verify Supabase signUp was NEVER called
    expect(mockSignUp).not.toHaveBeenCalled();
  });

  it('allows sign up with clean unbreached password and proceeds to Supabase signUp', async () => {
    vi.spyOn(passwordBreachModule, 'checkPasswordBreached').mockResolvedValue({
      breached: false,
      count: 0,
    });
    mockSignUp.mockResolvedValue({
      data: { user: { id: 'u123', identities: [{}] }, session: null },
      error: null,
    });

    const { container } = render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>,
    );

    // Switch to Sign Up tab
    const signUpTabButton = screen.getByRole('button', { name: /create account|sign up/i });
    fireEvent.click(signUpTabButton);

    // Fill form
    const nameInput = container.querySelector('#fullName') as HTMLInputElement;
    const emailInput = container.querySelector('#email') as HTMLInputElement;
    const passwordInput = container.querySelector('#password') as HTMLInputElement;

    fireEvent.change(nameInput, { target: { value: 'Seeker Jane' } });
    fireEvent.change(emailInput, { target: { value: 'seeker2@gmail.com' } });
    fireEvent.change(passwordInput, { target: { value: 'SuperSecretUniquePass_2026!#$' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /18 years/i }));

    // Submit form
    const submitBtn = screen.getByRole('button', { name: /create account/i });
    fireEvent.click(submitBtn);

    // Verify Supabase signUp WAS called
    await waitFor(() => {
      expect(mockSignUp).toHaveBeenCalledWith({
        email: 'seeker2@gmail.com',
        password: 'SuperSecretUniquePass_2026!#$',
        options: {
          emailRedirectTo: expect.any(String),
          data: {
            full_name: 'Seeker Jane',
            age_confirmed: true,
            age_confirmed_at: expect.any(String),
          },
        },
      });
    });
  });
});
