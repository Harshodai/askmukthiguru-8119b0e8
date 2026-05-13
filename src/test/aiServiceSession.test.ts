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
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);

    expect(body.session_id).toBe('conversation-123');
    expect(body.messages[1].content).toContain('Prior summary');
  });
});
