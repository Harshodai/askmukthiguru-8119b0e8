import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ChatMessage, isFirstPersonAbstainMessage } from '@/components/chat/ChatMessage';
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
    expect(screen.getByText(/Sources cited: 2/)).toBeInTheDocument();
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
    // With citations present, clean source pill replaces bulky details and raw debug scores
    expect(screen.getByText(/Sources cited: 2/)).toBeInTheDocument();
    expect(screen.queryByText("Teaching-supported")).not.toBeInTheDocument();
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

  it("skips response-provenance on plain abstains (grounding card already says it)", () => {
    // Owner declutter: the grounding card's "No direct discourse match" and
    // this row's "No grounded teaching was found" stack the same fact twice.
    // The row stays only when it adds a score or a distinct state.
    const message = makeGuruMessage({
      content: 'I could not find a verified teaching for this.',
      citations: [],
      groundingState: "abstained",
    });
    render(<ChatMessage message={message} />, { wrapper });
    expect(screen.queryByTestId("response-provenance")).not.toBeInTheDocument();
    expect(screen.getByTestId("teaching-grounding")).toBeInTheDocument();
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

    it('never labels source-only partial evidence as Verified, even when citationsVerified is true', () => {
      render(
        <ChatMessage
          message={makeGuruMessage({
            teachingPreview: preview,
            citationsVerified: true,
            verification: { passed: false, method: 'grounded_partial_evidence', partial: true, citations_verified: true },
          })}
        />,
        { wrapper },
      );
      expect(screen.getByText('Closest passages (not verified)')).toBeInTheDocument();
      expect(screen.queryByText('Verified Sacred Teaching')).not.toBeInTheDocument();
    });

    it('live partial-evidence payload shape (bare-URL citations, abstained, partial) claims nothing as verified', () => {
      // Shape captured live 2026-10-11: titles/snippets/speakers all null.
      const { container } = render(
        <ChatMessage
          message={makeGuruMessage({
            citations: [
              { url: 'https://www.youtube.com/watch?v=vARTudIEq30', title: null, speakerVerified: undefined },
              { url: 'https://www.youtube.com/watch?v=_GEMrEWCiXw', title: null, speakerVerified: undefined },
            ] as never,
            groundingState: 'abstained',
            citationsVerified: true,
            verification: { passed: false, method: 'grounded_partial_evidence', partial: true, citations_verified: true },
          })}
        />,
        { wrapper },
      );
      const text = container.textContent ?? '';
      expect(text).not.toMatch(/verified sacred teaching/i);
      // No fabricated clip range / authenticity claim for title-less, timestamp-less sources.
      expect(text).not.toMatch(/01:16/);
      expect(text).not.toMatch(/authentic discourse/i);
      // Backend now sends partial evidence as `abstained`: the card must say partial, and must
      // not claim there are no citations while the references block lists sources.
      expect(text).not.toMatch(/without direct discourse citations/i);
      expect(text).not.toMatch(/no direct discourse match/i);
      expect(screen.getByText('Closest passages (not verified)')).toBeInTheDocument();
    });

    it('first-person weak match (verification.direct=false) is never badged Verified', () => {
      render(
        <ChatMessage
          message={makeGuruMessage({
            teachingPreview: preview,
            groundingState: 'grounded',
            citationsVerified: true,
            verification: { passed: true, method: 'first_person_verbatim_clip_gate', citations_verified: true, direct: false },
          })}
        />,
        { wrapper },
      );
      expect(screen.getByText('Related teaching — not a direct answer')).toBeInTheDocument();
      expect(screen.queryByText('Verified Sacred Teaching')).not.toBeInTheDocument();
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

describe('ChatMessage seeker-readiness (faculty review 2026-10-05)', () => {
  it('shows no grounding label on the client-authored welcome greeting', () => {
    render(<ChatMessage message={makeGuruMessage({ isWelcome: true })} isLastGuru />, { wrapper });
    expect(screen.queryByTestId('response-provenance')).not.toBeInTheDocument();
    expect(screen.queryByText(/Reflective guidance/)).not.toBeInTheDocument();
  });

  it('does not stack a "Verification unavailable" row under a failed message', () => {
    const message = makeGuruMessage({
      content: 'The Guru could not be reached.',
      groundingState: 'system_error',
      error: {
        kind: 'network',
        title: 'Connection problem',
        description: 'The Guru could not be reached. Check your connection and retry.',
        retryable: true,
        actionLabel: 'retry',
      },
    });
    render(<ChatMessage message={message} isLastGuru />, { wrapper });
    expect(screen.queryByText('Verification unavailable')).not.toBeInTheDocument();
  });

  it('offers no copy or read-aloud on a failed message', () => {
    const message = makeGuruMessage({
      content: "AskMukthiGuru can't answer right now. Please try again in a moment.",
      groundingState: 'system_error',
      error: {
        kind: 'server_error',
        title: 'Something went wrong',
        description: 'This answer could not be completed. Please retry.',
        retryable: true,
        actionLabel: 'retry',
      },
    });
    render(<ChatMessage message={message} isLastGuru />, { wrapper });
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.queryByTitle(/copy/i)).not.toBeInTheDocument();
    expect(screen.queryByTitle(/read aloud/i)).not.toBeInTheDocument();
  });

  it('hides the engineering "Deepen & Tune" panel by default', () => {
    const message = makeGuruMessage({
      content: 'The Beautiful State is a state of connection. Inner Stillness follows.',
      groundingState: 'grounded',
    });
    render(<ChatMessage message={message} isLastGuru />, { wrapper });
    expect(screen.queryByText(/Memgraph/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/bolt:\/\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/Deepen & Tune/i)).not.toBeInTheDocument();
  });
});

describe('ChatMessage H9 — reflection prompt is labelled as product-generated (not the teacher\'s words)', () => {
  // Mitigation label lives in ChatMessage.tsx (aside[data-testid="atma-vichara-inquiry"]
  // > p[data-testid="reflection-prompt-label"]). It is hardcoded English copy,
  // not an i18n key, so assert the literal string.
  const REFLECTION_LABEL =
    "Optional reflection prompt inspired by the cited teaching. It is not the teacher's own words.";

  // A cited guru answer split by the '---' divider into teaching body +
  // Atma Vichara inquiry body — the exact shape that triggers the aside.
  const makeReflectionMessage = (): Message =>
    makeGuruMessage({
      content:
        'The Beautiful State arises when you stop resisting what is.\n\n---\n\nWhat changes when you pause before reacting?',
      citations: [{ url: 'https://www.ekam.org/teaching', title: 'The Beautiful State' }],
      groundingState: 'grounded',
    });

  it('renders the H9 label verbatim and scopes the reflection content to the labelled prompt', () => {
    const { container } = render(<ChatMessage message={makeReflectionMessage()} />, { wrapper });

    const inquiry = screen.getByTestId('atma-vichara-inquiry');
    expect(inquiry).toHaveAttribute(
      'aria-label',
      'Optional reflection prompt inspired by the cited teaching',
    );

    const label = screen.getByTestId('reflection-prompt-label');
    expect(label.textContent?.trim()).toBe(REFLECTION_LABEL);
    // Label sits inside the same container as the reflection, before its content.
    expect(inquiry.contains(label)).toBe(true);
    expect(inquiry).toHaveTextContent('What changes when you pause before reacting?');

    // The reflection must NOT be presented inside the primary "guru teaching
    // words" hero block (the .prose container that renders corpus text).
    const hero = container.querySelector('.prose');
    expect(hero).not.toBeNull();
    expect(hero).toHaveTextContent('The Beautiful State arises when you stop resisting what is.');
    expect(hero).not.toHaveTextContent('What changes when you pause before reacting?');

    // No teacher authorship is claimed anywhere in the reflection block.
    expect(inquiry.textContent ?? '').not.toMatch(/Sri\s+(Krishnaji|Preethaji)/);
    expect(inquiry.textContent ?? '').not.toMatch(/\b(said|says|teaches|words of)\b/i);
  });

  it('does not show the reflection label on a normal cited answer with no inquiry section', () => {
    render(
      <ChatMessage
        message={makeGuruMessage({ content: 'Teaching about inner stillness and awareness.' })}
      />,
      { wrapper },
    );
    expect(screen.queryByTestId('atma-vichara-inquiry')).not.toBeInTheDocument();
    expect(screen.queryByTestId('reflection-prompt-label')).not.toBeInTheDocument();
    expect(screen.queryByText(REFLECTION_LABEL)).not.toBeInTheDocument();
  });
});

describe('ChatMessage personalize this teaching (T-B14)', () => {
  const clip = {
    url: 'https://www.youtube.com/watch?v=eumRL5DfFzM&t=91s',
    title: 'Talk',
    timestampSeconds: 91,
  };

  it('shows no button unless the parent allows personalization', () => {
    render(<ChatMessage message={makeGuruMessage({ citations: [clip] })} />, { wrapper });
    expect(screen.queryByTestId('personalize-teaching')).not.toBeInTheDocument();
  });

  it('says what personalization uses and links to the saved memory', () => {
    render(
      <ChatMessage message={makeGuruMessage({ citations: [clip] })} onPersonalizeTeaching={vi.fn()} />,
      { wrapper },
    );
    expect(screen.getByTestId('personalize-note')).toHaveTextContent('Uses only memories you chose to save.');
    expect(screen.getByRole('button', { name: 'Review what is saved' })).toBeInTheDocument();
    expect(screen.getByTestId('personalize-teaching')).toHaveAttribute('aria-describedby');
  });

  it('shows the button and sends the served clip id and start second', () => {
    const onPersonalizeTeaching = vi.fn();
    render(
      <ChatMessage
        message={makeGuruMessage({ citations: [clip] })}
        onPersonalizeTeaching={onPersonalizeTeaching}
      />,
      { wrapper },
    );
    fireEvent.click(screen.getByTestId('personalize-teaching'));
    expect(onPersonalizeTeaching).toHaveBeenCalledWith({
      video_id: 'eumRL5DfFzM',
      timestamp_seconds: 91,
    });
  });

  it('hides the button when the citation has no real timestamp or video id', () => {
    const { rerender } = render(
      <ChatMessage
        message={makeGuruMessage({ citations: [{ url: clip.url, title: 'Talk' }] })}
        onPersonalizeTeaching={vi.fn()}
      />,
      { wrapper },
    );
    expect(screen.queryByTestId('personalize-teaching')).not.toBeInTheDocument();
    rerender(
      <ChatMessage
        message={makeGuruMessage({
          citations: [{ url: 'https://example.com/post', title: 'Post', timestampSeconds: 5 }],
        })}
        onPersonalizeTeaching={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('personalize-teaching')).not.toBeInTheDocument();
  });

  it('treats a start of 0 seconds as a real timestamp', () => {
    const onPersonalizeTeaching = vi.fn();
    render(
      <ChatMessage
        message={makeGuruMessage({ citations: [{ ...clip, timestampSeconds: 0 }] })}
        onPersonalizeTeaching={onPersonalizeTeaching}
      />,
      { wrapper },
    );
    fireEvent.click(screen.getByTestId('personalize-teaching'));
    expect(onPersonalizeTeaching).toHaveBeenCalledWith({ video_id: 'eumRL5DfFzM', timestamp_seconds: 0 });
  });

  it('hides the button when the citation is already personalized (personalized_for: true)', () => {
    render(
      <ChatMessage
        message={makeGuruMessage({ citations: [{ ...clip, personalized_for: true }] })}
        onPersonalizeTeaching={vi.fn()}
      />,
      { wrapper },
    );
    expect(screen.queryByTestId('personalize-teaching')).not.toBeInTheDocument();
  });

  it('hides the button when message.content contains the personalization disclaimer label', () => {
    // Backend flag authoritative when citations exist (Slice C): content-sniff
    // is a fallback solely for citation-less legacy bubbles. With citations
    // and no flag, the button shows; without citations, the label hides it.
    const personalizedContent =
      'Teaching text here.\n\n_This is a personalized reflection on the teaching above, in our own words — not a direct quote from the teachers._';
    const { rerender } = render(
      <ChatMessage
        message={makeGuruMessage({ content: personalizedContent, citations: [clip] })}
        onPersonalizeTeaching={vi.fn()}
      />,
      { wrapper },
    );
    expect(screen.queryByTestId('personalize-teaching')).toBeInTheDocument();
    rerender(
      <ChatMessage
        message={makeGuruMessage({ content: personalizedContent, citations: [] })}
        onPersonalizeTeaching={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('personalize-teaching')).not.toBeInTheDocument();
  });

  describe('first-person abstain (Track 2)', () => {
    it('isFirstPersonAbstainMessage accurately detects all abstain signals', () => {
      // 1. Explicit flag
      expect(isFirstPersonAbstainMessage(makeGuruMessage({ isFirstPersonAbstain: true }))).toBe(true);

      // 2. Route decision
      expect(isFirstPersonAbstainMessage(makeGuruMessage({ routeDecision: 'first_person_abstain' }))).toBe(true);

      // 3. Verification method
      expect(
        isFirstPersonAbstainMessage(
          makeGuruMessage({ verification: { method: 'first_person_no_match_abstain' } }),
        ),
      ).toBe(true);
      expect(
        isFirstPersonAbstainMessage(
          makeGuruMessage({ verification: { method: 'first_person_store_unavailable' } }),
        ),
      ).toBe(true);

      // 4. Content fallback phrases
      expect(
        isFirstPersonAbstainMessage(
          makeGuruMessage({
            content: "I don't have a verified verbatim teaching that directly answers this question.",
          }),
        ),
      ).toBe(true);
      expect(
        isFirstPersonAbstainMessage(
          makeGuruMessage({
            content: 'I would rather say so than improvise one.',
          }),
        ),
      ).toBe(true);

      // 5. Normal messages
      expect(
        isFirstPersonAbstainMessage(
          makeGuruMessage({
            content: 'In Sri Krishnaji’s teachings, a beautiful state is free of inner conflict.',
            citations: [clip],
          }),
        ),
      ).toBe(false);
    });

    it('renders AbstainHelpCard when message is a first-person abstain', () => {
      const onAction = vi.fn();
      render(
        <ChatMessage
          message={makeGuruMessage({
            content:
              "I don't have a verified verbatim teaching that directly answers this specific question. I would rather say so than improvise one.",
            isFirstPersonAbstain: true,
          })}
          onAction={onAction}
        />,
        { wrapper },
      );

      expect(screen.getByTestId('abstain-help-card')).toBeInTheDocument();
      expect(screen.getByText('Explore Verified Teachings')).toBeInTheDocument();

      // Clicking a bank question propagates to onAction
      const q0 = screen.getByTestId('abstain-question-0');
      fireEvent.click(q0);
      expect(onAction).toHaveBeenCalledWith(
        'What is the difference between a beautiful state and a suffering state?',
      );

      // Clicking an OKF chip propagates to onAction
      const chip0 = screen.getByTestId('abstain-chip-0');
      fireEvent.click(chip0);
      expect(onAction).toHaveBeenCalledWith('Beautiful State');
    });

    it('does NOT render AbstainHelpCard on standard cited guru message', () => {
      render(
        <ChatMessage
          message={makeGuruMessage({
            content: 'Here is a genuine teaching from Sri Krishnaji.',
            citations: [clip],
          })}
        />,
        { wrapper },
      );

      expect(screen.queryByTestId('abstain-help-card')).not.toBeInTheDocument();
    });

    it('does NOT render AbstainHelpCard while streaming or when message has an error', () => {
      const { rerender } = render(
        <ChatMessage
          message={makeGuruMessage({
            content: "I don't have a verified verbatim teaching.",
            isFirstPersonAbstain: true,
          })}
          isStreaming={true}
        />,
        { wrapper },
      );
      expect(screen.queryByTestId('abstain-help-card')).not.toBeInTheDocument();

      rerender(
        <ChatMessage
          message={makeGuruMessage({
            content: '',
            isFirstPersonAbstain: true,
            error: {
              kind: 'network',
              title: 'Connection error',
              description: 'Failed to reach server',
            },
          })}
          isStreaming={false}
        />,
      );
      expect(screen.queryByTestId('abstain-help-card')).not.toBeInTheDocument();
    });
  });
});
