import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: mocks.getSession } },
}));

import { useAskData } from '@/admin/hooks/useAskData';

describe('useAskData', () => {
  beforeEach(() => {
    mocks.getSession.mockResolvedValue({ data: { session: { access_token: 'tok' } } });
    vi.stubGlobal('fetch', vi.fn());
  });

  it('starts idle with empty state', () => {
    const { result } = renderHook(() => useAskData());
    expect(result.current.loading).toBe(false);
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('sets result on successful ask', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ response: 'The p95 latency is 2.3s.' }),
    });

    const { result } = renderHook(() => useAskData());

    await act(async () => {
      await result.current.ask('What is p95?', 'ctx');
    });

    expect(result.current.result).toBe('The p95 latency is 2.3s.');
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/admin/ask'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ question: 'What is p95?', kpi_context: 'ctx' }),
      }),
    );
  });

  it('sets error on failed ask', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: false, text: async () => 'Bad request' });

    const { result } = renderHook(() => useAskData());

    await act(async () => {
      await result.current.ask('bad');
    });

    await waitFor(() => expect(result.current.error).toContain('API error'));
    expect(result.current.result).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('does nothing when question is empty', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    const { result } = renderHook(() => useAskData());
    await act(async () => {
      await result.current.ask('   ');
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
