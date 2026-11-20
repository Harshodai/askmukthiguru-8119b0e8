import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mocks = vi.hoisted(() => ({ getAccessToken: vi.fn(), refreshAccessToken: vi.fn() }));

vi.mock('@/lib/chat/auth', () => mocks);
vi.mock('@/lib/chat/anonSession', () => ({
  getAnonSessionToken: vi.fn().mockResolvedValue('anon'),
  refreshAnonSessionToken: vi.fn().mockResolvedValue(null),
}));
vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));

import { sendMessage } from '@/lib/chat/transport';
import { setAIProvider } from '@/lib/chat/config';

const fetchMock = vi.fn();

describe('transport: post-refresh retry and poll errors', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    mocks.getAccessToken.mockResolvedValue('old-token');
    mocks.refreshAccessToken.mockResolvedValue('new-token');
    setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('routes a 202 from the post-refresh retry into the job poller', async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: false, status: 401, clone: () => ({ json: async () => ({}) }) })
      .mockResolvedValueOnce({ ok: true, status: 202, json: async () => ({ job_id: 'j1', poll_url: '/api/jobs/j1' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'completed', result: { response: 'queued answer' } }) });

    const result = await sendMessage([], 'hello');

    expect(result.content).toBe('queued answer');
    expect(fetchMock.mock.calls[2][0]).toBe('http://localhost:8000/api/jobs/j1');
  });

  it.each([401, 403, 404])('stops polling early on a %i poll response', async (status) => {
    fetchMock
      .mockResolvedValueOnce({ status: 202, json: async () => ({ job_id: 'j2', poll_url: '/api/jobs/j2' }) })
      .mockResolvedValue({ ok: false, status });

    const result = await sendMessage([], 'hello');

    expect(result.error).toBeTruthy();
    expect(result.content).toBe('');
    expect(result.errorCode).not.toBe('timeout');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
