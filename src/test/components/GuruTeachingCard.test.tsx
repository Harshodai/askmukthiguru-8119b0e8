import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GuruTeachingCard } from '@/components/chat/ChatMessage';
import type { Citation } from '@/lib/chat/types';

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

const QUOTE = 'Stillness is the sacred doorway; enter without carrying yesterday.';

const verifiedCitation = (overrides: Partial<Citation> = {}): Citation => ({
  url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  title: 'Discourse on Stillness',
  quote: QUOTE,
  speaker: 'Sri Preethaji',
  speakerVerified: true,
  timestampSeconds: 76,
  playbackStartSeconds: 76,
  ...overrides,
});

describe('GuruTeachingCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the verified teaching as a distinct artifact with the byte-for-byte quote', () => {
    render(<GuruTeachingCard citation={verifiedCitation()} verified index={1} onPlay={vi.fn()} />);
    expect(screen.getByTestId('guru-teaching-card')).toBeInTheDocument();
    // Byte-for-byte: the quote node holds exactly the served text, nothing added.
    expect(screen.getByTestId('guru-teaching-quote').textContent).toBe(QUOTE);
    expect(screen.getByText('Sri Preethaji')).toBeInTheDocument();
    expect(screen.getByText('Verified')).toBeInTheDocument();
  });

  it('opens timestamped playback with the served quote and position', () => {
    const onPlay = vi.fn();
    render(<GuruTeachingCard citation={verifiedCitation()} verified index={2} onPlay={onPlay} />);
    fireEvent.click(screen.getByRole('button', { name: /Play clip: Sri Preethaji at 1:16/i }));
    expect(onPlay).toHaveBeenCalledTimes(1);
    expect(onPlay).toHaveBeenCalledWith(
      expect.objectContaining({ index: 2, quote: QUOTE, speakerVerified: true }),
    );
  });

  it('downgrades an unverified teacher name to the channel and never shows the bare name', () => {
    render(
      <GuruTeachingCard
        citation={verifiedCitation({
          speaker: 'Sri Krishnaji',
          speakerVerified: false,
          channel_name: 'Some Vlog',
        })}
        verified={false}
      />,
    );
    expect(screen.getByText('shared in Some Vlog')).toBeInTheDocument();
    expect(screen.getByText('Unverified attribution')).toBeInTheDocument();
    expect(screen.queryByText('Sri Krishnaji')).not.toBeInTheDocument();
    // The quote itself is untouched by the attribution downgrade.
    expect(screen.getByTestId('guru-teaching-quote').textContent).toBe(QUOTE);
  });

  it('falls back to "unverified clip" when an unverified teacher name has no known source', () => {
    render(
      <GuruTeachingCard
        citation={verifiedCitation({ speaker: 'Sri Krishnaji', speakerVerified: false })}
        verified={false}
      />,
    );
    expect(screen.getByText('unverified clip')).toBeInTheDocument();
    expect(screen.queryByText('Sri Krishnaji')).not.toBeInTheDocument();
  });

  it('badges a related (not direct) teaching as related, never verified', () => {
    render(<GuruTeachingCard citation={verifiedCitation()} verified related />);
    expect(screen.getByText('Related — not a direct answer')).toBeInTheDocument();
    expect(screen.queryByText('Verified')).not.toBeInTheDocument();
  });

  it('labels personalized servings as reflections in our own words, keeping the served text intact', () => {
    render(
      <GuruTeachingCard
        citation={verifiedCitation({ personalized_for: true })}
        verified={false}
      />,
    );
    expect(screen.getAllByText('Personalized reflection').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/not a direct quote from the teachers/i)).toBeInTheDocument();
    expect(screen.getByTestId('guru-teaching-quote').textContent).toBe(QUOTE);
  });

  it('renders nothing when no quotable excerpt was served', () => {
    const { container } = render(
      <GuruTeachingCard citation={verifiedCitation({ quote: undefined, textSnippet: undefined })} verified />,
    );
    expect(screen.queryByTestId('guru-teaching-card')).not.toBeInTheDocument();
    expect(container.textContent).toBe('');
  });

  it('renders served markup as inert text, never as DOM', () => {
    const malicious = 'Before <script>window.__xss_fired = true;</script> <img src=x onerror="window.__xss_fired = true">';
    const { container } = render(
      <GuruTeachingCard citation={verifiedCitation({ quote: malicious })} verified />,
    );
    expect(screen.getByTestId('guru-teaching-quote').textContent).toBe(malicious);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect((window as unknown as { __xss_fired?: boolean }).__xss_fired).toBeUndefined();
  });
});
