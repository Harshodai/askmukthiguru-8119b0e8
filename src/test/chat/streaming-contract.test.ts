import { describe, it, expect, vi } from 'vitest';
import type { StreamChunk } from '@/lib/chat/types';

const { fetchWithRetryMock, recordMetricMock } = vi.hoisted(() => ({
  fetchWithRetryMock: vi.fn(),
  recordMetricMock: vi.fn().mockResolvedValue(undefined),
}));

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
  recordMetric: recordMetricMock,
}));

vi.mock('@/lib/chat/fetchWithRetry', () => ({
  fetchWithRetry: fetchWithRetryMock,
}));

import { sendMessageStreaming } from '@/lib/chat/streaming';

const sseResponse = (payload: string): Response => {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(payload));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { 'content-type': 'text/event-stream' },
  });
};

describe('T1-18 (UX-005): Stream contract tests', () => {
  it('throws stream_interrupted when stream terminates after final without done event', async () => {
    // Stream cut after final text before metadata/citations/safety notices arrive
    fetchWithRetryMock.mockResolvedValue(
      sseResponse('data: {"token":"verbatim quote chunk"}\n\nevent: final\ndata: "Full verbatim quote."\n\n'),
    );

    const chunks: StreamChunk[] = [];
    let thrownError: any = null;
    try {
      for await (const chunk of sendMessageStreaming([], 'tell me about suffering')) {
        chunks.push(chunk);
      }
    } catch (err) {
      thrownError = err;
    }

    expect(thrownError).not.toBeNull();
    expect(thrownError?.errorCode).toBe('stream_interrupted');
    expect(thrownError?.message).toContain('ended before completion metadata was received');
    // Verifies that while token and final were parsed, the stream did not complete cleanly
    expect(chunks.some((c) => c.type === 'final')).toBe(true);
    expect(chunks.some((c) => c.type === 'done')).toBe(false);
  });

  it('delivers done metadata before or with final event on successful completion', async () => {
    // T1-18 server contract: done event precedes final
    fetchWithRetryMock.mockResolvedValue(
      sseResponse(
        'data: {"token":"verbatim chunk"}\n\n' +
        'event: done\ndata: {"intent":"QUERY","citations":[{"id":"c1","title":"Wisdom","url":"https://youtube.com/watch?v=abc"}],"safety_notices":[]}\n\n' +
        'event: final\ndata: "Final authoritative text."\n\n' +
        'data: [DONE]\n\n'
      ),
    );

    const chunks: StreamChunk[] = [];
    for await (const chunk of sendMessageStreaming([], 'what is love?')) {
      chunks.push(chunk);
    }

    const doneIndex = chunks.findIndex((c) => c.type === 'done');
    const finalIndex = chunks.findIndex((c) => c.type === 'final');
    expect(doneIndex).toBeGreaterThanOrEqual(0);
    expect(finalIndex).toBeGreaterThanOrEqual(0);
    expect(doneIndex).toBeLessThan(finalIndex);
    expect(chunks[doneIndex]).toMatchObject({
      type: 'done',
      intent: 'QUERY',
      citations: expect.arrayContaining([expect.objectContaining({ title: 'Wisdom', url: 'https://youtube.com/watch?v=abc' })]),
    });
  });

  it('triggers inactivity timeout when stream stalls', async () => {
    // Create an indefinite stalling stream
    const body = new ReadableStream({
      start(_controller) {
        // Enqueue nothing, never close
      },
    });
    fetchWithRetryMock.mockResolvedValue(
      new Response(body, {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      }),
    );

    let thrownError: any = null;
    try {
      // Pass a very short timeout of 50ms for the test
      for await (const _chunk of sendMessageStreaming(
        [],
        'question',
        0,
        undefined,
        undefined,
        undefined,
        undefined,
        false,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        50, // 50ms timeout
      )) {
        // empty
      }
    } catch (err) {
      thrownError = err;
    }

    expect(thrownError).not.toBeNull();
    expect(thrownError?.errorCode).toBe('timeout');
    expect(thrownError?.message).toContain('Stream timed out waiting for server response');
  });
});

describe('streamed request body', () => {
  it('contains no system-role message (backend owns the system prompt)', async () => {
    fetchWithRetryMock.mockClear();
    fetchWithRetryMock.mockResolvedValue(sseResponse('data: {"token":"x"}\n\n'));
    try {
      for await (const _ of sendMessageStreaming([{ role: 'user', content: 'hi' }], 'hi')) void _;
    } catch {
      // stream-completion errors are irrelevant here; only the request body matters
    }
    const body = JSON.parse(fetchWithRetryMock.mock.calls[0][1].body as string);
    expect(body.messages.some((m: { role: string }) => m.role === 'system')).toBe(false);
    expect(JSON.stringify(body)).not.toContain('You are the guru');
  });
});
