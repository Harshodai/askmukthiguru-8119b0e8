import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: mocks.getSession,
    },
  },
}));

import { sendMessage, setAIProvider } from '@/lib/aiService';

describe('aiService session continuity', () => {
  beforeEach(() => {
    mocks.getSession.mockResolvedValue({ data: { session: null } });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          response: 'A remembered answer',
          citations: [],
          meditation_step: 0,
        }),
      }),
    );
    setAIProvider({ provider: 'custom', endpoint: '/api/chat' });
  });

  it('sends the active conversation id as session_id', async () => {
    await sendMessage(
      [{ role: 'user', content: 'What is awareness?' }],
      'Continue from there',
      0,
      'Prior summary',
      'conversation-123',
    );

    const fetchMock = globalThis.fetch as unknown as {
      mock: { calls: Array<[string, RequestInit]> };
    };
    const chatCall = fetchMock.mock.calls.find(([url]) => url === '/api/chat');
    expect(chatCall).toBeDefined();
    const body = JSON.parse(chatCall![1].body as string);

    expect(body.session_id).toBe('conversation-123');
    expect(body.messages[1].content).toContain('Prior summary');
  });

  it('echoes the signed anon-session token instead of the raw id for anonymous users', async () => {
    const fetchMock = globalThis.fetch as unknown as {
      mock: { calls: Array<[string, RequestInit]> };
    };
    fetchMock.mock.calls.length = 0;
    // First call: anon-session mint returns a signed token.
    fetchMock.mockImplementationOnce(async (url: string) => {
      if (url.includes('anon-session')) {
        return {
          ok: true,
          json: async () => ({ token: 'signed.payload.signature', session_id: 'anon:payload' }),
        };
      }
      return {
        ok: true,
        json: async () => ({ response: 'A remembered answer', citations: [], meditation_step: 0 }),
      };
    });

    await sendMessage(
      [{ role: 'user', content: 'What is awareness?' }],
      'Continue from there',
      0,
      undefined,
      'conversation-123',
    );

    const chatCall = fetchMock.mock.calls.find(([url]) => url === '/api/chat');
    const body = JSON.parse(chatCall![1].body as string);
    expect(body.session_id).toBe('signed.payload.signature');
  });
});
