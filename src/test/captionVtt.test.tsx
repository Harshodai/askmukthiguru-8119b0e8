/**
 * NEW-A11Y-4 (A11Y-06): captions for clip video come from the stored verbatim
 * text only. YouTube embeds ask for YouTube's own captions (cc_load_policy=1).
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { buildCaptionVtt } from '@/lib/captionVtt';
import { DiscourseVideoModal } from '@/components/chat/CitationCard';

afterEach(() => cleanup());

describe('buildCaptionVtt', () => {
  it('writes one cue whose text equals the quote', () => {
    const vtt = buildCaptionVtt('Be still, and the truth reveals itself.', 76, 165.5)!;
    expect(vtt.startsWith('WEBVTT\n\n')).toBe(true);
    expect(vtt).toContain('00:01:16.000 --> 00:02:45.500\nBe still, and the truth reveals itself.\n');
  });
  it('escapes markup and never lets a blank line end the cue', () => {
    const vtt = buildCaptionVtt('a < b & c\n\n\nsecond line', 0, 5)!;
    expect(vtt).toContain('a &lt; b &amp; c\nsecond line\n');
    expect(vtt.split('\n\n')).toHaveLength(2); // header block + one cue block
  });
  it('returns null for empty text or an empty time range', () => {
    expect(buildCaptionVtt('   ', 0, 5)).toBeNull();
    expect(buildCaptionVtt('x', 5, 5)).toBeNull();
  });
});

const base = {
  index: 1,
  title: 'Clip',
  speaker: 'Sri Krishnaji',
  playbackStartSeconds: 76,
  playbackEndSeconds: 165,
  quote: 'Be still, and the truth reveals itself.',
};

describe('clip dialog captions', () => {
  it('direct video has a captions track with a cue for the quote', async () => {
    let blobText = '';
    const realCreate = URL.createObjectURL;
    URL.createObjectURL = ((b: Blob) => {
      const reader = new FileReader();
      reader.onload = () => (blobText = String(reader.result));
      reader.readAsText(b);
      return 'blob:test-captions';
    }) as typeof URL.createObjectURL;
    try {
      render(
        <DiscourseVideoModal
          citation={{ ...base, url: '/api/media/videos/abc123' } as never}
          isOpen
          onClose={() => undefined}
        />,
      );
      const video = document.querySelector('video[data-testid="direct-video-player"]')!;
      const track = video.querySelector('track[kind="captions"]');
      expect(track).not.toBeNull();
      expect(track).toHaveAttribute('src', 'blob:test-captions');
      await new Promise((r) => setTimeout(r, 20));
      expect(blobText).toContain(base.quote);
    } finally {
      URL.createObjectURL = realCreate;
    }
  });

  it('YouTube embed asks for captions', () => {
    render(
      <DiscourseVideoModal
        citation={{ ...base, url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' } as never}
        isOpen
        onClose={() => undefined}
      />,
    );
    const frame = document.querySelector('iframe')!;
    expect(frame.getAttribute('src')).toContain('cc_load_policy=1');
  });
});
