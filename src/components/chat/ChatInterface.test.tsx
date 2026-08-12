import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ChatInterface } from './ChatInterface';

// Mock all necessary hooks and components
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
  }),
}));

vi.mock('@/lib/auth', () => ({
  useAuth: () => ({
    user: { id: 'test-id', email: 'test@example.com' },
  }),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({
    toast: vi.fn(),
  }),
}));

vi.mock('@/components/common/SereneMindProvider', () => ({
  useSereneMind: () => ({
    open: vi.fn(),
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

// Mock local storage access functions
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
}));

// Mock the AI service
vi.mock('@/lib/aiService', () => ({
  sendMessage: vi.fn().mockResolvedValue({ content: 'Mocked guru response', citations: [] }),
  sendMessageStreaming: vi.fn().mockImplementation(() => ({
    [Symbol.asyncIterator]: async function* () {
      yield { type: 'message', text: 'Mocked guru response' };
    }
  })),
  generateSummary: vi.fn().mockResolvedValue('Mock summary'),
  generateConversationTitle: vi.fn().mockResolvedValue('Finding Peace'),
  setLanguage: vi.fn(),
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

vi.mock('@/lib/responseCache', () => ({
  hashMessages: vi.fn().mockReturnValue('mockhash'),
  getCachedResponse: vi.fn().mockReturnValue(null),
  setCachedResponse: vi.fn(),
  clearResponseCache: vi.fn(),
}));

vi.mock('@/components/chat/DesktopSidebar', () => ({
  DesktopSidebar: () => <div data-testid="desktop-sidebar">Sidebar</div>,
  useSidebarCollapsed: () => ({
    isCollapsed: false,
    toggle: vi.fn(),
  }),
}));

vi.mock('@/components/chat/ChatHeader', () => ({
  ChatHeader: () => <div data-testid="chat-header">Header</div>,
}));

vi.mock('@/hooks/useDailyTeaching', () => ({
  useDailyTeaching: () => ({ teaching: null, loading: false, error: null, refetch: vi.fn() }),
}));
vi.mock('./HealingPathCard', () => ({
  HealingPathCard: () => null,
}));
vi.mock('@/components/meditation/GuidedMeditationFlow', () => ({
  GuidedMeditationFlow: () => null,
}));

vi.mock('./ChatComposer', () => ({
  ChatComposer: ({ inputValue, onInputChange, onSubmit }: {
    inputValue: string;
    onInputChange: (event: { target: { value: string } }) => void;
    onSubmit: (event: { preventDefault: () => void }) => void;
  }) => (
    <div>
      <textarea aria-label="Your message" value={inputValue} onChange={onInputChange} />
      <button aria-label="Send message" type="button" onClick={() => onSubmit({ preventDefault: () => {} })}>Send</button>
    </div>
  ),
}));

vi.mock('./DailyTeaching', () => ({
  DailyTeaching: () => null,
}));

vi.mock('@/components/chat/MessageList', () => ({
  MessageList: () => <div data-testid="message-list">Messages</div>,
}));

import { fireEvent, waitFor } from '@testing-library/react';
import { sendMessage, sendMessageStreaming } from '@/lib/aiService';
import { setCurrentConversationId } from '@/lib/chatStorage';

describe('ChatInterface', () => {
  beforeEach(() => {
    // We need browser layout shims that remain constructible after other tests.
    class TestResizeObserver {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    }
    vi.stubGlobal('ResizeObserver', TestResizeObserver);
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    vi.clearAllMocks();
  });

  it('renders without crashing and displays the sidebar', () => {
    render(
      <BrowserRouter>
        <ChatInterface />
      </BrowserRouter>
    );

    expect(screen.getByTestId('desktop-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('chat-header')).toBeInTheDocument();
  });

  it('allows user to type and send a message', async () => {
    render(
      <BrowserRouter>
        <ChatInterface />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(setCurrentConversationId).toHaveBeenCalledWith('test-conv-id');
    });
    const input = screen.getByLabelText('Your message');

    fireEvent.change(input, { target: { value: 'How do I find peace?' } });
    await waitFor(() => {
      expect(input).toHaveValue('How do I find peace?');
    });
    fireEvent.click(screen.getByLabelText('Send message'));

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

    // Check if the mock message appears in the list
    // MessageList is mocked as <div data-testid="message-list">Messages</div>
    // We should probably unmock it or check if it's called with the new messages.
    // Since it's mocked, we can't see the actual messages inside it easily unless we use props.
    // Let's improve the MessageList mock to show children or messages.
  });
});
