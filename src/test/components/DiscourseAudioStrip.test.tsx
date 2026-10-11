import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DiscourseAudioStrip } from '@/components/chat/DiscourseAudioStrip';

describe('DiscourseAudioStrip', () => {
  const mockCitation = {
    url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    title: 'Transform Your Life by Forgiving Yourself',
    speaker: 'Sri Preethaji',
    speakerVerified: true,
    playbackStartSeconds: 76,
    playbackEndSeconds: 165,
  };

  it('renders teacher avatar, speaker name, discourse title, and duration', () => {
    render(<DiscourseAudioStrip citation={mockCitation} />);

    expect(screen.getByTestId('discourse-audio-strip')).toBeInTheDocument();
    expect(screen.getByText('Sri Preethaji')).toBeInTheDocument();
    expect(screen.getByText('Transform Your Life by Forgiving Yourself')).toBeInTheDocument();
    expect(screen.getByText(/01:16 – 02:45/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Play source clip/i })).toBeInTheDocument();
  });

  it('never fabricates a clip range or an authenticity title when the citation has no timing or title', () => {
    render(<DiscourseAudioStrip citation={{ url: mockCitation.url }} />);

    expect(screen.queryByText(/01:16|02:45/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Authentic Discourse/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Play source clip' })).toBeInTheDocument();
    expect(screen.queryByText(/\(null\)|\(\)/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('discourse-audio-play-button'));
    const playing = screen.getByText(/^Playing /);
    expect(playing.textContent).not.toMatch(/\(|null/);
  });

  it('toggles playback state and reveals iframe on click', () => {
    render(<DiscourseAudioStrip citation={mockCitation} />);

    const playBtn = screen.getByTestId('discourse-audio-play-button');
    expect(playBtn).toHaveTextContent(/Play source clip/i);

    // Click play
    fireEvent.click(playBtn);
    expect(playBtn).toHaveTextContent(/Pause/i);
    expect(screen.getAllByTitle('Transform Your Life by Forgiving Yourself').length).toBeGreaterThanOrEqual(1);

    // Click pause
    fireEvent.click(playBtn);
    expect(playBtn).toHaveTextContent(/Play source clip/i);
  });

  it('triggers onOpenVideoModal callback when modal button clicked', () => {
    const onOpenVideoModal = vi.fn();
    render(<DiscourseAudioStrip citation={mockCitation} onOpenVideoModal={onOpenVideoModal} />);

    const videoBtn = screen.getByTitle('Watch discourse video');
    fireEvent.click(videoBtn);
    expect(onOpenVideoModal).toHaveBeenCalledTimes(1);
    expect(onOpenVideoModal).toHaveBeenCalledWith(
      expect.objectContaining({
        speaker: 'Sri Preethaji',
        playbackStartSeconds: 76,
        playbackEndSeconds: 165,
      })
    );
  });
});
