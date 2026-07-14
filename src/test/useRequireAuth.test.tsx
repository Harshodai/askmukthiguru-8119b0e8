import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const { navigateMock, getSessionMock, onAuthStateChangeMock, isEmailAllowedMock, signOutMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  getSessionMock: vi.fn(),
  onAuthStateChangeMock: vi.fn(() => ({
    data: { subscription: { unsubscribe: vi.fn() } },
  })),
  isEmailAllowedMock: vi.fn((email: string | undefined | null) => true),
  signOutMock: vi.fn().mockResolvedValue({}),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: getSessionMock,
      onAuthStateChange: onAuthStateChangeMock,
      signOut: signOutMock,
    },
  },
  isEmailAllowed: (email: string | undefined | null) => isEmailAllowedMock(email),
}));

import { useRequireAuth } from '@/hooks/useRequireAuth';

describe('useRequireAuth', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    getSessionMock.mockReset();
    onAuthStateChangeMock.mockClear();
    isEmailAllowedMock.mockReset();
    isEmailAllowedMock.mockImplementation(() => true);
    signOutMock.mockReset();
    signOutMock.mockResolvedValue({});
    sessionStorage.clear();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { pathname: '/chat', search: '' },
    });
  });

  it('redirects unauthenticated users to /auth and saves redirect path', async () => {
    getSessionMock.mockResolvedValue({ data: { session: null } });
    renderHook(() => useRequireAuth());
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/auth', { replace: true });
    });
    expect(sessionStorage.getItem('auth_redirect_path')).toBe('/chat');
  });

  it('keeps authenticated users on the page (no redirect)', async () => {
    getSessionMock.mockResolvedValue({
      data: { session: { user: { id: 'u-1', email: 'a@b.com' } } },
    });
    const { result } = renderHook(() => useRequireAuth());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(navigateMock).not.toHaveBeenCalled();
    expect(result.current.user?.id).toBe('u-1');
  });

  it('redirects and signs out users with disallowed email domains', async () => {
    isEmailAllowedMock.mockReturnValue(false);
    getSessionMock.mockResolvedValue({
      data: { session: { user: { id: 'u-1', email: 'spam@unallowed.com' } } },
    });

    renderHook(() => useRequireAuth());
    await waitFor(() => {
      expect(signOutMock).toHaveBeenCalled();
      expect(navigateMock).toHaveBeenCalledWith('/auth', { replace: true });
    });
  });

  it('redirects and signs out test@example.com if not an explicit login', async () => {
    getSessionMock.mockResolvedValue({
      data: { session: { user: { id: 'u-2', email: 'test@example.com' } } },
    });
    sessionStorage.setItem('auth_explicit_login', 'false');

    renderHook(() => useRequireAuth());
    await waitFor(() => {
      expect(signOutMock).toHaveBeenCalled();
      expect(navigateMock).toHaveBeenCalledWith('/auth', { replace: true });
    });
  });

  it('allows test@example.com if auth_explicit_login is true', async () => {
    getSessionMock.mockResolvedValue({
      data: { session: { user: { id: 'u-2', email: 'test@example.com' } } },
    });
    sessionStorage.setItem('auth_explicit_login', 'true');

    const { result } = renderHook(() => useRequireAuth());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(signOutMock).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
    expect(result.current.user?.email).toBe('test@example.com');
  });

  it('prevents race condition redirects on page mount if onAuthStateChange fires early SIGNED_OUT', async () => {
    // Mock onAuthStateChange to trigger callback with SIGNED_OUT on registration
    let onAuthCallback: any;
    (onAuthStateChangeMock as any).mockImplementation((callback) => {
      onAuthCallback = callback;
      // Immediately call with no session
      callback('SIGNED_OUT', null);
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });

    // Mock getSession to resolve slightly later with a valid session
    let resolveSession: any;
    const sessionPromise = new Promise((resolve) => {
      resolveSession = resolve;
    });
    getSessionMock.mockReturnValue(sessionPromise);

    const { result } = renderHook(() => useRequireAuth());

    // Verify it is still loading and hasn't navigated yet
    expect(result.current.loading).toBe(true);
    expect(navigateMock).not.toHaveBeenCalled();

    // Resolve getSession with a valid user
    resolveSession({ data: { session: { user: { id: 'u-1', email: 'allowed@gmail.com' } } } });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(navigateMock).not.toHaveBeenCalled();
    expect(result.current.user?.email).toBe('allowed@gmail.com');
  });
});

