import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  getAccessToken: vi.fn(),
  refreshAccessToken: vi.fn(),
  getAnonSessionToken: vi.fn(),
  refreshAnonSessionToken: vi.fn(),
}));

vi.mock('@/lib/chat/auth', () => ({
  getAccessToken: mocks.getAccessToken,
  refreshAccessToken: mocks.refreshAccessToken,
}));
vi.mock('@/lib/chat/anonSession', () => ({
  getAnonSessionToken: mocks.getAnonSessionToken,
  refreshAnonSessionToken: mocks.refreshAnonSessionToken,
}));
vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));

import { sendMessage } from '@/lib/chat/transport';
import { sendMessageStreaming } from '@/lib/chat/streaming';
import { setAIProvider } from '@/lib/chat/config';

const badToken = () =>
  new Response(JSON.stringify({ detail: 'Invalid anonymous session token' }), {
    status: 400,
    headers: { 'Content-Type': 'application/json' },
  });
const sentSession = (call: unknown[]) =>
  JSON.parse(((call[1] as RequestInit).body as string)).session_id;

const fetchMock = vi.fn();

describe('rotated anon HMAC secret: 400 "Invalid anonymous session token"', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    mocks.getAccessToken.mockResolvedValue(null);
    mocks.getAnonSessionToken.mockResolvedValue('old.sig');
    mocks.refreshAnonSessionToken.mockReset().mockResolvedValue('new.sig');
    setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('sendMessage re-mints once and retries with the new token', async () => {
    fetchMock
      .mockResolvedValueOnce(badToken())
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ response: 'ok' }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );

    const result = await sendMessage([], 'hello');

    expect(mocks.refreshAnonSessionToken).toHaveBeenCalledTimes(1);
    expect(sentSession(fetchMock.mock.calls[0])).toBe('old.sig');
    expect(sentSession(fetchMock.mock.calls[1])).toBe('new.sig');
    expect(result.error).toBeUndefined();
  });

  it('sendMessage does not refresh on an unrelated 400', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'something else' }), { status: 400, headers: { 'Content-Type': 'application/json' } }),
    );
    await sendMessage([], 'hello');
    expect(mocks.refreshAnonSessionToken).not.toHaveBeenCalled();
  });

  it('sendMessageStreaming re-mints once and retries with the new token', async () => {
    fetchMock
      .mockResolvedValueOnce(badToken())
      .mockResolvedValueOnce(new Response('nope', { status: 500 }));

    await expect(async () => {
      for await (const _ of sendMessageStreaming([], 'hello')) void _;
    }).rejects.toBeTruthy();

    expect(mocks.refreshAnonSessionToken).toHaveBeenCalledTimes(1);
    expect(sentSession(fetchMock.mock.calls[0])).toBe('old.sig');
    expect(sentSession(fetchMock.mock.calls[1])).toBe('new.sig');
  });
});
