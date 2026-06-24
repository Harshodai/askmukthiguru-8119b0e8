import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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

  it('renders user message content and initials avatar', () => {
    render(<ChatMessage message={makeUserMessage()} />, { wrapper });
    expect(screen.getByText('Hello guru')).toBeInTheDocument();
    expect(screen.getByText('S')).toBeInTheDocument();
  });

  it('does not show feedback buttons on user messages', () => {
    render(<ChatMessage message={makeUserMessage()} />, { wrapper });
    expect(screen.queryByTitle('Helpful')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Not helpful')).not.toBeInTheDocument();
  });

  it('opens feedback panel after thumbs up click', () => {
    render(<ChatMessage message={makeGuruMessage()} />, { wrapper });
    fireEvent.click(screen.getByTitle('Helpful'));
    expect(screen.getByText('What helped?')).toBeInTheDocument();
    expect(screen.getByText('Clear answer')).toBeInTheDocument();
  });

  it('opens feedback panel after thumbs down click', () => {
    render(<ChatMessage message={makeGuruMessage()} />, { wrapper });
    fireEvent.click(screen.getByTitle('Not helpful'));
    expect(screen.getByText('What could improve?')).toBeInTheDocument();
  });

  it('shows confidence score badge when present', () => {
    render(<ChatMessage message={makeGuruMessage({ confidenceScore: 8 })} />, { wrapper });
    expect(screen.getByText('Confidence: 8/10')).toBeInTheDocument();
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

  it('renders citations section with source count', () => {
    const message = makeGuruMessage({
      citations: [
        'https://www.youtube.com/watch?v=abc123',
        'https://www.ekam.org/teaching',
      ],
    });
    render(<ChatMessage message={message} />, { wrapper });

    expect(screen.getByText(/References/i)).toBeInTheDocument();
    expect(screen.getByText('2 sources')).toBeInTheDocument();
  });

  it('uses inline URLs as fallback citations when none provided', () => {
    const message = makeGuruMessage({
      content: 'See https://www.youtube.com/watch?v=xyz for the teaching.',
      citations: [],
    });
    render(<ChatMessage message={message} />, { wrapper });
    expect(screen.getByText(/References/i)).toBeInTheDocument();
  });

  it('displays memory provenance when memoriesUsed is non-empty', () => {
    const message = makeGuruMessage({
      memoriesUsed: ['You mentioned feeling anxious before practice.'],
    });
    render(<ChatMessage message={message} />, { wrapper });
    expect(screen.getByText(/Recalled from your reflections/i)).toBeInTheDocument();
  });
});
