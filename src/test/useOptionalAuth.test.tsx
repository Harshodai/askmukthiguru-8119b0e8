import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const { getSessionMock, onAuthStateChangeMock, isEmailAllowedMock, getAnonSessionTokenMock } = vi.hoisted(() => ({
  getSessionMock: vi.fn(),
  onAuthStateChangeMock: vi.fn(() => ({
    data: { subscription: { unsubscribe: vi.fn() } },
  })),
  isEmailAllowedMock: vi.fn((email: string | undefined | null) => true),
  getAnonSessionTokenMock: vi.fn().mockResolvedValue('anon-token'),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: getSessionMock,
      onAuthStateChange: onAuthStateChangeMock,
    },
  },
  isEmailAllowed: (email: string | undefined | null) => isEmailAllowedMock(email),
}));

vi.mock('@/lib/chat/anonSession', () => ({
  getAnonSessionToken: getAnonSessionTokenMock,
}));

import { useOptionalAuth } from '@/hooks/useOptionalAuth';

describe('useOptionalAuth', () => {
  beforeEach(() => {
    getSessionMock.mockReset();
    onAuthStateChangeMock.mockClear();
    isEmailAllowedMock.mockReset();
    isEmailAllowedMock.mockImplementation(() => true);
    getAnonSessionTokenMock.mockReset();
    getAnonSessionTokenMock.mockResolvedValue('anon-token');
    sessionStorage.clear();
    localStorage.clear();
  });

  it('ignores a stale getSession that resolves after a newer onAuthStateChange session', async () => {
    let onAuthCallback: (event: string, session: any) => void = () => {};
    onAuthStateChangeMock.mockImplementation((callback: any) => {
      onAuthCallback = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });

    let resolveGetSession: (value: any) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveGetSession = resolve;
    });
    getSessionMock.mockReturnValue(pending);

    const { result } = renderHook(() => useOptionalAuth());
    expect(result.current.loading).toBe(true);

    const sessionB = { user: { id: 'u-b', email: 'allowed@gmail.com' } };
    await act(async () => {
      await onAuthCallback('SIGNED_IN', sessionB);
    });
    await waitFor(() => expect(result.current.user?.id).toBe('u-b'));

    const sessionA = { user: { id: 'u-a', email: 'other@gmail.com' } };
    await act(async () => {
      resolveGetSession({ data: { session: sessionA } });
      await Promise.resolve();
    });

    expect(result.current.user?.id).toBe('u-b');
    expect(result.current.mode).toBe('authenticated');
  });

  it('does not write state when unmounted while getSession is pending', async () => {
    let resolveGetSession: (value: any) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveGetSession = resolve;
    });
    getSessionMock.mockReturnValue(pending);

    const { unmount } = renderHook(() => useOptionalAuth());
    unmount();

    await act(async () => {
      resolveGetSession({
        data: { session: null },
      });
      await Promise.resolve();
    });

    expect(getAnonSessionTokenMock).not.toHaveBeenCalled();
  });

  it('falls back to an anonymous token for disallowed sessions', async () => {
    isEmailAllowedMock.mockReturnValue(false);
    getSessionMock.mockResolvedValue({
      data: { session: { user: { id: 'u-1', email: 'spam@unallowed.com' } } },
    });

    const { result } = renderHook(() => useOptionalAuth());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.mode).toBe('anonymous');
    expect(result.current.user).toBeNull();
    expect(result.current.anonToken).toBe('anon-token');
    expect(getAnonSessionTokenMock).toHaveBeenCalled();
  });
});
