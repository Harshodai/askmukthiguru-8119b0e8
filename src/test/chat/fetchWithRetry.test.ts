import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchWithRetry,
  retryDelayMs,
  SERVER_BUSY_HELPLINE_MESSAGE,
} from '@/lib/chat/fetchWithRetry';
import { buildMessageError } from '@/lib/chat/errors';
import { INDIA_CRISIS_LINES } from '@/lib/crisisHelplines';

describe('fetchWithRetry Retry-After jitter (RP-A8)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('adds 0-1s jitter on the Retry-After header path', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    expect(retryDelayMs('5', 0)).toBe(5500);
  });

  it('spans the full jitter range on the header path', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
    expect(retryDelayMs('3', 1)).toBe(3000);
    vi.spyOn(Math, 'random').mockReturnValue(0.999);
    const delay = retryDelayMs('8', 2);
    expect(delay).toBeGreaterThanOrEqual(8000);
    expect(delay).toBeLessThan(9000);
  });

  it('keeps exponential backoff when no header is set', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
    expect(retryDelayMs(null, 0)).toBe(1000);
    expect(retryDelayMs(null, 1)).toBe(2000);
  });

  it('falls back to backoff on a malformed Retry-After (review P2-2)', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
    expect(retryDelayMs('garbage', 0)).toBe(1000);
    expect(retryDelayMs('', 1)).toBe(2000);
    expect(retryDelayMs('-5', 0)).toBe(1000);
  });

  it('honors Retry-After then returns the final 503 after exhausting attempts', async () => {
    vi.useFakeTimers();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      new Response('busy', { status: 503, headers: { 'Retry-After': '0' } }),
    );
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const pending = fetchWithRetry('http://backend.test/api/chat', { method: 'POST' }, 3);
    await vi.advanceTimersByTimeAsync(10_000);
    const res = await pending;
    expect(res.status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});

describe('final-503 helpline copy (RP-A2)', () => {
  it('derives every helpline number from the registry, never retyped', () => {
    // Owner ruling 2026-10-13 (review P3-7): shedding copy names only the
    // call-verified line + national emergency — every shown number still
    // comes from the registry, never retyped.
    expect(SERVER_BUSY_HELPLINE_MESSAGE).toContain('14416');
    expect(SERVER_BUSY_HELPLINE_MESSAGE).toContain('112');
    expect(SERVER_BUSY_HELPLINE_MESSAGE).not.toContain('Vandrevala');
    expect(SERVER_BUSY_HELPLINE_MESSAGE).not.toContain('9999');
  });

  it('maps a 503 to helpline text instead of the generic error', () => {
    const err = buildMessageError('server_error', 'Streaming failed: 503', 503);
    expect(err.description).toContain('14416');
    expect(err.title).toMatch(/busy/i);
    expect(err.retryable).toBe(true);
  });

  it('renders universal helpline on non-503 server errors (PROD-SAFE-02)', () => {
    const err = buildMessageError('server_error', 'boom', 500);
    expect(err.title).toBe('Something went wrong');
    expect(err.description).toContain('14416');
  });
});

describe('fetchWithRetry quota 429 and Retry-After cap', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('caps a header-driven delay at MAX_RETRY_AFTER_MS', async () => {
    const { MAX_RETRY_AFTER_MS } = await import('@/lib/chat/fetchWithRetry');
    vi.spyOn(Math, 'random').mockReturnValue(0.999);
    expect(retryDelayMs('3600', 0)).toBeLessThanOrEqual(MAX_RETRY_AFTER_MS);
    expect(MAX_RETRY_AFTER_MS).toBe(20_000);
  });

  it('never sleeps an hour on a Retry-After: 3600 503', async () => {
    vi.useFakeTimers();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(new Response('busy', { status: 503, headers: { 'Retry-After': '3600' } }));
    const pending = fetchWithRetry('http://x.test/api/chat', { method: 'POST' }, 2);
    await vi.advanceTimersByTimeAsync(21_000);
    expect((await pending).status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('returns a quota-exhausted 429 immediately, body still readable', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ quota_exceeded: true }), { status: 429, headers: { 'Retry-After': '3600' } }),
    );
    const res = await fetchWithRetry('http://x.test/api/chat', { method: 'POST' }, 3);
    expect(res.status).toBe(429);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(await res.json()).toEqual({ quota_exceeded: true });
  });

  it('still retries a plain 429 without quota flag', async () => {
    vi.useFakeTimers();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(new Response('{}', { status: 429, headers: { 'Retry-After': '0' } }))
      .mockResolvedValueOnce(new Response('ok', { status: 200 }));
    const pending = fetchWithRetry('http://x.test/api/chat', { method: 'POST' }, 3);
    await vi.advanceTimersByTimeAsync(2_000);
    expect((await pending).status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
