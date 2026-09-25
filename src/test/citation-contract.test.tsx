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
        citation={{ ...baseCitation, speaker: 'Sri Krishnaji' }}
      />,
    );
    expect(screen.getByText('Sri Krishnaji')).toBeInTheDocument();
    expect(screen.queryByText('Ekams Wisdom')).not.toBeInTheDocument();
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
