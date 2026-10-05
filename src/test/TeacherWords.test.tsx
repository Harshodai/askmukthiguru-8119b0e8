import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TeacherWords from '@/pages/TeacherWords';
import { queryFirstPerson, FirstPersonError } from '@/lib/firstPersonService';
import type { FirstPersonResponse } from '@/lib/firstPersonService';

vi.mock('@/lib/firstPersonService', async () => {
  const actual = await vi.importActual<typeof import('@/lib/firstPersonService')>(
    '@/lib/firstPersonService',
  );
  return {
    ...actual,
    queryFirstPerson: vi.fn(),
  };
});

// PublicShell renders Navbar/Footer, which pull in auth/i18n context not
// relevant here — stub it down to a passthrough so tests exercise TeacherWords only.
vi.mock('@/components/layout/PublicShell', () => ({
  PublicShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const citation = {
  video_id: 'abc123',
  start_ms: 0,
  end_ms: 4000,
  timestamp_seconds: 0,
  speaker: 'Sri Krishnaji',
  teacher_id: 'krishnaji',
  transcript_hash: 'hash',
  verbatim_text: 'The Beautiful State is a state of consciousness.',
  text_snippet: 'The Beautiful State is a state of consciousness.',
  source_url: 'https://www.youtube.com/watch?v=abc123&t=0s',
  video_url: 'https://www.youtube.com/watch?v=abc123',
  confidence: 0.95,
  is_verbatim: true,
  provenance_kind: 'speech_turn_clip',
  caption_status: 'auto_transcript',
};

function successResponse(overrides: Partial<FirstPersonResponse> = {}): FirstPersonResponse {
  return {
    answer_text: 'quote',
    citations: [citation],
    status: 'success',
    is_direct_answer: true,
    latency_ms: 100,
    cached: false,
    error: null,
    ...overrides,
  } as FirstPersonResponse;
}

async function askQuestion(text = 'What is the Beautiful State?') {
  fireEvent.change(screen.getByLabelText(/your question/i), { target: { value: text } });
  // Matches "Ask" or the in-flight "Searching…" label, so this also works
  // for a second submit fired while the first request is still pending.
  fireEvent.click(screen.getByRole('button', { name: /ask|searching/i }));
}

describe('TeacherWords page', () => {
  beforeEach(() => {
    vi.mocked(queryFirstPerson).mockReset();
  });

  it('renders a direct-answer success result with the real speaker and clip', async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue(successResponse());

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByText(/The Beautiful State is a state of consciousness/)).toBeInTheDocument();
    });
    expect(screen.getByText('Sri Krishnaji')).toBeInTheDocument();
    expect(screen.getByText('auto-transcript')).toBeInTheDocument();
    expect(screen.queryByText(/Related, not a direct answer/i)).not.toBeInTheDocument();
  });

  it('labels a weak match as "Related, not a direct answer"', async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue(
      successResponse({ status: 'weak_match', is_direct_answer: false }),
    );

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByText(/Related, not a direct answer/i)).toBeInTheDocument();
    });
  });

  it('shows an honest abstention message with no clips', async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue({
      answer_text: 'No verified first-person discourse found for this question.',
      citations: [],
      status: 'abstained',
      is_direct_answer: false,
      latency_ms: 80,
      cached: false,
      error: null,
    } as FirstPersonResponse);

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(
        screen.getByText('No verified first-person discourse found for this question.'),
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /play clip/i })).not.toBeInTheDocument();
  });

  it('renders crisis redirect text prominently with no clips', async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue({
      answer_text: 'If you are in crisis, call 988.',
      citations: [],
      status: 'crisis_redirect',
      is_direct_answer: false,
      latency_ms: 40,
      cached: false,
      error: null,
    } as FirstPersonResponse);

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('If you are in crisis, call 988.');
    });
    expect(screen.queryByRole('button', { name: /play clip/i })).not.toBeInTheDocument();
  });

  it('surfaces a 404 "disabled" error without swallowing it, and offers no Retry', async () => {
    vi.mocked(queryFirstPerson).mockRejectedValue(
      new FirstPersonError('disabled', 'First-person verbatim mode is currently disabled.', 404),
    );

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/enabled on this deployment/i);
    });
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });

  it('shows a Retry button for a network error', async () => {
    vi.mocked(queryFirstPerson).mockRejectedValue(
      new FirstPersonError('network', 'Could not reach the backend. Check your connection and try again.'),
    );

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/could not reach the backend/i);
    });
    expect(screen.getByRole('button', { name: /retry/i })).toBeEnabled();
  });

  it('shows a Retry button for an unavailable (503) error and retries the same query', async () => {
    vi.mocked(queryFirstPerson)
      .mockRejectedValueOnce(new FirstPersonError('unavailable', 'temporarily unavailable', 503))
      .mockResolvedValueOnce(successResponse());

    render(<TeacherWords />);
    await askQuestion('what is grace?');

    const retryButton = await screen.findByRole('button', { name: /retry/i });
    expect(retryButton).toBeEnabled();
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(queryFirstPerson).toHaveBeenLastCalledWith('what is grace?', expect.anything());
    });
    await waitFor(() => {
      expect(screen.getByText(/The Beautiful State is a state of consciousness/)).toBeInTheDocument();
    });
  });

  it('disables Retry for a rate_limited error until the wait elapses, and shows the wait', async () => {
    vi.mocked(queryFirstPerson).mockRejectedValue(
      new FirstPersonError('rate_limited', 'Too many requests — please wait a moment and try again.', 429, 1),
    );

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/retry in 1s/i);
    });
    const retryButton = screen.getByRole('button', { name: /retry/i });
    expect(retryButton).toBeDisabled();

    await waitFor(
      () => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeEnabled();
      },
      { timeout: 2000 },
    );
  });

  it('never lets an older in-flight response overwrite a newer one', async () => {
    let resolveFirst: (v: FirstPersonResponse) => void;
    let resolveSecond: (v: FirstPersonResponse) => void;
    const firstPromise = new Promise<FirstPersonResponse>((res) => {
      resolveFirst = res;
    });
    const secondPromise = new Promise<FirstPersonResponse>((res) => {
      resolveSecond = res;
    });

    vi.mocked(queryFirstPerson).mockImplementationOnce(() => firstPromise).mockImplementationOnce(() => secondPromise);

    render(<TeacherWords />);
    await askQuestion('first question');
    await askQuestion('second question');

    resolveSecond!(
      successResponse({ citations: [{ ...citation, verbatim_text: 'Second answer text.' }] }),
    );
    await waitFor(() => {
      expect(screen.getByText(/Second answer text/)).toBeInTheDocument();
    });

    // The stale first request resolves late — it must not clobber the newer result.
    resolveFirst!(
      successResponse({ citations: [{ ...citation, verbatim_text: 'First answer text (stale).' }] }),
    );
    await new Promise((r) => setTimeout(r, 10));
    expect(screen.getByText(/Second answer text/)).toBeInTheDocument();
    expect(screen.queryByText(/First answer text \(stale\)/)).not.toBeInTheDocument();
  });

  it('blocks empty and whitespace-only submissions', () => {
    render(<TeacherWords />);
    const askButton = screen.getByRole('button', { name: /ask/i });
    expect(askButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/your question/i), { target: { value: '   ' } });
    expect(askButton).toBeDisabled();
    expect(queryFirstPerson).not.toHaveBeenCalled();
  });

  it('caps input length to match the backend request model (2000 chars)', () => {
    render(<TeacherWords />);
    expect(screen.getByLabelText(/your question/i)).toHaveAttribute('maxlength', '2000');
  });

  it('has an aria-live polite region wrapping the results', () => {
    const { container } = render(<TeacherWords />);
    expect(container.querySelector('[aria-live="polite"]')).toBeInTheDocument();
  });

  it('moves focus to the results heading after a successful response', async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue(successResponse());

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /teachings found/i })).toHaveFocus();
    });
  });

  it("gives the Play clip button an accessible name including the speaker and time", async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue(
      successResponse({ citations: [{ ...citation, timestamp_seconds: 274 }] }),
    );

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Play clip: Sri Krishnaji at 4:34/i })).toBeInTheDocument();
    });
  });

  it('shows the playback window from playback_start_seconds, rendering 0 as 0:00', async () => {
    vi.mocked(queryFirstPerson).mockResolvedValue(
      successResponse({ citations: [{ ...citation, playback_start_seconds: 0 }] }),
    );

    render(<TeacherWords />);
    await askQuestion();

    await waitFor(() => {
      expect(screen.getByText(/from 0:00/)).toBeInTheDocument();
    });
  });
});
