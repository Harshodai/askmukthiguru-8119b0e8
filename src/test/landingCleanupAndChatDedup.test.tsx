import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Navbar } from '@/components/landing/Navbar';
import Index from '@/pages/Index';
import { ChatMessage } from '@/components/chat/ChatMessage';
import type { Message } from '@/types/chat';

// Mock Capacitor
vi.mock('@capacitor/core', () => ({
  Capacitor: {
    isNativePlatform: () => false,
  },
}));

// Mock hooks
vi.mock('@/hooks/useChatCapabilities', () => ({
  useChatCapabilities: () => ({
    capabilities: { googleSso: false },
    loading: false,
  }),
}));

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({
    profile: { displayName: 'Seeker', avatarDataUrl: null, avatarUrl: null, preferredLanguage: 'en' },
    loading: false,
  }),
}));

vi.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: vi.fn(),
  }),
}));

vi.mock('@/hooks/useNotes', () => ({
  useNotes: () => ({
    createNote: vi.fn(),
  }),
}));

describe('Landing Page Cleanup', () => {
  it('does not render WhatsApp button, Wisdom Map link, or Start Chat button in Navbar', () => {
    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>,
    );

    // WhatsApp removed
    expect(screen.queryByTestId('navbar-whatsapp-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('navbar-mobile-whatsapp-button')).not.toBeInTheDocument();

    // Wisdom Map removed
    expect(screen.queryByRole('link', { name: /wisdom map/i })).not.toBeInTheDocument();

    // Start Chat button in navbar removed (Hero CTA is the primary path)
    const navLinks = screen.getAllByRole('link');
    const startChatNavButtons = navLinks.filter(
      (l) => l.textContent?.toLowerCase().includes('start chat') && l.className.includes('hidden md:inline-flex'),
    );
    expect(startChatNavButtons).toHaveLength(0);
  });

  it('does not render WisdomGraphPreview on Index landing page', () => {
    render(
      <BrowserRouter>
        <Index />
      </BrowserRouter>,
    );

    // WisdomGraphPreview heading / container not present
    expect(screen.queryByText(/living knowledge graph/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/wisdom map/i)).not.toBeInTheDocument();
  });
});

describe('ChatMessage Deduplication & Audio Strip Guard', () => {
  it('suppresses duplicate body when teachingBody includes speaker attribution header', () => {
    const verbatimQuote = 'We need them to evolve into beings living in a Beautiful State.';
    const message: Message = {
      id: 'msg-verbatim-1',
      role: 'guru',
      content: `Sri Preethaji · Discourse by Sri Preethaji\n\n${verbatimQuote}`,
      timestamp: new Date(),
      isVerbatim: true,
      citations: [
        {
          index: 1,
          url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
          title: 'Sacred Oneness Discourse',
          quote: verbatimQuote,
          textSnippet: verbatimQuote,
          speaker: 'Sri Preethaji',
          speakerVerified: true,
          rightsCleared: true,
          isVerbatim: true,
          timestampSeconds: 62,
        },
      ],
      citationsVerified: true,
      verification: { direct: false, passed: true },
    };

    render(
      <BrowserRouter>
        <ChatMessage message={message} />
      </BrowserRouter>,
    );

    // GuruTeachingCard renders the quote
    expect(screen.getByTestId('guru-teaching-card')).toBeInTheDocument();
    expect(screen.getByTestId('guru-teaching-quote')).toHaveTextContent(verbatimQuote);

    // Duplicate markdown prose is suppressed:
    // Ensure there is only 1 instance of the verbatimQuote in the message container
    const quoteMatches = screen.getAllByText((content) => content.includes(verbatimQuote));
    expect(quoteMatches).toHaveLength(1);

    // Ensure DiscourseAudioStrip is NOT rendered because GuruTeachingCard already has the player
    expect(screen.queryByTestId('discourse-audio-strip')).not.toBeInTheDocument();
    expect(screen.queryByText(/source clip/i)).not.toBeInTheDocument();
  });
});
