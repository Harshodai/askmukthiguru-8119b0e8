import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProvenanceDrawer } from '@/components/compliance/ProvenanceDrawer';
import { CitationBadge, DiscourseVideoModal } from '@/components/chat/CitationCard';
import { StreamingStatusPill } from '@/components/chat/StreamingStatusPill';
import { normalizeCitations, resolveAttributionLabel } from '@/lib/chat/types';
import { mapFirstPersonCitationToDiscourseCitation } from '@/lib/firstPersonCitationMapper';
import { FEATURE_FLAGS } from '@/lib/featureFlags';
import type { AIProvenanceManifest } from '@/types/provenance';

vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));

const YT = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ';
const BARE_TEACHER = /\bSri (Preethaji|Krishnaji)\b/;

const manifest: AIProvenanceManifest = {
  id: 'm1',
  originType: 'ai_generated',
  riskTier: 'transparency',
  modality: 'text',
  generatedAt: '2026-10-07T00:00:00.000Z',
  modelDescriptor: { name: 'M', version: '1', provider: 'P', parameters: 'x' },
  latencyMs: 100,
  grounding: {
    status: 'grounded',
    sourceCount: 3,
    sources: [{ title: 'A teaching', url: 'https://example.com/a' }],
    confidenceScore: 0.94,
    evidenceSupportLabel: 'Dual-Layer Doctrine Retrieval',
    corpusVersion: 'v1',
  },
  disclosure: { article: 'Article 50(1)', notice: 'n', plainLanguageDisclosure: 'p' },
};

const hover = (container: HTMLElement) => {
  fireEvent.mouseEnter(container.querySelector('span.relative') as Element);
};

describe('(a) third-party verbatim clip never renders a bare teacher attribution', () => {
  const wire = {
    url: YT,
    speaker: 'Sri Krishnaji',
    is_verbatim: true,
    channel_name: 'Some Vlog',
    verbatim_text: 'Be here now.',
  };

  it('chat hover card and modal show no bare teacher name', () => {
    const [c] = normalizeCitations([wire]);
    expect(c.speakerVerified).toBeUndefined();
    const card = {
      index: 1,
      url: c.url,
      speaker: resolveAttributionLabel(c),
      speakerVerified: c.speakerVerified,
      quote: c.quote,
    };
    const { container } = render(<CitationBadge citation={card} onOpenVideoModal={() => {}} />);
    hover(container);
    expect(screen.getByText(/shared in Some Vlog/)).toBeInTheDocument();
    expect(screen.queryByText(BARE_TEACHER)).not.toBeInTheDocument();

    render(<DiscourseVideoModal isOpen onClose={() => {}} citation={card} />);
    expect(screen.queryByText(BARE_TEACHER)).not.toBeInTheDocument();
  });

  it('card given the raw wire speaker still downgrades', () => {
    const { container } = render(
      <CitationBadge
        citation={{ index: 1, url: YT, speaker: 'Sri Krishnaji', channelName: 'Some Vlog', quote: 'Be here now.' }}
        onOpenVideoModal={() => {}}
      />,
    );
    hover(container);
    expect(screen.queryByText(BARE_TEACHER)).not.toBeInTheDocument();
  });

  it('first-person mapper does not stamp verification over an explicit speaker_verified:false', () => {
    const d = mapFirstPersonCitationToDiscourseCitation(
      {
        speaker: 'Sri Krishnaji',
        verbatim_text: 'x',
        speaker_verified: false,
        end_ms: 1000,
        timestamp_seconds: 0,
        source_url: YT,
      } as never,
      1,
    );
    expect(d.speakerVerified).not.toBe(true);
  });
});

describe('(b) no seeker view renders confidence or verified-source counts', () => {
  it('ProvenanceDrawer hides Confidence Score, percentage and "verified sources"', () => {
    render(<ProvenanceDrawer isOpen onClose={() => {}} manifest={manifest} />);
    expect(screen.getByText('Knowledge Grounding Lineage')).toBeInTheDocument();
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();
    expect(screen.queryByText('94%')).not.toBeInTheDocument();
    expect(screen.queryByText(/verified source/i)).not.toBeInTheDocument();
    expect(screen.getByText('A teaching')).toBeInTheDocument();
  });

  it('StreamingStatusPill inspector never says "Verified Chunks"', () => {
    render(<StreamingStatusPill visible retrievedCount={7} />);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.queryByText(/verified/i)).not.toBeInTheDocument();
  });
});

describe('(c) chat citation cards show transcript status', () => {
  const open = (citation: Record<string, unknown>) => {
    const { container } = render(
      <CitationBadge
        citation={{ index: 1, url: YT, quote: 'Be here now.', ...citation } as never}
        onOpenVideoModal={() => {}}
      />,
    );
    hover(container);
  };

  it('defaults to Auto-transcript when no status field is present', () => {
    open({});
    expect(screen.getByTestId('auto-transcript-note')).toHaveTextContent(/auto-transcript/i);
  });

  it('shows Auto-transcript for auto-transcript status', () => {
    open({ transcriptStatus: 'auto-transcript' });
    expect(screen.getByTestId('auto-transcript-note')).toBeInTheDocument();
  });

  it('hides it only when the status says reviewed', () => {
    open({ transcriptStatus: 'reviewed' });
    expect(screen.queryByTestId('auto-transcript-note')).not.toBeInTheDocument();
  });

  it('modal also defaults to Auto-transcript', () => {
    render(
      <DiscourseVideoModal isOpen onClose={() => {}} citation={{ index: 1, url: YT, quote: 'Be here now.' }} />,
    );
    expect(screen.getByTestId('auto-transcript-note')).toBeInTheDocument();
  });

  it('normalizeCitations carries transcript_status; mapper prefers it over caption_status', () => {
    const [c] = normalizeCitations([{ url: YT, transcript_status: 'reviewed' }]);
    expect(c.transcriptStatus).toBe('reviewed');
    const d = mapFirstPersonCitationToDiscourseCitation(
      {
        speaker: 'Sri Krishnaji',
        verbatim_text: 'x',
        transcript_status: 'reviewed',
        caption_status: 'auto_transcript',
        end_ms: 1000,
        timestamp_seconds: 0,
        source_url: YT,
      } as never,
      1,
    );
    expect(d.transcriptStatus).toBe('reviewed');
  });
});

describe('Deepen & Tune bar', () => {
  it('is hidden by default', () => {
    expect(FEATURE_FLAGS.deepenAndTuneBar).toBe(false);
  });
});
