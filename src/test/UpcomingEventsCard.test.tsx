import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UpcomingEventsCard } from '@/components/ritual/UpcomingEventsCard';

const mocks = vi.hoisted(() => ({ state: { events: [] as unknown[], loading: false } }));

vi.mock('@/hooks/useUpcomingEvents', () => ({
  useUpcomingEvents: () => mocks.state,
}));

describe('UpcomingEventsCard', () => {
  it('renders nothing when there are no events (never a placeholder)', () => {
    mocks.state = { events: [], loading: false };
    const { container } = render(<UpcomingEventsCard />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders each published event with its details and an external link', () => {
    mocks.state = {
      loading: false,
      events: [
        {
          id: '1',
          title: 'Evening meditation',
          description: 'Bring a cushion.',
          starts_at: '2030-01-05T13:00:00.000Z',
          ends_at: null,
          location: 'Main hall',
          link_url: 'https://example.org/register',
        },
      ],
    };
    render(<UpcomingEventsCard />);
    expect(screen.getByText('Evening meditation')).toBeInTheDocument();
    expect(screen.getByText('Main hall')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /details/i });
    expect(link).toHaveAttribute('href', 'https://example.org/register');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('plays an attached video or audio recording inline', () => {
    const base = {
      description: null,
      starts_at: '2030-01-05T13:00:00.000Z',
      ends_at: null,
      location: null,
      link_url: null,
      image_url: null,
      media_path: 'x',
    };
    mocks.state = {
      loading: false,
      events: [
        { ...base, id: 'v', title: 'Talk', media_type: 'video', media_url: 'https://example.org/talk.mp4' },
        { ...base, id: 'a', title: 'Chant', media_type: 'audio', media_url: 'https://example.org/chant.mp3' },
      ],
    };
    const { container } = render(<UpcomingEventsCard />);
    expect(container.querySelector('video')).toHaveAttribute('src', 'https://example.org/talk.mp4');
    expect(container.querySelector('audio')).toHaveAttribute('src', 'https://example.org/chant.mp3');
  });
});
