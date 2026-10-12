import { describe, it, expect, vi, afterEach } from 'vitest';
import { buildPersonalizeRef, personalizeTeachingEnabled } from '@/lib/chat/personalize';

describe('personalize teaching helper (T-B14)', () => {
  afterEach(() => vi.unstubAllEnvs());

  it('is off unless the build flag is exactly "true"', () => {
    expect(personalizeTeachingEnabled()).toBe(false);
    vi.stubEnv('VITE_PERSONALIZE_TEACHING_ENABLED', '1');
    expect(personalizeTeachingEnabled()).toBe(false);
    vi.stubEnv('VITE_PERSONALIZE_TEACHING_ENABLED', 'true');
    expect(personalizeTeachingEnabled()).toBe(true);
  });

  it('reads the id from watch and short links', () => {
    const watch = { url: 'https://www.youtube.com/watch?v=eumRL5DfFzM&t=9s', timestampSeconds: 9 };
    const short = { url: 'https://youtu.be/eumRL5DfFzM?t=9', timestampSeconds: 9 };
    expect(buildPersonalizeRef(watch)).toEqual({ video_id: 'eumRL5DfFzM', timestamp_seconds: 9 });
    expect(buildPersonalizeRef(short)).toEqual({ video_id: 'eumRL5DfFzM', timestamp_seconds: 9 });
  });

  it('returns null without a real id, a real timestamp, or a parseable url', () => {
    expect(buildPersonalizeRef(undefined)).toBeNull();
    expect(buildPersonalizeRef({ url: 'https://youtu.be/short', timestampSeconds: 1 })).toBeNull();
    expect(buildPersonalizeRef({ url: 'https://www.youtube.com/watch?v=eumRL5DfFzM' })).toBeNull();
    expect(buildPersonalizeRef({ url: 'not a url', timestampSeconds: 1 })).toBeNull();
    expect(buildPersonalizeRef({ url: 'https://evil.example/watch?v=eumRL5DfFzM', timestampSeconds: 1 })).toBeNull();
  });
});
