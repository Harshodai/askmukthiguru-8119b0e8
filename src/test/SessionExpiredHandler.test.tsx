import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

const { navigateMock, onAuthStateChangeMock, isEmailAllowedMock, signOutMock, toastErrorMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  onAuthStateChangeMock: vi.fn(() => ({
    data: { subscription: { unsubscribe: vi.fn() } },
  })),
  isEmailAllowedMock: vi.fn(() => true),
  signOutMock: vi.fn().mockResolvedValue({}),
  toastErrorMock: vi.fn(),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
  useLocation: () => ({ pathname: '/chat', search: '' }),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      onAuthStateChange: onAuthStateChangeMock,
      signOut: signOutMock,
    },
  },
  isEmailAllowed: isEmailAllowedMock,
}));

vi.mock('sonner', () => ({
  toast: {
    error: toastErrorMock,
  },
}));

import { SessionExpiredHandler } from '@/components/common/SessionExpiredHandler';

describe('SessionExpiredHandler', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    onAuthStateChangeMock.mockClear();
    isEmailAllowedMock.mockReset();
    isEmailAllowedMock.mockReturnValue(true);
    signOutMock.mockReset();
    signOutMock.mockResolvedValue({});
    toastErrorMock.mockReset();
    sessionStorage.clear();
  });

  it('does not show toast or redirect on first mount if user was never signed in', () => {
    let authCallback: any;
    onAuthStateChangeMock.mockImplementation((callback) => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });

    render(<SessionExpiredHandler />);

    // Simulate initial SIGNED_OUT event on mount when user is null
    authCallback('SIGNED_OUT', null);

    expect(toastErrorMock).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('shows toast and redirects on natural SIGNED_OUT event after user was signed in', () => {
    let authCallback: any;
    onAuthStateChangeMock.mockImplementation((callback) => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });

    render(<SessionExpiredHandler />);

    // Simulate initial SIGNED_IN event with valid user
    authCallback('SIGNED_IN', { user: { email: 'allowed@gmail.com' } });

    // Simulate subsequent natural SIGNED_OUT event
    authCallback('SIGNED_OUT', null);

    expect(toastErrorMock).toHaveBeenCalledWith('Your session has ended', expect.any(Object));
    expect(navigateMock).toHaveBeenCalledWith('/auth', { replace: true });
  });

  it('does not show toast but redirects on explicit/auto-triggered signout', async () => {
    let authCallback: any;
    onAuthStateChangeMock.mockImplementation((callback) => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });

    render(<SessionExpiredHandler />);

    // Simulate initial SIGNED_IN event
    authCallback('SIGNED_IN', { user: { email: 'allowed@gmail.com' } });

    // Simulate explicit signout triggering (sets session storage)
    sessionStorage.setItem('auth_explicit_signout', 'true');

    // Simulate subsequent SIGNED_OUT event
    authCallback('SIGNED_OUT', null);

    expect(toastErrorMock).not.toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith('/auth', { replace: true });
    expect(sessionStorage.getItem('auth_explicit_signout')).toBeNull(); // verify flag gets cleared
  });

  it('auto-signs out and redirects user with disallowed email domain on mount', async () => {
    let authCallback: any;
    onAuthStateChangeMock.mockImplementation((callback) => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });
    isEmailAllowedMock.mockReturnValue(false);

    render(<SessionExpiredHandler />);

    // Simulate initial SIGNED_IN event with unallowed email
    await authCallback('SIGNED_IN', { user: { email: 'spam@unallowed.com' } });

    expect(signOutMock).toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith('/auth', { replace: true });
  });
});
