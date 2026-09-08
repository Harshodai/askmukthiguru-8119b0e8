import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { isSevereDistressLevel, shouldGateSereneMind } from '@/lib/chat/sereneMindGating';
import { SereneMindModal } from '@/components/chat/SereneMindModal';
import { GuidedMeditationFlow } from '@/components/meditation/GuidedMeditationFlow';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion');
  return {
    ...actual,
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

vi.mock('@/hooks/useBreathTeaching', () => ({
  useBreathTeaching: () => ({ teaching: null, loading: false, error: false }),
}));

describe('sereneMindGating helper', () => {
  it('treats only SEVERE/CRISIS (any case) as severe', () => {
    expect(isSevereDistressLevel('SEVERE')).toBe(true);
    expect(isSevereDistressLevel('CRISIS')).toBe(true);
    expect(isSevereDistressLevel('severe')).toBe(true);
    expect(isSevereDistressLevel('crisis')).toBe(true);
    expect(isSevereDistressLevel('MODERATE')).toBe(false);
    expect(isSevereDistressLevel('MILD')).toBe(false);
    expect(isSevereDistressLevel('NONE')).toBe(false);
    expect(isSevereDistressLevel(null)).toBe(false);
    expect(isSevereDistressLevel(undefined)).toBe(false);
  });

  it('does NOT gate generic guardrail blocks (no distress level)', () => {
    expect(
      shouldGateSereneMind({ blocked: true, blockReason: 'output_guardrail', distressLevel: null }),
    ).toBe(false);
    expect(
      shouldGateSereneMind({ blocked: true, blockReason: 'output_guardrail_violence' }),
    ).toBe(false);
  });

  it('does NOT gate moderate distress or circuit-breaker blocks', () => {
    expect(
      shouldGateSereneMind({ blocked: true, blockReason: 'output_guardrail', distressLevel: 'MODERATE' }),
    ).toBe(false);
    expect(
      shouldGateSereneMind({ blocked: true, blockReason: 'circuit_breaker_open', distressLevel: 'CRISIS' }),
    ).toBe(false);
    expect(
      shouldGateSereneMind({ blocked: false, blockReason: 'output_guardrail', distressLevel: 'SEVERE' }),
    ).toBe(false);
  });

  it('gates only SEVERE/CRISIS blocks', () => {
    expect(
      shouldGateSereneMind({ blocked: true, blockReason: 'output_guardrail', distressLevel: 'SEVERE' }),
    ).toBe(true);
    expect(
      shouldGateSereneMind({ blocked: true, blockReason: 'output_guardrail', distressLevel: 'CRISIS' }),
    ).toBe(true);
  });
});

describe('SereneMindModal skip affordance', () => {
  it('always shows close + skip even when gated', () => {
    render(<SereneMindModal isOpen onClose={vi.fn()} initialTab="video" isGated />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Close')).toBeInTheDocument();
    expect(screen.getByText(/continue chatting/i)).toBeInTheDocument();
  });

  it('does not trap Escape when gated (close stays available)', () => {
    const onClose = vi.fn();
    render(<SereneMindModal isOpen onClose={onClose} initialTab="video" isGated />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByLabelText('Close')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('GuidedMeditationFlow skip affordance', () => {
  it('always shows close even when gated', () => {
    render(<GuidedMeditationFlow isOpen onClose={vi.fn()} isGated />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Close')).toBeInTheDocument();
  });
});

const chatMocks = vi.hoisted(() => ({
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
    auth: { getSession: chatMocks.getSession },
    from: vi.fn(() => ({ update: vi.fn(() => ({ eq: vi.fn(() => Promise.resolve()) })) })),
  },
}));

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({
    profile: { id: 't', displayName: 'Test User', preferredLanguage: 'en', ttsEnabled: false, ttsRate: 1 },
    loading: false,
    update: vi.fn(),
  }),
}));

vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));

vi.mock('@/components/common/SereneMindProvider', () => ({
  useSereneMind: () => ({ open: chatMocks.openSereneMind, setOnComplete: chatMocks.setSereneMindOnComplete }),
}));

vi.mock('@/hooks/useSpeechRecognition', () => ({
  useSpeechRecognition: () => ({
    transcript: '', interimTranscript: '', isListening: false, isSupported: true, error: null,
    startListening: vi.fn(), stopListening: vi.fn(), resetTranscript: vi.fn(),
  }),
}));

vi.mock('@/hooks/useTextToSpeech', () => ({
  useTextToSpeech: () => ({ speak: vi.fn(), stop: vi.fn(), isSpeaking: false, isSupported: true }),
}));

vi.mock('@/lib/aiService', () => ({
  sendMessage: chatMocks.sendMessage,
  sendMessageStreaming: chatMocks.sendMessageStreaming,
  generateSummary: chatMocks.generateSummary,
  generateConversationTitle: chatMocks.generateConversationTitle,
  setLanguage: chatMocks.setLanguage,
  queueMemoryExtraction: vi.fn(),
}));

vi.mock('@/lib/chatStorage', () => ({
  generateId: () => 'test-msg-id',
  saveConversation: vi.fn(async () => {}),
  loadConversation: vi.fn(async () => null),
  loadConversations: vi.fn(async () => []),
  createNewConversation: vi.fn().mockReturnValue({ id: 'c1', messages: [], updatedAt: new Date(), preview: '' }),
  getConversationPreview: vi.fn().mockReturnValue('preview'),
  getCurrentConversationId: vi.fn(async () => null),
  setCurrentConversationId: vi.fn(async () => {}),
  updateConversationSummary: vi.fn(async () => {}),
  hashMessages: vi.fn().mockReturnValue('mockhash'),
}));

vi.mock('@/lib/responseCache', () => ({
  hashMessages: vi.fn().mockReturnValue('mockhash'),
  getCachedResponse: vi.fn().mockReturnValue(null),
  setCachedResponse: vi.fn(),
  clearResponseCache: vi.fn(),
}));

vi.mock('@/lib/memoryApi', () => ({ memoryApi: { getRelevant: vi.fn().mockResolvedValue([]) } }));

vi.mock('@/hooks/useAssistants', () => ({
  useAssistants: () => ({ assistants: [], selected: null, selectedSlug: 'general', setSelectedSlug: vi.fn(), loading: false }),
}));

vi.mock('@/components/chat/DesktopSidebar', () => ({
  DesktopSidebar: () => <div data-testid="desktop-sidebar">Sidebar</div>,
  useSidebarCollapsed: () => ({ isCollapsed: false, toggle: vi.fn() }),
}));

vi.mock('@/components/chat/ChatHeader', () => ({ ChatHeader: () => <div data-testid="chat-header">Header</div> }));

vi.mock('@/components/chat/MessageList', () => ({
  MessageList: ({ messages }: { messages: unknown[] }) => (
    <div data-testid="message-list">
      {messages.map((m: any, i: number) => (
        <div key={m.id ?? i}>{m.content}</div>
      ))}
    </div>
  ),
}));

vi.mock('@/components/chat/ChatErrorBanner', () => ({ ChatErrorBanner: () => <div data-testid="chat-error-banner" /> }));
vi.mock('@/components/chat/ChatEmptyState', () => ({ ChatEmptyState: () => <div data-testid="chat-empty-state" /> }));
vi.mock('@/components/chat/ThinkingPills', () => ({
  ThinkingPills: () => <div data-testid="thinking-pills" />,
  mapStatusToLabel: (s: string) => s,
}));
vi.mock('@/components/chat/SlashCommandMenu', () => ({ SlashCommandMenu: () => null }));
vi.mock('@/components/chat/ScrollToBottomFab', () => ({ ScrollToBottomFab: () => null }));
vi.mock('@/components/chat/MobileConversationSheet', () => ({ MobileConversationSheet: () => null }));
vi.mock('@/components/chat/WisdomCardGenerator', () => ({ WisdomCardGenerator: () => null }));
vi.mock('@/components/landing/FloatingParticles', () => ({ FloatingParticles: () => null }));
vi.mock('@/components/chat/DailyTeaching', () => ({ DailyTeaching: () => null }));
vi.mock('@/hooks/useDailyTeaching', () => ({ useDailyTeaching: () => ({ teaching: null, loading: false }) }));
vi.mock('@/hooks/useChatShortcuts', () => ({ useChatShortcuts: vi.fn() }));
vi.mock('@/hooks/useSwipeGesture', () => ({ useSwipeGesture: vi.fn() }));

import { ChatInterface } from '@/components/chat/ChatInterface';

describe('ChatInterface blocked-path gating', () => {
  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    chatMocks.getSession.mockResolvedValue({ data: { session: null } });
    chatMocks.generateSummary.mockResolvedValue('');
    chatMocks.generateConversationTitle.mockResolvedValue('T');
    chatMocks.sendMessageStreaming.mockImplementation(() => ({
      [Symbol.asyncIterator]: async function* () {},
    }));
    vi.clearAllMocks();
    chatMocks.getSession.mockResolvedValue({ data: { session: null } });
  });

  async function sendChat(text: string) {
    render(
      <BrowserRouter>
        <ChatInterface />
      </BrowserRouter>,
    );
    await screen.findByRole('heading', { level: 2, name: /Test/i });
    fireEvent.change(screen.getByLabelText('Your message'), { target: { value: text } });
    fireEvent.click(screen.getByLabelText('Send message'));
  }

  it('generic guardrail block does NOT open the gated modal', async () => {
    chatMocks.sendMessage.mockResolvedValue({
      content: 'Blocked by safety filter.',
      blocked: true,
      blockReason: 'output_guardrail_violence',
      proactiveSereneMind: { triggered: false },
    });
    await sendChat('Tell me about a scripture battle');
    await waitFor(() => expect(chatMocks.sendMessage).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText('Blocked by safety filter.')).toBeInTheDocument());
    expect(chatMocks.openSereneMind).not.toHaveBeenCalledWith('audio', true);
  });

  it('SEVERE distress block opens the gated modal', async () => {
    chatMocks.sendMessage.mockResolvedValue({
      content: 'Support message.',
      blocked: true,
      blockReason: 'output_guardrail',
      proactiveSereneMind: { triggered: true, level: 'SEVERE' },
    });
    await sendChat('I am in deep crisis');
    await waitFor(() => expect(chatMocks.sendMessage).toHaveBeenCalled());
    await waitFor(() =>
      expect(chatMocks.openSereneMind).toHaveBeenCalledWith('audio', true),
    );
  });
});
