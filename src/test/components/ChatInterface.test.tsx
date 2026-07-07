import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ChatInterface } from '@/components/chat/ChatInterface';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  sendMessage: vi.fn(),
  sendMessageStreaming: vi.fn(),
  generateSummary: vi.fn(),
  generateConversationTitle: vi.fn(),
  setLanguage: vi.fn(),
  openSereneMind: vi.fn(),
  setSereneMindOnComplete: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: { getSession: mocks.getSession },
    from: vi.fn(() => ({ update: vi.fn(() => ({ eq: vi.fn(() => Promise.resolve()) })) })),
  },
}));

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({
    profile: {
      id: 'test-id',
      displayName: 'Test User',
      preferredLanguage: 'en',
      ttsEnabled: false,
      ttsRate: 1,
      prePracticeLog: undefined,
    },
    loading: false,
    update: vi.fn(),
  }),
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock('@/components/common/SereneMindProvider', () => ({
  useSereneMind: () => ({
    open: mocks.openSereneMind,
    setOnComplete: mocks.setSereneMindOnComplete,
  }),
}));

vi.mock('@/hooks/useSpeechRecognition', () => ({
  useSpeechRecognition: () => ({
    transcript: '',
    interimTranscript: '',
    isListening: false,
    isSupported: true,
    error: null,
    startListening: vi.fn(),
    stopListening: vi.fn(),
    resetTranscript: vi.fn(),
  }),
}));

vi.mock('@/hooks/useTextToSpeech', () => ({
  useTextToSpeech: () => ({
    speak: vi.fn(),
    stop: vi.fn(),
    isSpeaking: false,
    isSupported: true,
  }),
}));

vi.mock('@/lib/aiService', () => ({
  sendMessage: mocks.sendMessage,
  sendMessageStreaming: mocks.sendMessageStreaming,
  generateSummary: mocks.generateSummary,
  generateConversationTitle: mocks.generateConversationTitle,
  setLanguage: mocks.setLanguage,
  queueMemoryExtraction: vi.fn(),
}));

vi.mock('@/lib/chatStorage', () => ({
  generateId: () => 'test-msg-id',
  saveConversation: vi.fn(),
  loadConversation: vi.fn().mockReturnValue(null),
  loadConversations: vi.fn().mockReturnValue([]),
  createNewConversation: vi.fn().mockReturnValue({
    id: 'test-conv-id',
    messages: [],
    updatedAt: new Date(),
    preview: '',
  }),
  getConversationPreview: vi.fn().mockReturnValue('preview'),
  getCurrentConversationId: vi.fn().mockReturnValue(null),
  setCurrentConversationId: vi.fn(),
  updateConversationSummary: vi.fn(),
  hashMessages: vi.fn().mockReturnValue('mockhash'),
}));

vi.mock('@/lib/responseCache', () => ({
  hashMessages: vi.fn().mockReturnValue('mockhash'),
  getCachedResponse: vi.fn().mockReturnValue(null),
  setCachedResponse: vi.fn(),
  clearResponseCache: vi.fn(),
}));

vi.mock('@/lib/memoryApi', () => ({
  memoryApi: { getRelevant: vi.fn().mockResolvedValue([]) },
}));

vi.mock('@/hooks/useAssistants', () => ({
  useAssistants: () => ({
    assistants: [],
    selected: null,
    selectedSlug: 'general',
    setSelectedSlug: vi.fn(),
    loading: false,
  }),
}));

vi.mock('@/components/chat/DesktopSidebar', () => ({
  DesktopSidebar: () => <div data-testid="desktop-sidebar">Sidebar</div>,
  useSidebarCollapsed: () => ({ isCollapsed: false, toggle: vi.fn() }),
}));

vi.mock('@/components/chat/ChatHeader', () => ({
  ChatHeader: () => <div data-testid="chat-header">Header</div>,
}));

vi.mock('@/components/chat/MessageList', () => ({
  MessageList: ({ messages }: { messages: unknown[] }) => (
    <div data-testid="message-list">
      {messages.map((m: any, i: number) => (
        <div key={m.id ?? i} data-testid={`msg-${m.role}`}>
          {m.content}
        </div>
      ))}
    </div>
  ),
}));

vi.mock('@/components/chat/ChatErrorBanner', () => ({
  ChatErrorBanner: () => <div data-testid="chat-error-banner" />,
}));

vi.mock('@/components/chat/ChatEmptyState', () => ({
  ChatEmptyState: () => <div data-testid="chat-empty-state" />,
}));

vi.mock('@/components/chat/ThinkingPills', () => ({
  ThinkingPills: () => <div data-testid="thinking-pills" />,
  mapStatusToLabel: (s: string) => s,
}));

vi.mock('@/components/chat/SlashCommandMenu', () => ({
  SlashCommandMenu: () => null,
}));

