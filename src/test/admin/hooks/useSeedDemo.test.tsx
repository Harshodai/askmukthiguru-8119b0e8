import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  rpc: vi.fn(),
  invalidateQueries: vi.fn(),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { rpc: mocks.rpc },
}));

import { useSeedDemo } from '@/admin/hooks/useSeedDemo';

describe('useSeedDemo', () => {
  beforeEach(() => {
    mocks.rpc.mockReset();
    mocks.invalidateQueries.mockReset();
  });

  it('seeds demo data and invalidates admin queries', async () => {
    mocks.rpc.mockResolvedValue({ data: { ok: true }, error: null });

    const { result } = renderHook(() => useSeedDemo());
    expect(result.current.loading).toBe(false);

    await act(async () => {
      await result.current.seed();
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mocks.rpc).toHaveBeenCalledWith('seed_admin_demo');
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['admin'] });
  });

  it('surfaces backend rejection reason', async () => {
    const { toast } = await import('sonner');
    mocks.rpc.mockResolvedValue({ data: { ok: false, reason: 'quota exceeded' }, error: null });

    const { result } = renderHook(() => useSeedDemo());
    await act(async () => {
      await result.current.seed();
    });

    expect(toast.error).toHaveBeenCalledWith('Seed failed: quota exceeded');
  });

  it('surfaces network/rpc errors', async () => {
    const { toast } = await import('sonner');
    mocks.rpc.mockResolvedValue({ data: null, error: new Error('network down') });

    const { result } = renderHook(() => useSeedDemo());
    await act(async () => {
      await result.current.seed();
    });

    expect(toast.error).toHaveBeenCalledWith('Seed failed: network down');
  });
});
