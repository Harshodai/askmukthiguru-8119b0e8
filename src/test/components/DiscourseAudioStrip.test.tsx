import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DiscourseAudioStrip } from '@/components/chat/DiscourseAudioStrip';

describe('DiscourseAudioStrip', () => {
  const mockCitation = {
    url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    title: 'Transform Your Life by Forgiving Yourself',
    speaker: 'Sri Preethaji',
    playbackStartSeconds: 76,
    playbackEndSeconds: 165,
  };

  it('renders teacher avatar, speaker name, discourse title, and duration', () => {
    render(<DiscourseAudioStrip citation={mockCitation} />);

    expect(screen.getByTestId('discourse-audio-strip')).toBeInTheDocument();
    expect(screen.getByText('Sri Preethaji')).toBeInTheDocument();
    expect(screen.getByText('Transform Your Life by Forgiving Yourself')).toBeInTheDocument();
    expect(screen.getByText(/01:16 – 02:45/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Listen in Guru's Voice/i })).toBeInTheDocument();
  });

  it('toggles playback state and reveals iframe on click', () => {
    render(<DiscourseAudioStrip citation={mockCitation} />);

    const playBtn = screen.getByTestId('discourse-audio-play-button');
    expect(playBtn).toHaveTextContent(/Listen in Guru's Voice/i);

    // Click play
    fireEvent.click(playBtn);
    expect(playBtn).toHaveTextContent(/Pause/i);
    expect(screen.getAllByTitle('Transform Your Life by Forgiving Yourself').length).toBeGreaterThanOrEqual(1);

    // Click pause
    fireEvent.click(playBtn);
    expect(playBtn).toHaveTextContent(/Listen in Guru's Voice/i);
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
