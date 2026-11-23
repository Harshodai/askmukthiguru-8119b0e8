import { act, renderHook, waitFor } from '@testing-library/react';
import type { Session } from '@supabase/supabase-js';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWhatsAppConnection } from '@/hooks/useWhatsAppConnection';

const mocks = vi.hoisted(() => ({ getSession: vi.fn(), onAuthStateChange: vi.fn() }));
vi.mock('@/integrations/supabase/client', () => ({ supabase: { auth: mocks } }));
vi.mock('@/lib/backendUrl', () => ({ BACKEND_URL: 'https://backend.test' }));

const session = (id: string) => ({ access_token: `test-${id}`, user: { id } }) as Session;
const linked = (phone = '+91 *** 123') => ({ linked: true, masked_phone: phone, sync_history_consent: false, memory_write_consent: false });
const response = (data: unknown) => ({ ok: true, json: async () => data });

describe('WhatsApp account-scoped confirmations', () => {
  let authChanged: (event: string, next: Session | null) => void;
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mocks.getSession.mockResolvedValue({ data: { session: session('A') } });
    mocks.onAuthStateChange.mockImplementation(callback => {
      authChanged = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(linked())));
  });

  it('keeps memory disabled when server does not confirm consent', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(response(linked()) as Response).mockResolvedValueOnce(response({ success: true }) as Response);
    const { result } = renderHook(() => useWhatsAppConnection());
    await waitFor(() => expect(result.current.status?.linked).toBe(true));
    await act(async () => { expect(await result.current.updateConsent('memory_write_consent', true)).toBe(false); });
    expect(result.current.status?.memory_write_consent).toBe(false);
    expect(result.current.error).not.toBeNull();
  });

  it('keeps account linked when unlink is not confirmed', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(linked()) as Response).mockResolvedValueOnce(response({ success: false }) as Response);
    const { result } = renderHook(() => useWhatsAppConnection());
    await waitFor(() => expect(result.current.status?.linked).toBe(true));
    await act(async () => { expect(await result.current.unlink()).toBe(false); });
    expect(result.current.status?.linked).toBe(true);
  });

  it('ignores a previous account status arriving after account switch', async () => {
    let finishA: (value: Response) => void = () => {};
    vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finishA = resolve; }))
      .mockResolvedValueOnce(response(linked('+91 *** 456')) as Response);
    const { result } = renderHook(() => useWhatsAppConnection());
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    act(() => authChanged('SIGNED_IN', session('B')));
    await waitFor(() => expect(result.current.status?.masked_phone).toBe('+91 *** 456'));
    await act(async () => finishA(response(linked('+91 *** 123')) as Response));
    expect(result.current.status?.masked_phone).toBe('+91 *** 456');
  });

  it('does not restore an account after sign-out during linking', async () => {
    let finish: (value: Response) => void = () => {};
    vi.mocked(fetch).mockResolvedValueOnce(response({ linked: false }) as Response)
      .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const { result } = renderHook(() => useWhatsAppConnection());
    await waitFor(() => expect(result.current.status?.linked).toBe(false));
    let verified: Promise<boolean> = Promise.resolve(false);
    act(() => { verified = result.current.verify('private_challenge_123456789', false, false); });
    act(() => authChanged('SIGNED_OUT', null));
    await act(async () => { finish(response({ success: true, ...linked() }) as Response); expect(await verified).toBe(false); });
    expect(result.current.session).toBeNull();
    expect(result.current.status).toBeNull();
  });

  it('submits one change even when invoked twice before rerender', async () => {
    const { result } = renderHook(() => useWhatsAppConnection());
    await waitFor(() => expect(result.current.status?.linked).toBe(true));
    vi.mocked(fetch).mockResolvedValueOnce(response({ memory_write_consent: true }) as Response);
    await act(async () => {
      const first = result.current.updateConsent('memory_write_consent', true);
      const second = result.current.updateConsent('memory_write_consent', true);
      expect(await first).toBe(true);
      expect(await second).toBe(false);
    });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(result.current.status?.memory_write_consent).toBe(true);
  });
});