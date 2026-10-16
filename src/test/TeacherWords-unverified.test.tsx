import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TeacherWords from '@/pages/TeacherWords';
import { queryFirstPerson } from '@/lib/firstPersonService';
import type { FirstPersonResponse } from '@/lib/firstPersonService';

/**
 * Slice D — TeacherWords unverified-downgrade (owner ruling 2026-10-16:
 * unverified clips never show a bare teacher name).
 *
 * First-person payloads carry no channel, so the downgraded label on this
 * surface is the `unverified clip` fallback; the `shared in <channel>` form
 * (channel-carrying citations) is pinned in citation-attribution.test.tsx.
 * The verified control below proves the absence assertion is sensitive —
 * the harness renders the bare name when verification is present.
 */

vi.mock('@/lib/firstPersonService', async () => {
  const actual = await vi.importActual<typeof import('@/lib/firstPersonService')>(
    '@/lib/firstPersonService',
  );
  return {
    ...actual,
    queryFirstPerson: vi.fn(),
  };
});

vi.mock('@/components/layout/PublicShell', () => ({
  PublicShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/chat/InlineActions', () => ({
  InlineActions: () => null,
  EngagementCard: () => null,
}));

const QUOTE = 'Awareness watches the movement of thought without following it.';

function unverifiedCitation(overrides = {}) {
  return {
    video_id: 'abc123',
    point_id: 'p1',
    start_ms: 0,
    end_ms: 4000,
    timestamp_seconds: 0,
    speaker: 'Sri Krishnaji',
    speaker_verified: false,
    teacher_id: 'krishnaji',
    transcript_hash: 'hash',
    verbatim_text: QUOTE,
    text_snippet: QUOTE,
    source_url: 'https://www.youtube.com/watch?v=abc123&t=0s',
    video_url: 'https://www.youtube.com/watch?v=abc123',
    confidence: 0.95,
    is_verbatim: true,
    provenance_kind: 'speech_turn_clip',
    caption_status: 'auto_transcript',
    ...overrides,
  };
}

function responseFor(citation: unknown): FirstPersonResponse {
  return {
    answer_text: 'quote',
    citations: [citation],
    status: 'success',
    is_direct_answer: true,
    latency_ms: 100,
    cached: false,
    error: null,
  } as FirstPersonResponse;
}

async function askQuestion() {
  fireEvent.change(screen.getByLabelText(/your question/i), {
    target: { value: 'What is awareness?' },
  });
  fireEvent.click(screen.getByRole('button', { name: /ask|searching/i }));
}

describe('TeacherWords unverified-downgrade', () => {
  beforeEach(() => {
    vi.mocked(queryFirstPerson).mockReset();
  });

  it('downgrades an unverified clip and never shows the bare teacher name', async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue(responseFor(unverifiedCitation()));

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByText(/Awareness watches the movement of thought/)).toBeInTheDocument();
    });
    expect(screen.getByText('unverified clip')).toBeInTheDocument();
    expect(screen.queryByText('Sri Krishnaji')).not.toBeInTheDocument();
  });

  it('downgrades null verification the same as false', async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue(
      responseFor(unverifiedCitation({ speaker_verified: null })),
    );

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByText('unverified clip')).toBeInTheDocument();
    });
    expect(screen.queryByText('Sri Krishnaji')).not.toBeInTheDocument();
  });

  it('control: a verified clip still renders the bare teacher name', async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue(
      responseFor(unverifiedCitation({ speaker_verified: true })),
    );

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByText('Sri Krishnaji')).toBeInTheDocument();
    });
    expect(screen.queryByText('unverified clip')).not.toBeInTheDocument();
  });
});