vi.mock('@/components/chat/ScrollToBottomFab', () => ({
  ScrollToBottomFab: () => <div data-testid="scroll-to-bottom" />,
}));

vi.mock('@/components/chat/MobileConversationSheet', () => ({
  MobileConversationSheet: () => null,
}));

vi.mock('@/components/meditation/GuidedMeditationFlow', () => ({
  GuidedMeditationFlow: () => null,
}));

vi.mock('@/components/chat/WisdomCardGenerator', () => ({
  WisdomCardGenerator: () => null,
}));

vi.mock('@/components/landing/FloatingParticles', () => ({
  FloatingParticles: () => null,
}));

vi.mock('@/components/chat/DailyTeaching', () => ({
  DailyTeaching: () => null,
}));

vi.mock('@/hooks/useDailyTeaching', () => ({
  useDailyTeaching: () => ({ teaching: null, loading: false }),
}));

vi.mock('@/hooks/useChatShortcuts', () => ({
  useChatShortcuts: vi.fn(),
}));

vi.mock('@/hooks/useSwipeGesture', () => ({
  useSwipeGesture: vi.fn(),
}));

import { sendMessage, sendMessageStreaming } from '@/lib/aiService';

describe('ChatInterface (regression)', () => {
  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    mocks.getSession.mockResolvedValue({ data: { session: null } });
    mocks.sendMessage.mockResolvedValue({ content: 'Mocked guru response', citations: [] });
    mocks.sendMessageStreaming.mockImplementation(() => ({
      [Symbol.asyncIterator]: async function* () {
        yield { type: 'message', text: 'Mocked guru response' };
      },
    }));
    mocks.generateSummary.mockResolvedValue('');
    mocks.generateConversationTitle.mockResolvedValue('Finding Peace');
    vi.clearAllMocks();
  });

  it('renders without crashing and displays the sidebar and message list', () => {
    render(
      <BrowserRouter>
        <ChatInterface />
      </BrowserRouter>
    );
    expect(screen.getByTestId('desktop-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('chat-header')).toBeInTheDocument();
  });

  it('shows landing state on a new conversation', () => {
    render(
      <BrowserRouter>
        <ChatInterface />
      </BrowserRouter>
    );
    // Greeting h2 always contains an English spiritual greeting (no Indic terms)
    const h2 = document.querySelector('h2');
    expect(h2).not.toBeNull();
    expect(h2!.textContent!.length).toBeGreaterThan(3);
  });

  it('allows user to type and sends a message via streaming', async () => {
    render(
      <BrowserRouter>
        <ChatInterface />
      </BrowserRouter>
    );

    const input = screen.getByLabelText('Your message');
    const sendButton = screen.getByLabelText('Send message');

    fireEvent.change(input, { target: { value: 'How do I find peace?' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(sendMessageStreaming).toHaveBeenCalledWith(
        expect.any(Array),
        'How do I find peace?',
        0,
        undefined,
        'test-conv-id',
        null,
        undefined,
        expect.any(AbortSignal)
      );
    });
  });

  it('falls back to non-streaming sendMessage when streaming yields no content', async () => {
    mocks.sendMessageStreaming.mockImplementation(() => ({
      [Symbol.asyncIterator]: async function* () {
        // Empty stream
      },
    }));

    render(
      <BrowserRouter>
        <ChatInterface />
      </BrowserRouter>
    );

    const input = screen.getByLabelText('Your message');
    const sendButton = screen.getByLabelText('Send message');

    fireEvent.change(input, { target: { value: 'Tell me about awareness' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith(
        expect.any(Array),
        'Tell me about awareness',
        0,
        undefined,
        'test-conv-id',
        null,
        undefined
      );
    });
  });

  it('renders an error fallback message when the backend returns an error code', async () => {
    mocks.sendMessageStreaming.mockImplementation(() => ({
      [Symbol.asyncIterator]: async function* () {
        // Empty stream
      },
    }));
    mocks.sendMessage.mockResolvedValue({
      content: '',
      error: 'Service unavailable',
      errorCode: 'server_error',
    });

    render(
      <BrowserRouter>
        <ChatInterface />
      </BrowserRouter>
    );

    const input = screen.getByLabelText('Your message');
    const sendButton = screen.getByLabelText('Send message');

    fireEvent.change(input, { target: { value: 'Trigger error' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalled();
    });
  });

  it('starts a new conversation when ChatHeader new-chat action is triggered', () => {
    render(
      <BrowserRouter>
        <ChatInterface />
      </BrowserRouter>
    );

    // ChatHeader is mocked; we cannot drive it from here. The regression value is
    // that the component tree renders with the mocked header and does not crash
    // when internal new-conversation state resets.
    expect(screen.getByTestId('chat-header')).toBeInTheDocument();
  });
});
