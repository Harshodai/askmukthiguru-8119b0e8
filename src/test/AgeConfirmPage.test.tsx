import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const navigateMock = vi.fn();
const getSessionMock = vi.fn();
const updateUserMock = vi.fn();

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: (...args: unknown[]) => getSessionMock(...args),
      updateUser: (...args: unknown[]) => updateUserMock(...args),
    },
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _k }),
}));

import AgeConfirmPage from '@/pages/AgeConfirmPage';

const sessionWithoutAge = {
  data: { session: { user: { id: 'u-1', user_metadata: {} } } },
};

// RP-D1: post-login 18+ confirmation stores age_confirmed metadata.
describe('AgeConfirmPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    getSessionMock.mockResolvedValue(sessionWithoutAge);
    updateUserMock.mockResolvedValue({ data: {}, error: null });
  });

  it('requires the checkbox before continuing', async () => {
    render(
      <MemoryRouter>
        <AgeConfirmPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    await waitFor(() => {
      expect(screen.getByText(/confirm you are 18 years/i)).toBeInTheDocument();
    });
    expect(updateUserMock).not.toHaveBeenCalled();
  });

  it('stores age_confirmed metadata and continues to the stored path', async () => {
    sessionStorage.setItem('auth_redirect_path', '/chat');
    render(
      <MemoryRouter>
        <AgeConfirmPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    await waitFor(() => {
      expect(updateUserMock).toHaveBeenCalledWith({
        data: { age_confirmed: true, age_confirmed_at: expect.any(String) },
      });
    });
    expect(navigateMock).toHaveBeenCalledWith('/chat', { replace: true });
  });
});
