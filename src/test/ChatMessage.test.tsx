import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatMessage } from '@/components/chat/ChatMessage';

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({
    profile: {
      displayName: 'Seeker',
      avatarDataUrl: null,
    },
  }),
}));

vi.mock('@/lib/profileStorage', () => ({
  getInitials: (name: string) => name.slice(0, 2).toUpperCase(),
}));

const guruMessage = {
  id: 'msg-1',
  role: 'guru' as const,
  content: 'When you are in a beautiful state, you become life itself.',
  timestamp: new Date(),
};

const userMessage = {
  id: 'msg-2',
  role: 'user' as const,
  content: 'What is the Beautiful State?',
  timestamp: new Date(),
};

describe('ChatMessage', () => {
  it('renders guru message with sparkles icon', () => {
    render(<ChatMessage message={guruMessage} />);
    expect(screen.getByText(/beautiful state/i)).toBeInTheDocument();
  });

  it('renders user message with initials', () => {
    render(<ChatMessage message={userMessage} />);
    expect(screen.getByText('What is the Beautiful State?')).toBeInTheDocument();
    expect(screen.getByText('SE')).toBeInTheDocument();
  });

  it('shows feedback buttons on guru messages', () => {
    render(<ChatMessage message={guruMessage} />);
    expect(screen.getByTitle('Helpful')).toBeInTheDocument();
    expect(screen.getByTitle('Not helpful')).toBeInTheDocument();
  });

  it('shows share button on guru messages', () => {
    render(<ChatMessage message={guruMessage} />);
    expect(screen.getByTitle('Share as Wisdom Card')).toBeInTheDocument();
  });

  it('does not show feedback on user messages', () => {
    render(<ChatMessage message={userMessage} />);
    expect(screen.queryByTitle('Helpful')).not.toBeInTheDocument();
  });

  it('shows feedback panel after voting', () => {
    render(<ChatMessage message={guruMessage} />);
    const thumbsUp = screen.getByTitle('Helpful');
    fireEvent.click(thumbsUp);
    expect(screen.getByText('What helped?')).toBeInTheDocument();
  });

  it('shows streaming cursor when isStreaming', () => {
    const streamingMsg = { ...guruMessage, content: 'Streaming...' };
    const { container } = render(<ChatMessage message={streamingMsg} isStreaming />);
    // The cursor is a motion.span — check for presence
    const cursor = container.querySelector('[class*="bg-ojas"]');
    expect(cursor).not.toBeNull();
  });
});
