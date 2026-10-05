import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { normalizeCitations } from '@/lib/chat/types';
import { CitationBadge, DiscourseVideoModal, type DiscourseCitation } from '@/components/chat/CitationCard';

describe('normalizeCitations — snake_case backend payload mapping', () => {
  it('maps timestamp_seconds, text_snippet and speaker to camelCase', () => {
    const [citation] = normalizeCitations([
      {
        url: 'https://youtu.be/abc123',
        title: 'A Talk',
        speaker: 'Sri Preethaji',
        timestamp_seconds: 42,
        text_snippet: 'the exact words spoken',
      },
    ]);
    expect(citation.timestampSeconds).toBe(42);
    expect(citation.textSnippet).toBe('the exact words spoken');
    expect(citation.speaker).toBe('Sri Preethaji');
  });

  it('treats a timestamp_seconds of 0 as a valid, present value — not absent', () => {
    const [citation] = normalizeCitations([
      { url: 'https://youtu.be/abc123', timestamp_seconds: 0 },
    ]);
    expect(citation.timestampSeconds).toBe(0);
  });

  it('leaves timestampSeconds undefined when the backend sends none', () => {
    const [citation] = normalizeCitations([{ url: 'https://youtu.be/abc123' }]);
    expect(citation.timestampSeconds).toBeUndefined();
  });

  it('passes through a bare URL string citation', () => {
    const [citation] = normalizeCitations(['https://youtu.be/abc123']);
    expect(citation).toEqual({ url: 'https://youtu.be/abc123' });
  });

  it('drops entries with no resolvable url', () => {
    expect(normalizeCitations([{ title: 'no url here' }])).toEqual([]);
  });

  it('returns an empty array for non-array input', () => {
    expect(normalizeCitations(null)).toEqual([]);
    expect(normalizeCitations(undefined)).toEqual([]);
  });

  it('maps playback_start_seconds, playback_end_seconds and playback_url to camelCase', () => {
    const [citation] = normalizeCitations([
      {
        url: 'https://youtu.be/abc123',
        playback_start_seconds: 39.5,
        playback_end_seconds: 67.3,
        playback_url: 'https://www.youtube.com/watch?v=abc123&t=39s',
      },
    ]);
    expect(citation.playbackStartSeconds).toBe(39.5);
    expect(citation.playbackEndSeconds).toBe(67.3);
    expect(citation.playbackUrl).toBe('https://www.youtube.com/watch?v=abc123&t=39s');
  });

  it('treats playback_start_seconds of 0 as a valid present value — not absent', () => {
    const [citation] = normalizeCitations([
      { url: 'https://youtu.be/abc123', playback_start_seconds: 0 },
    ]);
    expect(citation.playbackStartSeconds).toBe(0);
  });
});

const baseCitation: DiscourseCitation = {
  index: 1,
  url: 'https://www.youtube.com/watch?v=abc12345678',
};

describe('CitationCard — timestamp 0 and speaker attribution', () => {
  it('DiscourseVideoModal embeds start=0 when the citation starts at second 0', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, startTimestamp: 0 }}
      />,
    );
    const iframe = document.querySelector('iframe');
    expect(iframe?.getAttribute('src')).toContain('start=0');
  });

  it('DiscourseVideoModal embeds the real start second when present', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, startTimestamp: 137 }}
      />,
    );
    const iframe = document.querySelector('iframe');
    expect(iframe?.getAttribute('src')).toContain('start=137');
  });

  it('DiscourseVideoModal shows the citation speaker from data, not a hardcoded name', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, speaker: 'Sri Krishnaji', speakerVerified: true }}
      />,
    );
    expect(screen.getByText('Sri Krishnaji')).toBeInTheDocument();
    expect(screen.queryByText('Ekams Wisdom')).not.toBeInTheDocument();
  });

  it('DiscourseVideoModal downgrades an unverified teacher name with unknown source', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, speaker: 'Sri Krishnaji' }}
      />,
    );
    expect(screen.getByText('unverified clip')).toBeInTheDocument();
    expect(screen.queryByText('Sri Krishnaji')).not.toBeInTheDocument();
  });

  it('DiscourseVideoModal falls back to a neutral label when no speaker is known', () => {
    render(<DiscourseVideoModal isOpen onClose={() => {}} citation={{ ...baseCitation }} />);
    expect(screen.getByText('Ekam teachings')).toBeInTheDocument();
  });

  it('CitationBadge hovercard renders the timestamp when it is 0', () => {
    render(
      <CitationBadge
        citation={{ ...baseCitation, startTimestamp: 0 }}
        onOpenVideoModal={() => {}}
      />,
    );
    // Hover to reveal the preview card, which is where the timestamp shows.
    const wrapper = screen.getByRole('button').parentElement as HTMLElement;
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByText('0:00')).toBeInTheDocument();
  });
});

describe('CitationCard — playback pre-roll fields (Dexa acoustic offsets)', () => {
  it('DiscourseVideoModal uses playbackStartSeconds for the iframe start when present', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, playbackStartSeconds: 39 }}
      />,
    );
    const iframe = document.querySelector('iframe');
    expect(iframe?.getAttribute('src')).toContain('start=39');
  });

  it('DiscourseVideoModal prefers playbackStartSeconds over startTimestamp', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, playbackStartSeconds: 39, startTimestamp: 42 }}
      />,
    );
    const iframe = document.querySelector('iframe');
    // pre-roll start (39) wins over raw timestamp (42)
    expect(iframe?.getAttribute('src')).toContain('start=39');
    expect(iframe?.getAttribute('src')).not.toContain('start=42');
  });

  it('DiscourseVideoModal falls back to startTimestamp when playbackStartSeconds is absent', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, startTimestamp: 42 }}
      />,
    );
    const iframe = document.querySelector('iframe');
    expect(iframe?.getAttribute('src')).toContain('start=42');
  });

  it('DiscourseVideoModal uses start=0 when playbackStartSeconds is 0 (floor case)', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, playbackStartSeconds: 0 }}
      />,
    );
    const iframe = document.querySelector('iframe');
    expect(iframe?.getAttribute('src')).toContain('start=0');
  });
});

describe('DiscourseVideoModal — YouTube start and end whole seconds', () => {
  it('ceils a fractional playbackStartSeconds to prevent preceding host bleed', () => {
    render(
      <DiscourseVideoModal isOpen onClose={() => {}} citation={{ ...baseCitation, playbackStartSeconds: 94.25 }} />,
    );
    const src = document.querySelector('iframe')?.getAttribute('src') ?? '';
    expect(src).toContain('start=95');
    expect(src).not.toContain('94.25');
  });

  it('floors a fractional playbackEndSeconds to prevent trailing host bleed', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, playbackStartSeconds: 94.25, playbackEndSeconds: 120.75 }}
      />,
    );
    const src = document.querySelector('iframe')?.getAttribute('src') ?? '';
    expect(src).toContain('start=95');
    expect(src).toContain('&end=120');
  });

  it('keeps an end bound on a clip too short for ceil/floor (never plays on unbounded)', () => {
    render(
      <DiscourseVideoModal
        isOpen
        onClose={() => {}}
        citation={{ ...baseCitation, playbackStartSeconds: 94.25, playbackEndSeconds: 95.6 }}
      />,
    );
    const src = document.querySelector('iframe')?.getAttribute('src') ?? '';
    expect(src).toContain('start=95');
    expect(src).toContain('&end=96');
  });
});
