import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@/lib/chat/auth', () => ({
  getAccessToken: vi.fn().mockResolvedValue(undefined),
}));

import { queryFirstPerson, FirstPersonError } from '@/lib/firstPersonService';
import { mapFirstPersonCitationToDiscourseCitation } from '@/lib/firstPersonCitationMapper';
import type { FirstPersonCitation } from '@/lib/firstPersonService';

const baseCitation: FirstPersonCitation = {
  video_id: 'abc123',
  start_ms: 0,
  end_ms: 5000,
  timestamp_seconds: 0,
  speaker: 'Sri Krishnaji',
  teacher_id: 'krishnaji',
  transcript_hash: 'hash',
  verbatim_text: 'This is the exact teaching.',
  text_snippet: 'This is the exact teaching.',
  source_url: 'https://www.youtube.com/watch?v=abc123&t=0s',
  video_url: 'https://www.youtube.com/watch?v=abc123',
  confidence: 0.91,
  is_verbatim: true,
  provenance_kind: 'speech_turn_clip',
  caption_status: 'manual_caption',
};

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers });
}

describe('mapFirstPersonCitationToDiscourseCitation', () => {
  it('preserves a timestamp of 0 instead of dropping it', () => {
    const mapped = mapFirstPersonCitationToDiscourseCitation(baseCitation, 1);
    expect(mapped.startTimestamp).toBe(0);
  });

  it('passes the real speaker through unchanged, never hardcoded', () => {
    const mapped = mapFirstPersonCitationToDiscourseCitation(
      { ...baseCitation, speaker: 'Sri Preethaji' },
      1,
    );
    expect(mapped.speaker).toBe('Sri Preethaji');
  });

  it('carries the verbatim quote and derived end timestamp', () => {
    const mapped = mapFirstPersonCitationToDiscourseCitation(baseCitation, 2);
    expect(mapped.quote).toBe('This is the exact teaching.');
    expect(mapped.endTimestamp).toBe(5);
    expect(mapped.index).toBe(2);
  });

  it('prefers playback_url or source_url over video_url for deep linking to exact seconds', () => {
    const mapped = mapFirstPersonCitationToDiscourseCitation(baseCitation, 1);
    expect(mapped.url).toBe(baseCitation.source_url);

    const withPlayback = mapFirstPersonCitationToDiscourseCitation(
      { ...baseCitation, playback_url: 'https://www.youtube.com/watch?v=abc123&t=2s' },
      1,
    );
    expect(withPlayback.url).toBe('https://www.youtube.com/watch?v=abc123&t=2s');
  });
});

describe('queryFirstPerson', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns a parsed success response', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        answer_text: '"quote"\n— Sri Krishnaji (abc123, 0s)',
        citations: [baseCitation],
        status: 'success',
        is_direct_answer: true,
        latency_ms: 120.5,
        cached: false,
        error: null,
      }),
    );

    const result = await queryFirstPerson('What is the Beautiful State?');
    expect(result.status).toBe('success');
    expect(result.citations[0].timestamp_seconds).toBe(0);
  });

  it('throws a typed "disabled" error on 404, never swallowing it', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('', { status: 404 }));

    await expect(queryFirstPerson('q')).rejects.toMatchObject({
      code: 'disabled',
      status: 404,
    } satisfies Partial<FirstPersonError>);
  });

  it('throws a typed "rate_limited" error on 429 and surfaces Retry-After', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response('', { status: 429, headers: { 'Retry-After': '30' } }),
    );

    const err = await queryFirstPerson('q').catch((e) => e);
    expect(err).toBeInstanceOf(FirstPersonError);
    expect(err.code).toBe('rate_limited');
    expect(err.retryAfterSeconds).toBe(30);
  });

  it('throws a typed "unavailable" error on 503', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('', { status: 503 }));

    await expect(queryFirstPerson('q')).rejects.toMatchObject({ code: 'unavailable', status: 503 });
  });

  it('throws a typed "invalid_response" error on non-JSON response', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('<html>502 Bad Gateway</html>', { status: 200 }));

    await expect(queryFirstPerson('q')).rejects.toMatchObject({ code: 'invalid_response' });
  });
});
