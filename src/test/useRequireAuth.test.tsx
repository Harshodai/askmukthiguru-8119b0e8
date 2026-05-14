import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const navigateMock = vi.fn();
const getSessionMock = vi.fn();
const onAuthStateChangeMock = vi.fn(() => ({
  data: { subscription: { unsubscribe: vi.fn() } },
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: getSessionMock,
      onAuthStateChange: onAuthStateChangeMock,
    },
  },
}));

import { useRequireAuth } from '@/hooks/useRequireAuth';

describe('useRequireAuth', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    getSessionMock.mockReset();
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
});
