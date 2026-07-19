import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatMessage } from '@/components/chat/ChatMessage';
import { BrowserRouter } from 'react-router-dom';
import type { Message } from '@/lib/chatStorage';

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({
    profile: { displayName: 'Seeker', avatarDataUrl: null },
  }),
}));

vi.mock('@/lib/profileStorage', () => ({
  getInitials: (name: string) => name.charAt(0).toUpperCase(),
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

const guruMessage: Message = {
  id: 'msg-1',
  role: 'guru',
  content: 'Welcome to the beautiful state.',
  timestamp: new Date(),
};

const userMessage: Message = {
  id: 'msg-2',
  role: 'user',
  content: 'Hello guru',
  timestamp: new Date(),
};

describe('ChatMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders guru message with sparkle icon', () => {
    render(<ChatMessage message={guruMessage} />, { wrapper });
    expect(screen.getByText(/Welcome to the beautiful state/)).toBeInTheDocument();
  });

  it('renders user message with bubble styling', () => {
    render(<ChatMessage message={userMessage} />, { wrapper });
    expect(screen.getByText('Hello guru')).toBeInTheDocument();
  });

  it('shows feedback tags panel after thumbs up click', async () => {
    render(<ChatMessage message={guruMessage} />, { wrapper });
    const thumbsUp = screen.getByTitle('Helpful');
    fireEvent.click(thumbsUp);
    expect(screen.getByText('What helped?')).toBeInTheDocument();
    expect(screen.getByText('Clear answer')).toBeInTheDocument();
  });

  it('shows different label for thumbs down', () => {
    render(<ChatMessage message={guruMessage} />, { wrapper });
    const thumbsDown = screen.getByTitle('Not helpful');
    fireEvent.click(thumbsDown);
    expect(screen.getByText('What could improve?')).toBeInTheDocument();
  });

  it('allows selecting feedback tags', () => {
    render(<ChatMessage message={guruMessage} />, { wrapper });
    const thumbsUp = screen.getByTitle('Helpful');
    fireEvent.click(thumbsUp);
    const tagBtn = screen.getByText('Calming tone');
    fireEvent.click(tagBtn);
    expect(tagBtn.className).toContain('border-ojas');
  });

  it('does not show feedback buttons for user messages', () => {
    render(<ChatMessage message={userMessage} />, { wrapper });
    expect(screen.queryByTitle('Helpful')).not.toBeInTheDocument();
  });

  it('confidence score is computed but not displayed', () => {
    const msgWithScore: Message = {
      ...guruMessage,
      confidenceScore: 8,
    };
    render(<ChatMessage message={msgWithScore} />, { wrapper });
    expect(screen.queryByText(/High confidence/)).not.toBeInTheDocument();
    expect(screen.queryByText(/80%/)).not.toBeInTheDocument();
  });
});
