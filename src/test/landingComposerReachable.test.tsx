import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ChatInterface } from '@/components/chat/ChatInterface';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  sendMessage: vi.fn(),
  sendMessageStreaming: vi.fn(),
  generateConversationTitle: vi.fn(),
  setLanguage: vi.fn(),
  openSereneMind: vi.fn(),
  setSereneMindOnComplete: vi.fn(),
  changeUiLanguage: vi.fn().mockResolvedValue(undefined),
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

vi.mock('@/i18n', () => ({
  changeUiLanguage: mocks.changeUiLanguage,
}));

vi.mock('@/lib/aiService', () => ({
  sendMessage: mocks.sendMessage,
  sendMessageStreaming: mocks.sendMessageStreaming,
  generateConversationTitle: mocks.generateConversationTitle,
  setLanguage: mocks.setLanguage,
  queueMemoryExtraction: vi.fn(),
}));

vi.mock('@/lib/chatStorage', () => ({
  generateId: () => 'test-msg-id',
  saveConversation: vi.fn(async () => {}),
  loadConversation: vi.fn(async () => null),
  loadConversations: vi.fn(async () => []),
  createNewConversation: vi.fn().mockReturnValue({
    id: 'test-conv-id',
    messages: [],
    updatedAt: new Date(),
    preview: '',
  }),
  getConversationPreview: vi.fn().mockReturnValue('preview'),
  getCurrentConversationId: vi.fn(async () => null),
  setCurrentConversationId: vi.fn(async () => {}),
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
  useDailyTeaching: () => ({ teaching: { id: 't1', image_url: '', caption: 'Be in a beautiful state.' }, loading: false }),
}));

vi.mock('@/hooks/useChatShortcuts', () => ({
  useChatShortcuts: vi.fn(),
}));

vi.mock('@/hooks/useSwipeGesture', () => ({
  useSwipeGesture: vi.fn(),
}));


/**
 * Landing banners must never take the chat prompt away (2026-11-19).
 * b80722cd removed an auto-opening mood modal that stacked over the welcome notice and
 * hid the composer. The daily-teaching banner's dismiss relied on an unrelated re-render
 * counter and had a ~20 px tap target. Pinned at phone and desktop widths.
 */
function hiddenFromAT(el: HTMLElement): boolean {
  for (let n: HTMLElement | null = el; n; n = n.parentElement) {
    if (n.getAttribute('aria-hidden') === 'true' || n.hasAttribute('inert')) return true;
  }
  return false;
}
const renderChat = () => render(<BrowserRouter><ChatInterface /></BrowserRouter>);
const BANNER = /Be in a beautiful state/;

describe.each([
  ['phone', 375],
  ['desktop', 1280],
])('landing at %s width', (_label, width) => {
  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    mocks.getSession.mockResolvedValue({ data: { session: null } });
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
    window.dispatchEvent(new Event('resize'));
    sessionStorage.clear();
  });

  it('keeps the composer focusable and exposed while the banners show', async () => {
    renderChat();
    expect(await screen.findByText(BANNER)).toBeInTheDocument();
    const composer = (await screen.findByLabelText('Your message')) as HTMLTextAreaElement;
    expect(hiddenFromAT(composer)).toBe(false);
    expect(composer).not.toBeDisabled();
    act(() => composer.focus());
    expect(document.activeElement).toBe(composer);
    expect(document.querySelector('[aria-modal="true"]')).toBeNull();
  });

  it('dismisses the teaching banner with a labelled, >= 24 px control that sticks', async () => {
    const { unmount } = renderChat();
    await screen.findByText(BANNER);
    const dismiss = screen.getByRole('button', { name: 'Dismiss banner' });
    expect(dismiss.className).toMatch(/(^|\s)(h-6|h-7|h-8|h-9|h-10|min-h-11)(\s|$)/);
    fireEvent.click(dismiss);
    await waitFor(() => expect(screen.queryByText(BANNER)).toBeNull());
    unmount();
    renderChat();
    await screen.findByLabelText('Your message');
    expect(screen.queryByText(BANNER)).toBeNull();
  });
});

it('dismiss still works when sessionStorage throws', async () => {
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
  mocks.getSession.mockResolvedValue({ data: { session: null } });
  sessionStorage.clear();
  const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('blocked');
  });
  renderChat();
  await screen.findByText(BANNER);
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss banner' }));
  await waitFor(() => expect(screen.queryByText(BANNER)).toBeNull());
  spy.mockRestore();
});
