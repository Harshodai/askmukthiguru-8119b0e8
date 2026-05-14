import { describe, it, expect, beforeEach, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ getSession: vi.fn() }));
vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: mocks.getSession } },
}));

import { sendMessageStreaming, setAIProvider, type StreamChunk } from '@/lib/aiService';

/** Build a ReadableStream from a list of SSE text chunks. */
function sseStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(encoder.encode(chunks[i++]));
    },
  });
}

describe('sendMessageStreaming SSE parsing', () => {
  beforeEach(() => {
    mocks.getSession.mockResolvedValue({ data: { session: { access_token: 't' } } });
    setAIProvider({ provider: 'custom', endpoint: '/api/chat' });
  });

  it('parses status, token, and done events with citations + intent', async () => {
    const body = sseStream([
      'event: status\ndata: Searching knowledge base...\n',
      'event: message\ndata: {"token":"Hello "}\n',
      'event: message\ndata: {"token":"world"}\n',
      'event: done\ndata: {"intent":"DISTRESS","citations":["https://youtu.be/abc"],"meditation_step":1}\n',
      'data: [DONE]\n',
    ]);

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body,
    }));

    const collected: StreamChunk[] = [];
    for await (const chunk of sendMessageStreaming([], 'I feel overwhelmed', 0)) {
      collected.push(chunk);
    }

    const status = collected.find((c) => c.type === 'status');
    const tokens = collected.filter((c) => c.type === 'token');
    const done = collected.find((c) => c.type === 'done');

    expect(status).toMatchObject({ type: 'status', text: 'Searching knowledge base...' });
    expect(tokens.map((t) => (t as { text: string }).text).join('')).toBe('Hello world');
    expect(done).toBeDefined();
    expect(done).toMatchObject({
      type: 'done',
      intent: 'DISTRESS',
      meditationStep: 1,
    });
    expect((done as { citations: string[] }).citations).toEqual(['https://youtu.be/abc']);
  });

  it('unescapes \\n to real newlines in token text', async () => {
    const body = sseStream([
      'event: message\ndata: {"token":"line1\\nline2"}\n',
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body }));

    const tokens: string[] = [];
    for await (const chunk of sendMessageStreaming([], 'hi', 0)) {
      if (chunk.type === 'token') tokens.push(chunk.text);
    }
    expect(tokens.join('')).toBe('line1\nline2');
  });

  it('defaults intent to CASUAL and citations to [] when done payload is sparse', async () => {
    const body = sseStream([
      'event: done\ndata: {}\n',
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body }));

    let done: StreamChunk | undefined;
    for await (const chunk of sendMessageStreaming([], 'hi', 0)) {
      if (chunk.type === 'done') done = chunk;
    }
    expect(done).toMatchObject({ type: 'done', intent: 'CASUAL', meditationStep: 0 });
    expect((done as { citations: string[] }).citations).toEqual([]);
  });
});
