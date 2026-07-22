import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: mocks.getSession } },
}));

import {
  sendMessage,
  checkConnection,
  checkBackendHealth,
  getHealthStatus,
  resetHealthCache,
  generateConversationTitle,
  submitFeedbackToBackend,
  setAIProvider,
} from '@/lib/aiService';

describe('aiService regression — health and fallback paths', () => {
  beforeEach(() => {
    mocks.getSession.mockResolvedValue({ data: { session: null } });
    resetHealthCache();
    if (typeof AbortSignal.timeout !== 'function') {
      Object.defineProperty(AbortSignal, 'timeout', {
        value: (ms: number) => new AbortController().signal,
        configurable: true,
      });
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ response: 'Mocked response', citations: [], meditation_step: 0 }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('checkConnection', () => {
    it('placeholder provider reports offline mode without network calls', async () => {
      setAIProvider({ provider: 'placeholder' });
      const result = await checkConnection();
      expect(result).toEqual({ connected: true, mode: 'Offline Mode' });
    });


    it('reports connected when /api/health returns OK', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockResolvedValue({ ok: true });

      const result = await checkConnection();
      expect(result).toEqual({ connected: true, mode: 'Connected to Guru' });
    });

    it('reports reconnecting when /api/health fails', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockResolvedValue({ ok: false });

      const result = await checkConnection();
      expect(result).toEqual({ connected: false, mode: 'Reconnecting…' });
    });

    it('reports reconnecting when /api/health throws', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockRejectedValue(new Error('fetch failed'));

      const result = await checkConnection();
      expect(result).toEqual({ connected: false, mode: 'Reconnecting…' });
    });
  });

  describe('checkBackendHealth', () => {
    it('returns up when /api/health responds OK', async () => {
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockResolvedValue({ ok: true });

      const status = await checkBackendHealth('http://localhost:8000/api/chat');
      expect(status).toBe('up');
      expect(getHealthStatus()).toBe('up');
    });

    it('returns down when /api/health responds non-OK', async () => {
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockResolvedValue({ ok: false });

      const status = await checkBackendHealth('http://localhost:8000/api/chat');
      expect(status).toBe('down');
      expect(getHealthStatus()).toBe('down');
    });

    it('returns down when /api/health throws', async () => {
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockRejectedValue(new Error('network failure'));

      const status = await checkBackendHealth('http://localhost:8000/api/chat');
      expect(status).toBe('down');
      expect(getHealthStatus()).toBe('down');
    });

    it('caches health status for 30 seconds', async () => {
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockResolvedValue({ ok: true });

      await checkBackendHealth('http://localhost:8000/api/chat');
      await checkBackendHealth('http://localhost:8000/api/chat');
      await checkBackendHealth('http://localhost:8000/api/chat');

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  describe('sendMessage fallback paths', () => {
    it('returns placeholder response when provider is placeholder', async () => {
      setAIProvider({ provider: 'placeholder' });
      const result = await sendMessage([], 'Hello', 0);

      expect(result.content).toBeTruthy();
      expect(result.error).toBeUndefined();
    });

    it('returns parsed response for successful custom provider call', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      const result = await sendMessage([], 'Hello', 0);

      expect(result.content).toBe('Mocked response');
    });

    it('returns timeout error when backend responds 504', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockResolvedValue({
        ok: false,
        status: 504,
        json: async () => ({}),
      });

      const result = await sendMessage([], 'Hello', 0);
      expect(result.errorCode).toBe('timeout');
      expect(result.error).toContain('took too long');
    });

    it('returns network error with backend-unavailable message when fetch throws TypeError', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;

      // Prime the health cache as down so the user-facing message is explicit.
      fetchMock.mockRejectedValue(new Error('health check failed'));
      await checkBackendHealth('http://localhost:8000/api/chat');
      expect(getHealthStatus()).toBe('down');

      fetchMock.mockRejectedValue(new TypeError('fetch failed'));
      const result = await sendMessage([], 'Hello', 0);
      expect(result.errorCode).toBe('network');
      expect(result.error).toContain('Cannot reach the Guru');
    });

    it('returns timeout error when AbortError is raised', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      const abortError = new Error('Aborted');
      abortError.name = 'AbortError';
      fetchMock.mockRejectedValue(abortError);

      const result = await sendMessage([], 'Hello', 0);
      expect(result.errorCode).toBe('timeout');
      expect(result.error).toContain('timed out');
    });

    it('queues 202 response into polling until completed', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock
        .mockResolvedValueOnce({
          status: 202,
          ok: false,
          json: async () => ({ job_id: 'job-1', poll_url: 'http://localhost:8000/api/jobs/job-1' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'pending' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            status: 'completed',
            result: { response: 'Queued result', citations: ['https://youtu.be/abc'], meditation_step: 2 },
          }),
        });

      const result = await sendMessage([], 'Hello', 0);
      expect(result.content).toBe('Queued result');
      expect(result.citations).toEqual(['https://youtu.be/abc']);
      expect(result.meditationStep).toBe(2);
    });

    it('returns timeout error when queue job never completes', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockResolvedValue({
        status: 202,
        ok: false,
        json: async () => ({ job_id: 'job-2', poll_url: 'http://localhost:8000/api/jobs/job-2' }),
      });

      vi.useFakeTimers({ shouldAdvanceTime: true });
      const promise = sendMessage([], 'Hello', 0);
      await vi.advanceTimersByTimeAsync(130_000);
      const result = await promise;

      expect(result.errorCode).toBe('timeout');
      vi.useRealTimers();
    });
  });

  describe('transport helper fallback paths', () => {
    it('generateConversationTitle returns fallback slice for placeholder provider', async () => {
      setAIProvider({ provider: 'placeholder' });
      const title = await generateConversationTitle('What is the beautiful state?');
      expect(title).toBe('What is the beautiful state?');
    });

    it('submitFeedbackToBackend no-ops when provider is placeholder', async () => {
      setAIProvider({ provider: 'placeholder' });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockClear();

      await submitFeedbackToBackend({ query: 'q', answer: 'a', rating: 1 });
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('submitFeedbackToBackend posts to /api/feedback for custom provider', async () => {
      setAIProvider({ provider: 'custom', endpoint: 'http://localhost:8000/api/chat' });
      mocks.getSession.mockResolvedValue({
        data: { session: { access_token: 'token-1' } },
      });
      const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockResolvedValue({ ok: true });

      await submitFeedbackToBackend({ query: 'q', answer: 'a', rating: 1, comment: 'good' });

      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/api/feedback',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
          body: JSON.stringify({ query: 'q', answer: 'a', rating: 1, comment: 'good' }),
        }),
      );
    });
  });
});
