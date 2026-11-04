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

  it('does not keep an unverified teacher name even on a teacher-owned channel', () => {
    expect(
      resolveAttributionLabel({ speaker: 'Sri Krishnaji', channelName: 'Ekam' }),
    ).toBe('shared in Ekam');
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

describe('mapFirstPersonCitationToDiscourseCitation — verified only when the backend says so (QA-1)', () => {
  it('maps speaker_verified true to verified and a missing or false flag to unverified', () => {
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
    expect(mapFirstPersonCitationToDiscourseCitation(fp, 1).speakerVerified).toBe(false);
    expect(
      mapFirstPersonCitationToDiscourseCitation({ ...fp, speaker_verified: false } as FirstPersonCitation, 1)
        .speakerVerified,
    ).toBe(false);
    const mapped = mapFirstPersonCitationToDiscourseCitation(
      { ...fp, speaker_verified: true } as FirstPersonCitation,
      1,
    );
    expect(mapped.speakerVerified).toBe(true);
    expect(resolveAttributionLabel(mapped)).toBe('Sri Krishnaji');
  });
});

describe('groupEditorialTeachingCitations — source-preserving evidence cards', () => {
  const withVerifiedSourceRights = (citation: Record<string, unknown>) => ({
    ...citation,
    speaker_id: citation.speaker_id ?? `test-speaker-${citation.teacher_id}`,
    source_span_id: citation.source_span_id
      ?? `test-span-${citation.parent_unit_id}-${citation.source_span_index}`,
    is_verbatim: true,
    rights_cleared: true,
  });
  it('joins ordered child spans only within each video and retains the full playback window', async () => {
    const { groupEditorialTeachingCitations } = await import('@/lib/chat/teachingPreview');
    const groups = groupEditorialTeachingCitations(normalizeCitations([
      {
        url: 'https://www.youtube.com/watch?v=vARTudIEq30&t=10s',
        video_id: 'vARTudIEq30',
        teacher_id: 'krishnaji',
        parent_unit_id: 'parent-k',
        source_span_id: 'span-k-0',
        source_span_index: 0,
        speaker: 'Sri Krishnaji',
        speaker_verified: true,
        verbatim_text: 'Love is not possession.',
        playback_start_seconds: 10,
        playback_end_seconds: 14,
      },
      {
        url: 'https://www.youtube.com/watch?v=vARTudIEq30&t=14s',
        video_id: 'vARTudIEq30',
        teacher_id: 'krishnaji',
        parent_unit_id: 'parent-k',
        source_span_id: 'span-k-1',
        source_span_index: 1,
        speaker: 'Sri Krishnaji',
        speaker_verified: true,
        verbatim_text: 'It is a movement without fear.',
        playback_start_seconds: 14,
        playback_end_seconds: 19,
      },
      {
        url: 'https://www.youtube.com/watch?v=_GEMrEWCiXw&t=5s',
        video_id: '_GEMrEWCiXw',
        teacher_id: 'preethaji',
        parent_unit_id: 'parent-p',
        source_span_id: 'span-p-0',
        source_span_index: 0,
        speaker: 'Sri Preethaji',
        speaker_verified: true,
        verbatim_text: 'Love is a state of connection.',
        playback_start_seconds: 5,
        playback_end_seconds: 9,
      },
    ].map(withVerifiedSourceRights)));

    expect(groups).toHaveLength(2);
    expect(groups[0].citation.quote).toBe('Love is not possession. It is a movement without fear.');
    expect(groups[0].citation.playbackStartSeconds).toBe(10);
    expect(groups[0].citation.playbackEndSeconds).toBe(19);
    expect(groups[0].citation.speakerVerified).toBe(true);
    expect(groups[0].citation.quoteSegments).toEqual([
      'Love is not possession.',
      'It is a movement without fear.',
    ]);
    expect(groups[1].citation.quote).toBe('Love is a state of connection.');
    expect(groups[1].citation.videoId).toBe('_GEMrEWCiXw');
  });

  it('does not merge a claimed video identity that disagrees with the source URL', async () => {
    const { groupEditorialTeachingCitations } = await import('@/lib/chat/teachingPreview');
    const groups = groupEditorialTeachingCitations(normalizeCitations([
      {
        url: 'https://www.youtube.com/watch?v=_GEMrEWCiXw&t=10s',
        video_id: 'vARTudIEq30',
        teacher_id: 'krishnaji',
        parent_unit_id: 'parent-k',
        source_span_index: 0,
        speaker: 'Sri Krishnaji',
        speaker_verified: true,
        verbatim_text: 'First source excerpt.',
      },
      {
        url: 'https://www.youtube.com/watch?v=vARTudIEq30&t=14s',
        video_id: 'vARTudIEq30',
        teacher_id: 'krishnaji',
        parent_unit_id: 'parent-k',
        source_span_index: 1,
        speaker: 'Sri Krishnaji',
        speaker_verified: true,
        verbatim_text: 'Second source excerpt.',
      },
    ].map(withVerifiedSourceRights)));

    expect(groups).toHaveLength(2);
    expect(groups.map((group) => group.citation.quote)).toEqual([
      'First source excerpt.',
      'Second source excerpt.',
    ]);
  });

  it('keeps different parent units and non-contiguous source spans separate', async () => {
    const { groupEditorialTeachingCitations } = await import('@/lib/chat/teachingPreview');
    const groups = groupEditorialTeachingCitations(normalizeCitations([
      {
        url: 'https://www.youtube.com/watch?v=vARTudIEq30&t=14s',
        video_id: 'vARTudIEq30',
        teacher_id: 'krishnaji',
        parent_unit_id: 'parent-a',
        source_span_index: 2,
        speaker: 'Sri Krishnaji',
        speaker_verified: true,
        verbatim_text: 'Non-adjacent excerpt.',
      },
      {
        url: 'https://www.youtube.com/watch?v=vARTudIEq30&t=19s',
        video_id: 'vARTudIEq30',
        teacher_id: 'krishnaji',
        parent_unit_id: 'parent-b',
        source_span_index: 1,
        speaker: 'Sri Krishnaji',
        speaker_verified: true,
        verbatim_text: 'Different parent excerpt.',
      },
      {
        url: 'https://www.youtube.com/watch?v=vARTudIEq30&t=10s',
        video_id: 'vARTudIEq30',
        teacher_id: 'krishnaji',
        parent_unit_id: 'parent-a',
        source_span_index: 0,
        speaker: 'Sri Krishnaji',
        speaker_verified: true,
        verbatim_text: 'First excerpt.',
      },
    ].map(withVerifiedSourceRights)));

    expect(groups).toHaveLength(3);
    expect(groups.map((group) => group.citation.quote)).toEqual([
      'First excerpt.',
      'Non-adjacent excerpt.',
      'Different parent excerpt.',
    ]);
  });

  it('orders reversed contiguous children by source span index, not retrieval order', async () => {
    const { groupEditorialTeachingCitations } = await import('@/lib/chat/teachingPreview');
    const groups = groupEditorialTeachingCitations(normalizeCitations([
      {
        url: 'https://www.youtube.com/watch?v=vARTudIEq30&t=14s',
        video_id: 'vARTudIEq30',
        teacher_id: 'krishnaji',
        parent_unit_id: 'parent-k',
        source_span_index: 1,
        speaker: 'Sri Krishnaji',
        speaker_verified: true,
        verbatim_text: 'Second source sentence.',
      },
      {
        url: 'https://www.youtube.com/watch?v=vARTudIEq30&t=10s',
        video_id: 'vARTudIEq30',
        teacher_id: 'krishnaji',
        parent_unit_id: 'parent-k',
        source_span_index: 0,
        speaker: 'Sri Krishnaji',
        speaker_verified: true,
        verbatim_text: 'First source sentence.',
      },
    ].map(withVerifiedSourceRights)));

    expect(groups).toHaveLength(1);
    expect(groups[0].citation.quote).toBe('First source sentence. Second source sentence.');
  });
});
