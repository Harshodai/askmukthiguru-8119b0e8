/**
 * streaming.test.ts
 * Unit tests for FluidTokenPacer and ResilientStreamTransport.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { FluidTokenPacer } from '../lib/streaming/FluidTokenPacer';
import { ResilientStreamTransport } from '../lib/streaming/ResilientStreamTransport';

describe('FluidTokenPacer', () => {
  it('paces characters smoothly and invokes onEmit', async () => {
    let output = '';
    const pacer = new FluidTokenPacer({
      targetCharsPerSec: 100, // fast for testing
      onEmit: (char) => {
        output += char;
      },
    });

    pacer.push('Om Shanti');
    expect(pacer.getQueueLength()).toBe(9);

    pacer.flush();
    expect(output).toBe('Om Shanti');
    expect(pacer.getQueueLength()).toBe(0);
  });

  it('handles punctuation pauses and completion callback', async () => {
    let completed = false;
    let output = '';
    const pacer = new FluidTokenPacer({
      targetCharsPerSec: 200,
      onEmit: (char) => {
        output += char;
      },
      onComplete: () => {
        completed = true;
      },
    });

    pacer.push('Hello.');
    pacer.flush();
    expect(output).toBe('Hello.');
    expect(completed).toBe(true);
  });
});

describe('ResilientStreamTransport', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('connects and parses SSE streams correctly with Last-Event-ID', async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('id: 1\nevent: message\ndata: Hello Mukthi\n\n'));
        controller.close();
      },
    });

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      body: stream,
    } as any);

    const messages: any[] = [];
    const transport = new ResilientStreamTransport({
      url: 'http://localhost/stream',
      onMessage: (msg) => {
        messages.push(msg);
      },
    });

    await transport.connect();
    expect(messages.length).toBe(1);
    expect(messages[0].data).toBe('Hello Mukthi');
    expect(transport.getLastEventId()).toBe('1');
    transport.disconnect();
  });
});
