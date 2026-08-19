import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: mocks.getSession } },
}));

vi.mock('@/lib/chat/anonSession', () => ({
  getAnonSessionToken: vi.fn().mockResolvedValue('signed-anon-token'),
}));

import { generateConversationTitle, submitFeedbackToBackend, sendMessage, uploadChatAttachment } from '@/lib/chat/transport';
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
      json: async () => ({ title: '"  Awareness and Presence  "' }),
    });

    const title = await generateConversationTitle('What is awareness?');
    expect(title).toBe('Awareness and Presence');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/chat/title',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('first_message'),
      }),
    );
  });

  it('submitFeedbackToBackend posts to /api/feedback', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true });

    await submitFeedbackToBackend({ query: 'q', answer: 'a', rating: 1, feedback_text: 'good' });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/feedback',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer tok' }),
        body: JSON.stringify({ query: 'q', answer: 'a', rating: 1, feedback_text: 'good', metadata_json: undefined }),
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

  it('uploadChatAttachment sends a signed anonymous session token in multipart form data', async () => {
    mocks.getSession.mockResolvedValue({ data: { session: null } });
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ attachment_context: 'bounded', attachments: [], ephemeral: true, retention_seconds: 900 }),
    });

    await uploadChatAttachment(new File(['hello'], 'notes.txt', { type: 'text/plain' }), 'en');

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/chat/upload');
    expect(options.method).toBe('POST');
    expect((options.body as FormData).get('session_id')).toBe('signed-anon-token');
    expect((options.body as FormData).get('language_code')).toBe('en');
    expect((options.body as FormData).get('files')).toBeInstanceOf(File);
  });

  it('sendMessage preserves backend verification and provenance metadata', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        response: 'grounded answer',
        citations: ['https://example.com/teaching'],
        citations_verified: true,
        orphan_citations_stripped: false,
        faithfulness_score: 0.91,
        relevancy_score: 0.88,
        provenance_manifest: { manifest_id: 'manifest-1' },
        release_manifest: { release_id: 'release-1' },
        trace_id: 'trace-1',
        query_tier: 'tier2_simple',
      }),
    });

    const result = await sendMessage([], 'hello');

    expect(result).toMatchObject({
      content: 'grounded answer',
      citationsVerified: true,
      orphanCitationsStripped: false,
      faithfulnessScore: 0.91,
      relevancyScore: 0.88,
      provenanceManifest: { manifest_id: 'manifest-1' },
      releaseManifest: { release_id: 'release-1' },
      traceId: 'trace-1',
      queryTier: 'tier2_simple',
    });
  });

  it('sendMessage resolves a host-relative queue poll_url against the backend origin', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce({
        status: 202,
        json: async () => ({ job_id: 'job_1', poll_url: '/api/jobs/job_1' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'completed', result: { response: 'namaste' } }),
      });

    await sendMessage([], 'hello');

    // Second call is the poll — must hit the backend origin, not a bare relative path.
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://localhost:8000/api/jobs/job_1',
      expect.anything(),
    );
  });
});

describe('incognito request propagation', () => {
  it('sends explicit incognito mode on non-streaming chat requests', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockClear();
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ response: 'namaste' }),
    });

    await sendMessage([], 'private question', 0, undefined, undefined, undefined, undefined, true);

    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body).incognito).toBe(true);
  });
});
