import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { normalizeCitations, resolveAttributionLabel } from '@/lib/chat/types';
import { isAutoTranscript } from '@/lib/transcriptStatus';
import { DiscourseAudioStrip } from '@/components/chat/DiscourseAudioStrip';
import { mapFirstPersonCitationToDiscourseCitation } from '@/lib/firstPersonCitationMapper';

const BARE = /^Sri (Preethaji|Krishnaji)$/;
const YT = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ';

const cases: Array<{ name: string; wire: Record<string, unknown>; verified: boolean }> = [
  { name: 'is_verbatim true, no speaker_verified', wire: { url: YT, speaker: 'Sri Krishnaji', is_verbatim: true, channel_name: 'Some Vlog' }, verified: false },
  { name: 'speaker_verified false', wire: { url: YT, speaker: 'Sri Krishnaji', speaker_verified: false, is_verbatim: true }, verified: false },
  { name: 'speaker_verified null', wire: { url: YT, speaker: 'Sri Preethaji', speaker_verified: null }, verified: false },
  { name: 'third-party channel', wire: { url: YT, speaker: 'Sri Krishnaji', channel_name: 'Curly Tales' }, verified: false },
  { name: 'official channel, unknown speaker', wire: { url: YT, channel_name: 'Ekam' }, verified: false },
  { name: 'timestamp 0', wire: { url: YT, speaker: 'Sri Krishnaji', timestamp_seconds: 0, is_verbatim: true }, verified: false },
  { name: 'timestamp absent', wire: { url: YT, speaker: 'Sri Krishnaji', is_verbatim: true }, verified: false },
  { name: 'malformed URL', wire: { url: 'not a url', speaker: 'Sri Krishnaji', timestamp_seconds: 5, is_verbatim: true }, verified: false },
  { name: 'title absent', wire: { url: YT, speaker: 'Sri Preethaji', is_verbatim: true }, verified: false },
  { name: 'source absent', wire: { url: YT, speaker: 'Sri Preethaji' }, verified: false },
  { name: 'speaker_verified true is honoured', wire: { url: YT, speaker: 'Sri Krishnaji', speaker_verified: true }, verified: true },
];

describe('speaker attribution provenance', () => {
  it.each(cases)('$name', ({ wire, verified }) => {
    const [c] = normalizeCitations([wire]);
    expect(c.speakerVerified === true).toBe(verified);
    const label = resolveAttributionLabel(c);
    if (!verified && label) {
      const official = ['ekam', 'o&o academy'].includes(String(wire.channel_name ?? '').toLowerCase());
      // Only the teachers' own channels may keep a bare name; never a third party or unknown source.
      if (!official) expect(label).not.toMatch(BARE);
    }
  });

  it('is_verbatim alone never sets speakerVerified', () => {
    const [c] = normalizeCitations([{ url: YT, speaker: 'Sri Krishnaji', is_verbatim: true }]);
    expect(c.speakerVerified).toBeUndefined();
  });

  it('audio strip does not show a bare teacher name for an unverified citation', () => {
    render(<DiscourseAudioStrip citation={{ url: YT, speaker: 'Sri Krishnaji', playbackStartSeconds: 76, playbackEndSeconds: 165 }} />);
    expect(screen.queryByText('Sri Krishnaji')).not.toBeInTheDocument();
    expect(screen.queryByText(/Sri Preethaji & Sri Krishnaji/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Play source clip \(01:16 – 02:45\)/ })).toBeInTheDocument();
    expect(screen.queryByText(/Guru's Voice/i)).not.toBeInTheDocument();
  });
});

describe('transcript status', () => {
  it.each([
    ['auto_transcript', true],
    ['manual_caption', false],
    ['human_reviewed', false],
    ['', false],
    [undefined, false],
  ])('isAutoTranscript(%s) = %s', (s, expected) => {
    expect(isAutoTranscript(s as string | undefined)).toBe(expected);
  });

  it('first-person mapper carries caption_status to the citation card', () => {
    const d = mapFirstPersonCitationToDiscourseCitation(
      { speaker: 'Sri Krishnaji', verbatim_text: 'Be here.', caption_status: 'auto_transcript', end_ms: 4000, timestamp_seconds: 0, source_url: YT } as never,
      1,
    );
    expect(d.transcriptStatus).toBe('auto_transcript');
    expect(d.startTimestamp).toBe(0);
  });
});
