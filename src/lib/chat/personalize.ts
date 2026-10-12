/**
 * Explicit "personalize this teaching" opt-in (task T-B14).
 *
 * By default every answer is the teacher's own recorded clip. The backend runs
 * general generation only when a signed-in, non-incognito seeker asks for it
 * here AND has a personal knowledge graph; the backend is the authority on the
 * graph and on consent, so this module only builds the request.
 *
 * Build flag, default off until the backend half lands.
 */
import type { Citation } from './types';

export interface PersonalizeTeachingRef {
  video_id: string;
  timestamp_seconds: number;
}

export const personalizeTeachingEnabled = (): boolean =>
  import.meta.env.VITE_PERSONALIZE_TEACHING_ENABLED === 'true';

/** What the seeker "says" when they click the button; the backend keys on the ref, not this text. */
export const PERSONALIZE_TEACHING_PROMPT = 'Please personalize this teaching for me.';

const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;

const youtubeVideoId = (rawUrl: string): string | null => {
  try {
    const url = new URL(rawUrl);
    const host = url.hostname.replace(/^www\./, '');
    const id =
      host === 'youtu.be'
        ? url.pathname.slice(1)
        : host === 'youtube.com' || host === 'm.youtube.com'
          ? url.searchParams.get('v')
          : null;
    return id && YOUTUBE_ID.test(id) ? id : null;
  } catch {
    return null;
  }
};

/**
 * Identify the served clip by video id and start second. The backend looks the clip up
 * itself and never trusts client-sent text. Returns null when the citation has no real
 * YouTube id or no real timestamp (0 is a valid start; only absence means none).
 */
export const buildPersonalizeRef = (citation: Citation | undefined): PersonalizeTeachingRef | null => {
  if (!citation || typeof citation.timestampSeconds !== 'number') return null;
  const videoId = youtubeVideoId(citation.url);
  return videoId ? { video_id: videoId, timestamp_seconds: citation.timestampSeconds } : null;
};
