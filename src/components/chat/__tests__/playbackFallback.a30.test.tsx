/**
 * Ticket A30 — "Playback fallback: blocked YouTube embeds, slow mobile, offline
 * have no fallback" (`docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`).
 *
 * This file pins the behaviour of the two chat playback surfaces when a YouTube
 * embed fails to load. It was written first as `it.fails` markers recording a
 * KNOWN DEFECT; the defect is now fixed (`useYouTubeEmbedError` +
 * `DiscourseAudioStrip` / `DiscourseVideoModal` fallbacks, plus the `frame-src`
 * CSP entry in `nginx.conf` that had been blocking every embed), so the markers
 * are now REAL GATES: if either surface regresses to a black box that claims to
 * be playing, these tests fail.
 *
 * Surface 1 — `DiscourseAudioStrip` (the "Play source clip" strip attached under
 * every guru answer): renders `<iframe src="https://www.youtube.com/embed/...">`
 * and flips its own label to "Playing …" the instant it is clicked.
 *
 * Surface 2 — `DiscourseVideoModal` (opened from the citation badge / the strip's
 * YouTube icon): same `<iframe>` in a black `aspect-video` box.
 *
 * Both now observe the embed (YouTube `onError` postMessage + a bounded
 * no-sign-of-life timer, because a blocked frame posts nothing at all) and swap
 * the player for unchanged, already-translated recovery copy plus the external
 * "Watch on YouTube" escape hatch.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import { DiscourseAudioStrip } from '@/components/chat/DiscourseAudioStrip';
import { DiscourseVideoModal } from '@/components/chat/CitationCard';

const CITATION = {
  index: 1,
  url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  title: 'The Four Sacred Secrets — On Stillness',
  speaker: 'Sri Krishnaji',
  playbackStartSeconds: 76,
  playbackEndSeconds: 165,
  quote: 'Be still, and the truth reveals itself.',
};

/**
 * YouTube posts this exact message into the parent frame when an embed is
 * refused: `info: 101`/`150` are the "embedding disabled by request" codes that
 * `LazyYouTube` (src/components/chat/ChatMessage.tsx:642-685) already knew how
 * to detect; both playback surfaces now share that contract through
 * `useYouTubeEmbedError`.
 */
const emitYoutubeEmbedError = (code = 150) => {
  // Wrapped in act(): the surfaces react to this by re-rendering, and the
  // assertions below run synchronously.
  act(() => {
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'https://www.youtube.com',
        data: JSON.stringify({ event: 'onError', info: code }),
      }),
    );
  });
};

/** Copy already shipped in src/locales/en.json (`chat.videoUnavailable`,
 *  `chat.videoEmbedUnavailable`) — reused so the assertion describes the user
 *  outcome rather than a component-internal test id. */
const FALLBACK_COPY = /video unavailable|can't be embedded|cannot be embedded/i;

afterEach(() => cleanup());

describe('A30 playback fallback — DiscourseAudioStrip', () => {
  it('keeps the existing external YouTube escape hatch (baseline, passes today)', () => {
    render(<DiscourseAudioStrip citation={CITATION} />);

    expect(screen.getByTestId('discourse-audio-strip')).toBeInTheDocument();
    expect(screen.getByTitle('Open source video on YouTube')).toHaveAttribute(
      'href',
      CITATION.url,
    );
  });

  it(
    'shows a fallback and stops claiming "Playing" when the embed is blocked',
    () => {
      render(<DiscourseAudioStrip citation={CITATION} />);
      fireEvent.click(screen.getByTestId('discourse-audio-play-button'));

      const playButton = screen.getByTestId('discourse-audio-play-button');
      expect(playButton).toHaveTextContent(/Pause/); // optimistic, pre-load

      emitYoutubeEmbedError(150);

      // MISSING (now implemented): a user-visible recovery notice. Two lines of
      // shipped copy match the pattern ("Video unavailable" + "This video can't
      // be embedded"), so assert presence rather than a single node.
      expect(screen.getAllByText(FALLBACK_COPY).length).toBeGreaterThan(0);
      // The false playback claim must be withdrawn.
      expect(screen.queryByText(/^Playing /)).not.toBeInTheDocument();
    },
  );
});

describe('A30 playback fallback — DiscourseVideoModal', () => {
  it('shows a fallback when the modal embed is blocked', () => {
    render(<DiscourseVideoModal isOpen onClose={() => {}} citation={CITATION} />);

    emitYoutubeEmbedError(150);

    expect(screen.getAllByText(FALLBACK_COPY).length).toBeGreaterThan(0);
  });
});
