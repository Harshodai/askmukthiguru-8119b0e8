import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: mocks.getSession } },
}));

import { generateConversationTitle, submitFeedbackToBackend } from '@/lib/chat/transport';
import { setAIProvider } from '@/lib/chat/config';

describe('chat/transport helpers', () => {
  beforeEach(() => {
    mocks.getSession.mockResolvedValue({ data: { session: { access_token: 'tok' } } });
    setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
    vi.stubGlobal('fetch', vi.fn());
  });

  it('generateConversationTitle returns fallback when backend is unavailable', async () => {
    setAIProvider({ provider: 'placeholder' });
    const title = await generateConversationTitle('What is awareness?');
    expect(title).toBe('What is awareness?');
  });

  it('generateConversationTitle trims and cleans backend title', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ response: '"  Awareness and Presence  "' }),
    });

    const title = await generateConversationTitle('What is awareness?');
    expect(title).toBe('Awareness and Presence');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/chat',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('Title this conversation'),
      }),
    );
  });

  it('submitFeedbackToBackend posts to /api/feedback', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true });

    await submitFeedbackToBackend({ query: 'q', answer: 'a', rating: 1, comment: 'good' });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/feedback',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer tok' }),
        body: JSON.stringify({ query: 'q', answer: 'a', rating: 1, comment: 'good' }),
      }),
    );
  });

  it('submitFeedbackToBackend no-ops when provider is placeholder', async () => {
    setAIProvider({ provider: 'placeholder' });
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockClear();
    await submitFeedbackToBackend({ query: 'q', answer: 'a', rating: 1 });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
