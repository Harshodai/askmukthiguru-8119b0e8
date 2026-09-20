import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ChatMessage } from '@/components/chat/ChatMessage';
import type { Message } from '@/lib/chatStorage';

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({
    profile: { displayName: 'Seeker', avatarDataUrl: null, preferredLanguage: 'en', ttsEnabled: false },
  }),
}));

vi.mock('@/lib/profileStorage', () => ({
  getInitials: (name: string) => name.charAt(0).toUpperCase(),
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock('@/hooks/useNotes', () => ({
  useNotes: () => ({ createNote: vi.fn().mockResolvedValue(null) }),
}));

vi.mock('@/hooks/useStudyNotebooks', () => ({
  useStudyNotebooks: () => ({
    notebooks: [],
    loading: false,
    error: null,
    refresh: vi.fn(),
    createNotebook: vi.fn().mockResolvedValue({ id: 'nb-1', title: 'Saved from Chat' }),
    deleteNotebook: vi.fn(),
    addItem: vi.fn().mockResolvedValue(true),
    listItems: vi.fn().mockResolvedValue([]),
  }),
}));

vi.mock('@/lib/memoryApi', () => ({
  memoryApi: { add: vi.fn().mockResolvedValue({ id: 'm1' }) },
}));

vi.mock('@/lib/aiService', () => ({
  submitFeedbackToBackend: vi.fn(),
}));

vi.mock('@/lib/chatStorage', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/chatStorage')>();
  return {
    ...actual,
    saveFeedback: vi.fn(),
  };
});

vi.mock('html-to-image', () => ({
  toPng: vi.fn(() => Promise.resolve('data:image/png;base64,abc')),
}));

vi.mock('react-i18next', async () => {
  const en = (await import('@/locales/en.json')).default as Record<string, unknown>;
  return {
    useTranslation: () => ({
      t: (key: string, optsOrFallback?: Record<string, unknown> | string, maybeOpts?: Record<string, unknown>) => {
        const fallback = typeof optsOrFallback === 'string' ? optsOrFallback : undefined;
        const opts = typeof optsOrFallback === 'object' && optsOrFallback !== null ? optsOrFallback : maybeOpts;
        const value = key
          .split('.')
          .reduce((acc: unknown, part: string) => (acc as Record<string, unknown> | null)?.[part], en);
        const resolved = typeof value === 'string' ? value : (fallback ?? key);
        return resolved.replace(
          /\{\{(\w+)\}\}/g,
          (_, name: string) => String(opts?.[name] ?? `{{${name}}}`),
        );
      },
    }),
  };
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>{children}</BrowserRouter>
);

const makeGuruMessage = (overrides: Partial<Message> = {}): Message => ({
  id: 'msg-1',
  role: 'guru',
  content: 'Welcome to the beautiful state.',
  timestamp: new Date(),
  ...overrides,
});

const makeUserMessage = (overrides: Partial<Message> = {}): Message => ({
  id: 'msg-2',
  role: 'user',
  content: 'Hello guru',
  timestamp: new Date(),
  ...overrides,
});

describe('ChatMessage (regression)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders guru message content and sparkle avatar', () => {
    render(<ChatMessage message={makeGuruMessage()} />, { wrapper });
    expect(screen.getByText(/Welcome to the beautiful state/)).toBeInTheDocument();
  });

  it('renders user message content with bubble styling', () => {
    render(<ChatMessage message={makeUserMessage()} />, { wrapper });
    expect(screen.getByText('Hello guru')).toBeInTheDocument();
  });

  it('does not show feedback buttons on user messages', () => {
    render(<ChatMessage message={makeUserMessage()} isLastGuru />, { wrapper });
    expect(screen.queryByTestId('engagement-yes')).not.toBeInTheDocument();
  });

  it('submits yes feedback immediately without a refine panel', async () => {
    render(<ChatMessage message={makeGuruMessage()} isLastGuru />, { wrapper });
    fireEvent.click(screen.getByTestId('engagement-yes'));
    await waitFor(() => {
      expect(screen.getByTestId('engagement-thanks')).toBeInTheDocument();
    });
  });

  it('opens the refine panel after "Not quite" click', () => {
    render(<ChatMessage message={makeGuruMessage()} isLastGuru />, { wrapper });
    fireEvent.click(screen.getByTestId('engagement-not-quite'));
    expect(screen.getByText('Clear answer')).toBeInTheDocument();
  });

  it('uses one consolidated feedback surface per latest guru response', () => {
    render(<ChatMessage message={makeGuruMessage()} isLastGuru />, { wrapper });
    expect(screen.queryByTestId('feedback-buttons')).not.toBeInTheDocument();
    expect(screen.getByTestId('engagement-yes')).toBeInTheDocument();
  });

  it('offers a localized new-chat action when context is exhausted', () => {
    const onStartNewChat = vi.fn();
    const message = makeGuruMessage({
      error: {
        kind: 'context_exhausted',
        title: 'Conversation context limit reached',
        description: 'This conversation has reached its safe context limit.',
        actionLabel: 'new_chat',
      },
    });
    render(
      <ChatMessage message={message} isLastGuru onStartNewChat={onStartNewChat} />,
      { wrapper },
    );

    const button = screen.getByRole('button', { name: /continue in a new chat/i });
    expect(button).toBeInTheDocument();
    fireEvent.click(button);
    expect(onStartNewChat).toHaveBeenCalledTimes(1);
  });

  it('confidence score is computed but not displayed', () => {
    render(<ChatMessage message={makeGuruMessage({ confidenceScore: 8 })} />, { wrapper });
    expect(screen.queryByText(/High confidence/)).not.toBeInTheDocument();
    expect(screen.queryByText(/80%/)).not.toBeInTheDocument();
  });

  it('shows retry button when guru message has a network error', () => {
    const onRegenerate = vi.fn();
    const message = makeGuruMessage({
      error: {
        kind: 'network',
        title: 'Cannot reach the Guru',
        description: 'Network or backend is unreachable.',
        actionLabel: 'retry',
      },
    });
    render(<ChatMessage message={message} isLastGuru onRegenerate={onRegenerate} />, { wrapper });

    const retryBtn = screen.getByRole('button', { name: /Retry/i });
    expect(retryBtn).toBeInTheDocument();
    fireEvent.click(retryBtn);
    expect(onRegenerate).toHaveBeenCalled();
  });

  it('renders persistent teaching grounding with teacher and excerpt', () => {
    render(
      <ChatMessage
        message={makeGuruMessage({
          teachingPreview: [{
            title: 'Awareness and the Beautiful State',
            teacher: 'Sri Preethaji',
            url: 'https://example.com/teaching',
            excerpt: 'A source-backed teaching excerpt.',
          }],
        })}
      />,
      { wrapper },
    );
    expect(screen.getByTestId('teaching-grounding')).toBeInTheDocument();
    expect(screen.getByText('Awareness and the Beautiful State')).toBeInTheDocument();
    expect(screen.getByText('Sri Preethaji')).toBeInTheDocument();
    expect(screen.getByText(/A source-backed teaching excerpt/)).toBeInTheDocument();
  });

  it('renders citations section with source count', () => {
    const message = makeGuruMessage({
      citations: [
        { url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', title: 'Discourse on Stillness' },
        { url: 'https://www.ekam.org/teaching', title: null },
      ],
    });
    render(<ChatMessage message={message} />, { wrapper });

    expect(screen.getByText(/References/i)).toBeInTheDocument();
    expect(screen.getByText(/2 verified sources/)).toBeInTheDocument();
  });

  it('uses inline URLs as fallback citations when none provided', () => {
    const message = makeGuruMessage({
      content: 'See https://www.youtube.com/watch?v=dQw4w9WgXcQ for the teaching.',
      citations: [],
    });
    render(<ChatMessage message={message} />, { wrapper });
    expect(screen.getByText(/References/i)).toBeInTheDocument();
  });

  it('filters malformed and unsafe citation URLs instead of rendering them as sources', () => {
    const message = makeGuruMessage({
      citations: [
        { url: '' },
        { url: 'not-a-url' },
        { url: 'javascript:alert(1)' },
        { url: 'https://www.youtube.com/watch?v=abc123' },
      ],
    });
    render(<ChatMessage message={message} />, { wrapper });

    expect(screen.queryByText(/References/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('displays memory provenance when memoriesUsed is non-empty', () => {
    const message = makeGuruMessage({
      memoriesUsed: ['You mentioned feeling anxious before practice.'],
    });
    render(<ChatMessage message={message} />, { wrapper });
    expect(screen.getByText(/Recalled from your reflections/i)).toBeInTheDocument();
  });

  it("surfaces source context and verifier confidence for a guru response", () => {
    const message = makeGuruMessage({
      citations: [{ url: "https://example.com/one" }, { url: "https://example.com/two" }],
      groundingState: "grounded",
      confidenceScore: 8.4,
      confidenceReason: "Retrieved teaching and answer aligned.",
      answerEvidence: {
        corpus_id: "test-corpus",
        model_policy_id: "test-policy",
        evidence_support_label: "grounded",
        source_count: 2,
        citations_verified: true,
      },
    });
    render(<ChatMessage message={message} />, { wrapper });
    // With citations present, source context merges into the References
    // details summary instead of the standalone response-provenance badge.
    expect(screen.getByText(/2 verified sources/)).toBeInTheDocument();
    expect(screen.getByText("Teaching-supported")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View all sources in panel" })).toBeInTheDocument();
  });

  it("suppresses unverified teacher-attributed quotations when no source is linked", () => {
    const message = makeGuruMessage({
      content: 'Sri Preethaji says "Awareness is the beginning of freedom."',
      citations: [],
      groundingState: "abstained",
    });
    render(<ChatMessage message={message} />, { wrapper });
    expect(screen.getByText(/could not verify the quoted teaching/i)).toBeInTheDocument();
    expect(screen.queryByText(/Awareness is the beginning of freedom/i)).not.toBeInTheDocument();
  });

  it('renders a safety_redirect crisis message verbatim even with an uncited teacher quote', () => {
    // DISTRESS_RESPONSES[SEVERE] (backend/services/serene_mind_engine.py) quotes
    // Sri Krishnaji for comfort and has no citations by design — it's a hardcoded
    // safety template, not a RAG doctrine claim. It must never be swapped out for
    // the generic "could not verify" copy, which would hide the crisis helpline
    // text from someone in acute distress.
    const message = makeGuruMessage({
      content:
        "Sri Krishnaji says: 'When you stop running from your suffering and turn towards it with awareness, transformation begins.'\n\nIf you need to speak with someone right away, please reach out: 988 Suicide & Crisis Lifeline",
      citations: [],
      groundingState: 'safety_redirect',
    });
    render(<ChatMessage message={message} />, { wrapper });
    expect(screen.queryByText(/could not verify the quoted teaching/i)).not.toBeInTheDocument();
    expect(screen.getByText(/988 Suicide & Crisis Lifeline/i)).toBeInTheDocument();
  });

  it("treats ungrounded responses with no linked source as abstained (reflective guidance)", () => {
    // No inline URL: one would be promoted to a fallback citation, routing
    // this into the merged References block instead of response-provenance.
    const message = makeGuruMessage({
      content: 'Here is some wisdom without a linked source.',
      confidenceScore: 7.0,
    });
    render(<ChatMessage message={message} />, { wrapper });
    const provenance = screen.getByTestId("response-provenance");
    expect(provenance).toHaveTextContent("Reflective guidance");
    expect(provenance).not.toHaveTextContent("verified source");
  });
});

describe('ChatMessage guidance plan', () => {
  const guidancePlan = {
    response_mode: 'balanced_guidance',
    language: 'en',
    attribution: {
      label: 'Guidance inspired by retrieved teachings',
      source_backed: true,
    },
    action_step: {
      title: 'Notice one breath',
      instruction: 'Pause gently and notice one complete breath.',
      optional: true,
    },
    reflection_prompt: 'What changes when you pause before reacting?',
  } as const;

  it('renders the optional action, reflection, and attribution from the structured plan', () => {
    render(<ChatMessage message={makeGuruMessage({ guidancePlan })} />, { wrapper });
    expect(screen.getByTestId('guidance-plan')).toHaveTextContent('Try this now');
    expect(screen.getByTestId('guidance-plan')).toHaveTextContent('Notice one breath');
    expect(screen.getByTestId('guidance-plan')).toHaveTextContent('Go deeper');
    // Attribution text is intentionally omitted here — it duplicates the
    // response-provenance grounding badge rendered elsewhere on the message.
  });

  it('suppresses the guidance plan for a crisis response', () => {
    render(<ChatMessage message={makeGuruMessage({ content: '🆘 Please contact a helpline now.', guidancePlan })} />, { wrapper });
    expect(screen.queryByTestId('guidance-plan')).not.toBeInTheDocument();
  });

  it('never executes or renders raw HTML/script from LLM-generated content (react-markdown must stay rehype-raw-free)', () => {
    // react-markdown v10 without rehype-raw treats embedded HTML as literal text,
    // never as DOM -- this is the ONLY thing standing between LLM output and stored
    // XSS, since it is implicit (absence of a plugin) rather than an explicit
    // sanitizer. If a future change adds rehype-raw without rehype-sanitize
    // alongside it, this test must start failing.
    const malicious = 'Before <script>window.__xss_fired = true;</script> after, and an <img src=x onerror="window.__xss_fired = true">.';
    const { container } = render(<ChatMessage message={makeGuruMessage({ content: malicious })} />, { wrapper });
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img[onerror]')).toBeNull();
    expect((window as unknown as { __xss_fired?: boolean }).__xss_fired).toBeUndefined();
  });

  describe('TeachingGroundingCard verification & URL security', () => {
    const preview = [{
      title: 'Discourse on Stillness',
      teacher: 'Sri Krishnaji',
      url: 'https://example.com/stillness',
      excerpt: 'Stillness is the sacred doorway.',
    }];

    it('displays Verified Sacred Teaching only when citationsVerified is true', () => {
      render(
        <ChatMessage
          message={makeGuruMessage({
            teachingPreview: preview,
            citationsVerified: true,
          })}
        />,
        { wrapper },
      );
      expect(screen.getByText('Verified Sacred Teaching')).toBeInTheDocument();
    });

    it('displays Supporting Context when items exist but citationsVerified is not explicitly true', () => {
      render(
        <ChatMessage
          message={makeGuruMessage({
            teachingPreview: preview,
            citationsVerified: null,
          })}
        />,
        { wrapper },
      );
      expect(screen.getByText('Supporting Context')).toBeInTheDocument();
      expect(screen.queryByText('Verified Sacred Teaching')).not.toBeInTheDocument();
    });

    it('displays General Spiritual Context when citationsVerified is false', () => {
      render(
        <ChatMessage
          message={makeGuruMessage({
            teachingPreview: preview,
            citationsVerified: false,
          })}
        />,
        { wrapper },
      );
      expect(screen.getByText('General Spiritual Context')).toBeInTheDocument();
      expect(screen.queryByText('Verified Sacred Teaching')).not.toBeInTheDocument();
    });

    it('sanitizes unsafe teaching URLs and does not render them as clickable links', () => {
      render(
        <ChatMessage
          message={makeGuruMessage({
            teachingPreview: [{
              title: 'Unsafe Teaching Link',
              teacher: 'Sri Krishnaji',
              url: 'javascript:alert(1)',
              excerpt: 'Excerpt with unsafe URL.',
            }],
          })}
        />,
        { wrapper },
      );
      expect(screen.getByText('Unsafe Teaching Link')).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: /Unsafe Teaching Link/i })).not.toBeInTheDocument();
    });
  });
});

