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

  it('reads the id from embed and shorts URLs', () => {
    const embed = { url: 'https://www.youtube.com/embed/eumRL5DfFzM', timestampSeconds: 9 };
    const shorts = { url: 'https://www.youtube.com/shorts/eumRL5DfFzM?t=9', timestampSeconds: 9 };
    expect(buildPersonalizeRef(embed)).toEqual({ video_id: 'eumRL5DfFzM', timestamp_seconds: 9 });
    expect(buildPersonalizeRef(shorts)).toEqual({ video_id: 'eumRL5DfFzM', timestamp_seconds: 9 });
  });

  it('rejects non-video youtube paths and malformed embed ids', () => {
    // /embed/ with an id that is not 11 chars never passes YOUTUBE_ID.
    expect(buildPersonalizeRef({ url: 'https://www.youtube.com/embed/short', timestampSeconds: 1 })).toBeNull();
    // Path segments that are neither embed nor shorts fall back to ?v=, which
    // these URLs do not carry — no id is inferred from arbitrary paths.
    expect(buildPersonalizeRef({ url: 'https://www.youtube.com/live/eumRL5DfFzM', timestampSeconds: 1 })).toBeNull();
    expect(buildPersonalizeRef({ url: 'https://m.youtube.com/shorts/eumRL5DfFzM', timestampSeconds: 1 })).toEqual({ video_id: 'eumRL5DfFzM', timestamp_seconds: 1 });
  });
});

describe('personalizeTeaching survives save → load (T-B14 persistence)', () => {
  it('keeps the ref through the zod MessageSchema parse on load', async () => {
    const { saveChatHistory, loadChatHistory, clearLocalChatData } = await import('@/lib/chatStorage');
    await clearLocalChatData();
    try {
      saveChatHistory([{
        id: 'm-persist-1',
        role: 'user',
        content: 'Please personalize this teaching for me.',
        timestamp: new Date(),
        personalizeTeaching: { video_id: 'eumRL5DfFzM', timestamp_seconds: 9 },
      }]);
      const [loaded] = loadChatHistory();
      // z.object strips undeclared keys by default; if MessageSchema stops
      // declaring personalizeTeaching, regenerate/edit silently resend the
      // bare prompt with no clip after a reload — this assertion locks it.
      expect(loaded?.personalizeTeaching).toEqual({ video_id: 'eumRL5DfFzM', timestamp_seconds: 9 });
    } finally {
      await clearLocalChatData();
    }
  });
});
