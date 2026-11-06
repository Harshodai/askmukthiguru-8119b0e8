/**
 * NEW-A11Y-9 (A11Y-14, WCAG 2.4.3 / 3.3.1): the delete-account flow moves focus
 * to each stage's heading and reports a failed step in the page, not only in a
 * toast that disappears.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/lib/backendUrl', () => ({ BACKEND_URL: 'http://api.test' }));
vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: { access_token: 't' } } }) } },
}));

import { CancelFlow } from '@/components/profile/CancelFlow';

const fetchMock = vi.fn();
beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

const continueBtn = () => screen.getByRole('button', { name: /continue to cancellation/i });

describe('CancelFlow accessibility', () => {
  it('shows a failed step as an in-page alert tied to the flow', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 500, json: async () => ({ detail: 'Server is busy.' }) });
    render(<CancelFlow onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(continueBtn());
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Server is busy.');
  });

  it('moves focus to the new stage heading', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ next_stage: 'exit_survey' }) });
    render(<CancelFlow onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(continueBtn());
    const heading = await screen.findByRole('heading', { name: /main reason/i });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it('clears the error when the stage changes', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: 'Try again.' }) });
    render(<CancelFlow onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(continueBtn());
    await screen.findByRole('alert');
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ next_stage: 'exit_survey' }) });
    fireEvent.click(continueBtn());
    await screen.findByRole('heading', { name: /main reason/i });
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
