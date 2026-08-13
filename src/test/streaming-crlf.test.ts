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

import { splitSseLines, sendMessageStreaming } from '@/lib/chat/streaming';

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

describe('splitSseLines (CRLF handling)', () => {
  it('splits CRLF payloads without stray carriage returns', () => {
    const { lines, remainder } = splitSseLines('data: {"token":"x"}\r\n');
    expect(lines).toEqual(['data: {"token":"x"}']);
    expect(remainder).toBe('');
    expect(lines[0].includes('\r')).toBe(false);
  });

  it('splits CRLF event lines', () => {
    const { lines } = splitSseLines('event: status\r\n');
    expect(lines).toEqual(['event: status']);
    expect(lines[0].includes('\r')).toBe(false);
  });

  it('handles mixed LF/CRLF line endings', () => {
    const { lines, remainder } = splitSseLines('a\r\nb\nc');
    expect(lines).toEqual(['a', 'b']);
    expect(remainder).toBe('c');
  });

  it('keeps a partial final line in the remainder', () => {
    const { lines, remainder } = splitSseLines('data: {"token":"pa');
    expect(lines).toEqual([]);
    expect(remainder).toBe('data: {"token":"pa');
  });
});

describe('sendMessageStreaming with CRLF SSE payload', () => {
  it('parses CRLF token payloads end-to-end without stray \\r', async () => {
    fetchWithRetryMock.mockResolvedValue(
      sseResponse('data: {"token":"x"}\r\nevent: status\r\ndata: {"step":1}\r\n\r\ndata: [DONE]\r\n'),
    );

    const chunks: StreamChunk[] = [];
    for await (const chunk of sendMessageStreaming([], 'hello')) {
      chunks.push(chunk);
    }

    // Exact payload match — a stray \r would leak into text and fail toEqual.
    expect(chunks).toEqual([
      { type: 'token', text: 'x' },
      { type: 'status', text: '{"step":1}' },
    ]);
    expect(chunks[0].type).toBe('token');
  });

  it('matches CRLF event lines to the current SSE event type', async () => {
    fetchWithRetryMock.mockResolvedValue(
      sseResponse('event: status\r\ndata: {"step":1}\r\n\r\ndata: [DONE]\r\n'),
    );

    const chunks: StreamChunk[] = [];
    for await (const chunk of sendMessageStreaming([], 'hello')) {
      chunks.push(chunk);
    }

    expect(chunks).toEqual([{ type: 'status', text: '{"step":1}' }]);
    expect(recordMetricMock).toHaveBeenCalled();
  });
});

describe('incognito stream request propagation', () => {
  it('sends explicit incognito mode to the streaming endpoint', async () => {
    fetchWithRetryMock.mockClear();
    fetchWithRetryMock.mockResolvedValue(sseResponse('data: [DONE]\n\n'));

    for await (const _chunk of sendMessageStreaming([], 'private question', 0, undefined, undefined, undefined, undefined, true)) {
      // Completion payload is intentionally empty; this assertion targets the request contract.
    }

    const [, options] = fetchWithRetryMock.mock.calls[0];
    expect(JSON.parse(options.body).incognito).toBe(true);
  });
});
