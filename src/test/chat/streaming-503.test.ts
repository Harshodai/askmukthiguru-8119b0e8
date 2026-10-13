import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@/lib/chat/config', () => ({
  getCurrentConfig: vi.fn(() => ({
    provider: 'custom',
    endpoint: 'http://backend.test/api/chat',
    systemPrompt: 'You are the guru',
    language: 'en',
  })),
}));

vi.mock('@/lib/chat/auth', () => ({
  getAccessToken: vi.fn().mockResolvedValue('tok'),
  refreshAccessToken: vi.fn().mockResolvedValue(null),
}));

vi.mock('@/lib/chat/assistant', () => ({
  buildAssistantContext: vi.fn(() => ({})),
}));

vi.mock('@/lib/chat/telemetry', () => ({
  recordMetric: vi.fn().mockResolvedValue(undefined),
}));

import { sendMessageStreaming } from '@/lib/chat/streaming';

const busyResponse = () =>
  ({
    ok: false,
    status: 503,
    headers: { get: (name: string) => (name === 'Retry-After' ? '0' : null) },
    clone: () => ({ json: async () => ({ detail: 'Server busy, try again shortly' }) }),
  }) as unknown as Response;

describe('sendMessageStreaming final-503 (RP-A2)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.spyOn(Math, 'random').mockReturnValue(0);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('throws helpline text, not a generic error, when the server keeps shedding', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(busyResponse());
    const stream = sendMessageStreaming([], 'hello');
    let thrown: unknown;
    try {
      await stream.next();
    } catch (err) {
      thrown = err;
    }
    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as Error).message).toContain('14416');
    expect((thrown as Error & { status?: number }).status).toBe(503);
  });
});
