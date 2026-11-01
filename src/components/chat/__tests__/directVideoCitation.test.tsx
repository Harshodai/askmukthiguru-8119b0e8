import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { DiscourseVideoModal } from '@/components/chat/CitationCard';

const renderModal = (citation: Parameters<typeof DiscourseVideoModal>[0]['citation']) =>
  render(<DiscourseVideoModal isOpen onClose={() => {}} citation={citation} />);

describe('direct video citations', () => {
  it('plays an uploaded video in an HTML5 player at the exact padded clip start, with no YouTube iframe', () => {
    renderModal({
      index: 1,
      url: 'video:0123456789a',
      playbackStartSeconds: 12.35,
      playbackEndSeconds: 31.6,
      quote: 'Be here now.',
    });
    const player = document.querySelector('video[data-testid="direct-video-player"]');
    expect(player).not.toBeNull();
    const src = player!.getAttribute('src') ?? '';
    expect(src).toContain('/api/media/videos/0123456789a');
    expect(src.endsWith('#t=12.350,31.600')).toBe(true);
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('seeks to 0 when the clip starts at second 0', () => {
    renderModal({ index: 1, url: 'video:0123456789a', startTimestamp: 0 });
    const src = document.querySelector('video')!.getAttribute('src') ?? '';
    expect(src.endsWith('#t=0.000')).toBe(true);
  });

  it('recognises the media route URL', () => {
    renderModal({ index: 1, url: '/api/media/videos/0123456789a', startTimestamp: 4 });
    expect(document.querySelector('video')).not.toBeNull();
  });

  it('keeps YouTube citations on the iframe player', () => {
    renderModal({ index: 1, url: 'https://www.youtube.com/watch?v=abc12345678', startTimestamp: 9 });
    expect(document.querySelector('iframe')).not.toBeNull();
    expect(document.querySelector('video')).toBeNull();
  });
});
