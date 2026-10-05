import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { normalizeCitations, resolveAttributionLabel } from '@/lib/chat/types';
import { CitationBadge, type DiscourseCitation } from '@/components/chat/CitationCard';
import { mapFirstPersonCitationToDiscourseCitation } from '@/lib/firstPersonCitationMapper';
import type { FirstPersonCitation } from '@/lib/firstPersonService';

describe('resolveAttributionLabel — unverified teacher-name downgrade', () => {
  it('keeps verified citations byte-identical (bare teacher name, no suffix)', () => {
    expect(
      resolveAttributionLabel({
        speaker: 'Sri Krishnaji',
        speakerVerified: true,
        channelName: 'Curly Tales',
      }),
    ).toBe('Sri Krishnaji');
  });

  it('downgrades an unverified teacher name from a third-party channel', () => {
    expect(
      resolveAttributionLabel({
        speaker: 'Sri Krishnaji',
        speakerVerified: false,
        channelName: 'Curly Tales',
      }),
    ).toBe('shared in Curly Tales');
  });

  it('downgrades null verification with null title/unknown source (Q2 shape)', () => {
    expect(
      resolveAttributionLabel({
        speaker: 'Sri Krishnaji',
        speakerVerified: null,
        channelName: null,
        source: 'Unknown Channel',
      }),
    ).toBe('unverified clip');
  });

  it('downgrades when verification is simply absent and no source is known', () => {
    expect(resolveAttributionLabel({ speaker: 'Sri Preethaji' })).toBe('unverified clip');
  });

  it('keeps an unverified teacher name from a teacher-owned channel', () => {
    expect(
      resolveAttributionLabel({ speaker: 'Sri Krishnaji', channelName: 'Ekam' }),
    ).toBe('Sri Krishnaji');
  });

  it('passes non-teacher speakers through untouched', () => {
    expect(resolveAttributionLabel({ speaker: 'Unknown Channel' })).toBe('Unknown Channel');
  });

  it('returns undefined when no speaker is known (caller falls back)', () => {
    expect(resolveAttributionLabel({})).toBeUndefined();
  });

  it('is idempotent: downgraded labels never re-trigger the rule', () => {
    const once = resolveAttributionLabel({ speaker: 'Sri Krishnaji' });
    expect(once).toBe('unverified clip');
    expect(resolveAttributionLabel({ speaker: once })).toBe('unverified clip');
  });
});

describe('normalizeCitations — speaker_verified passthrough', () => {
  it('maps snake_case speaker_verified to camelCase speakerVerified', () => {
    const [citation] = normalizeCitations([
      {
        url: 'https://youtu.be/abc123',
        speaker: 'Sri Krishnaji',
        speaker_verified: false,
        channel_name: 'Curly Tales',
      },
    ]);
    expect(citation.speakerVerified).toBe(false);
    expect(citation.speaker).toBe('Sri Krishnaji');
    expect(citation.channel_name).toBe('Curly Tales');
  });

  it('leaves speakerVerified undefined when the backend sends none', () => {
    const [citation] = normalizeCitations([{ url: 'https://youtu.be/abc123' }]);
    expect(citation.speakerVerified).toBeUndefined();
  });
});

describe('CitationBadge — unverified attribution rendering', () => {
  const base: DiscourseCitation = {
    index: 1,
    url: 'https://www.youtube.com/watch?v=abc12345678',
  };

  it('hovercard renders a downgraded label for an unverified teacher name', () => {
    render(
      <CitationBadge
        citation={{ ...base, speaker: 'Sri Krishnaji', channelName: 'Curly Tales' }}
        onOpenVideoModal={() => {}}
      />,
    );
    const wrapper = screen.getByRole('button').parentElement as HTMLElement;
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByText('shared in Curly Tales')).toBeInTheDocument();
  });

  it('hovercard renders the bare name for a verified citation', () => {
    render(
      <CitationBadge
        citation={{
          ...base,
          speaker: 'Sri Krishnaji',
          speakerVerified: true,
          channelName: 'Curly Tales',
        }}
        onOpenVideoModal={() => {}}
      />,
    );
    const wrapper = screen.getByRole('button').parentElement as HTMLElement;
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByText('Sri Krishnaji')).toBeInTheDocument();
  });
});

describe('teachingPreviewsFromCitations — attribution downgrade', () => {
  it('downgrades unverified teacher names in preview cards', async () => {
    const { teachingPreviewsFromCitations } = await import('@/lib/chat/teachingPreview');
    const [preview] = teachingPreviewsFromCitations(
      normalizeCitations([
        {
          url: 'https://youtu.be/abc123',
          title: null,
          speaker: 'Sri Krishnaji',
          speaker_verified: null,
          source: 'Unknown Channel',
          quote: 'some teaching words',
        },
      ]),
    );
    expect(preview.teacher).toBe('unverified clip');
  });

  it('keeps verified teacher names byte-identical in preview cards', async () => {
    const { teachingPreviewsFromCitations } = await import('@/lib/chat/teachingPreview');
    const [preview] = teachingPreviewsFromCitations(
      normalizeCitations([
        {
          url: 'https://youtu.be/abc123',
          title: 'A Talk',
          speaker: 'Sri Krishnaji',
          speaker_verified: true,
          quote: 'some teaching words',
        },
      ]),
    );
    expect(preview.teacher).toBe('Sri Krishnaji');
  });
});

describe('mapFirstPersonCitationToDiscourseCitation — verified by construction', () => {
  it('marks mapped FP citations verified so teacher labels render unchanged', () => {
    const fp = {
      video_id: 'abc12345678',
      start_ms: 1000,
      end_ms: 5000,
      timestamp_seconds: 1,
      speaker: 'Sri Krishnaji',
      transcript_hash: 'h',
      verbatim_text: 'words',
      text_snippet: 'words',
      source_url: 'https://www.youtube.com/watch?v=abc12345678',
      video_url: 'https://www.youtube.com/watch?v=abc12345678',
      confidence: 0.9,
      is_verbatim: true,
      provenance_kind: 'speech_turn_clip',
      caption_status: 'auto_transcript',
    } as FirstPersonCitation;
    const mapped = mapFirstPersonCitationToDiscourseCitation(fp, 1);
    expect(mapped.speakerVerified).toBe(true);
    expect(resolveAttributionLabel(mapped)).toBe('Sri Krishnaji');
  });
});
