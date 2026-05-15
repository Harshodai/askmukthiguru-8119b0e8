import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AuthDiagnosticsPage from '@/pages/AuthDiagnosticsPage';

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: { session: { user: { id: 'u1', email: 'a@b.c' }, expires_at: 9999999999 } },
        error: null,
      }),
    },
    rpc: vi.fn().mockImplementation((name: string) => {
      if (name === 'whoami_diagnostics') {
        return Promise.resolve({
          data: { authenticated: true, profile_present: true, roles: ['user'], is_admin: false, display_name: 'Test' },
          error: null,
        });
      }
      // has_role
      return Promise.resolve({ data: false, error: null });
    }),
  },
}));

vi.mock('@/hooks/usePageMeta', () => ({ usePageMeta: () => {} }));
vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Headers({ 'content-type': 'application/json' }),
  } as Response);
});

describe('AuthDiagnosticsPage', () => {
  it('renders OK status for session, profile, roles', async () => {
    render(
      <MemoryRouter>
        <AuthDiagnosticsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('Supabase session')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Profile row exists')).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText('ok').length).toBeGreaterThan(0));
    expect(screen.getByText(/roles=\[user\]/)).toBeInTheDocument();
  });
});
