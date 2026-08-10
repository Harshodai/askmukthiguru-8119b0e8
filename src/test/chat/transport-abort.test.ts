import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: mocks.getSession } },
}));

import { generateConversationTitle, submitFeedbackToBackend, translateText } from '@/lib/chat/transport';
import { setAIProvider } from '@/lib/chat/config';

describe('chat/transport abort support (P1-AI-18)', () => {
  beforeEach(() => {
    mocks.getSession.mockResolvedValue({ data: { session: { access_token: 'tok' } } });
    setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
    vi.stubGlobal('fetch', vi.fn());
  });

  it('generateConversationTitle rejects with AbortError when caller signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation((_url: unknown, opts?: { signal?: AbortSignal }) => {
      if (opts?.signal?.aborted) {
        return Promise.reject(new DOMException('The operation was aborted', 'AbortError'));
      }
      return Promise.resolve({ ok: true, json: async () => ({ title: 'Awareness' }) });
    });

    await expect(generateConversationTitle('What is awareness?', { signal: controller.signal }))
      .rejects.toThrow(/aborted/i);
  });

  it('generateConversationTitle threads the caller signal into fetch', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ title: 'Awareness' }),
    });
    const controller = new AbortController();

    await generateConversationTitle('What is awareness?', { signal: controller.signal });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/chat/title',
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it('submitFeedbackToBackend rejects with AbortError when caller signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation((_url: unknown, opts?: { signal?: AbortSignal }) => {
      if (opts?.signal?.aborted) {
        return Promise.reject(new DOMException('The operation was aborted', 'AbortError'));
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await expect(
      submitFeedbackToBackend({ query: 'q', answer: 'a', rating: 1 }, { signal: controller.signal }),
    ).rejects.toThrow(/aborted/i);
  });

  it('translateText rejects with AbortError when caller signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation((_url: unknown, opts?: { signal?: AbortSignal }) => {
      if (opts?.signal?.aborted) {
        return Promise.reject(new DOMException('The operation was aborted', 'AbortError'));
      }
      return Promise.resolve({ ok: true, json: async () => ({ translated_text: 'नमस्ते' }) });
    });

    await expect(
      translateText('hello', 'hi', 'en-IN', { signal: controller.signal }),
    ).rejects.toThrow(/aborted/i);
  });

  it('existing callers without a signal still work (backward compatible)', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ title: 'Awareness' }),
    });

    const title = await generateConversationTitle('What is awareness?');
    expect(title).toBe('Awareness');
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/title'),
      expect.objectContaining({ signal: undefined }),
    );
  });
});
