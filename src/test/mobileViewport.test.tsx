import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { MobileConversationSheet } from '@/components/chat/MobileConversationSheet';
import { DesktopSidebar } from '@/components/chat/DesktopSidebar';
import { ChatComposer } from '@/components/chat/ChatComposer';
import { SereneMindModal } from '@/components/chat/SereneMindModal';

vi.mock('framer-motion', async () => {
  const React = await import('react');
  const strip = (props: Record<string, unknown>) => {
    const {
      initial: _i,
      animate: _a,
      exit: _e,
      transition: _t,
      whileHover: _wh,
      whileTap: _wt,
      variants: _v,
      layout: _l,
      layoutId: _li,
      drag: _d,
      dragConstraints: _dc,
      onAnimationComplete: _o,
      ...rest
    } = props;
    return rest;
  };
  const make = (tag: string) =>
    React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>((props, ref) =>
      React.createElement(tag, { ...strip(props as Record<string, unknown>), ref }),
    );
  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: new Proxy({}, { get: (_t, tag: string) => make(tag) }),
  };
});

vi.mock('@/assets/gurus-photo.jpg', () => ({ default: '/test-photo.jpg' }));

vi.mock('@/lib/chatStorage', () => ({
  loadConversations: vi.fn(async () => []),
  deleteConversation: vi.fn(),
  renameConversation: vi.fn(),
  formatRelativeTime: vi.fn(() => 'Today'),
}));

vi.mock('@/lib/memoryApi', () => ({
  memoryApi: { list: vi.fn(async () => ({ total: 0, items: [] })) },
}));

vi.mock('@/hooks/useBreathTeaching', () => ({
  useBreathTeaching: () => ({ teaching: null, loading: false, error: false }),
}));

vi.mock('@/lib/audio/hapticAudio', () => ({
  hapticAudio: { playDispatchChime: vi.fn() },
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

vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));

vi.mock('@/lib/aiService', () => ({ setLanguage: vi.fn() }));

const MOBILE_WIDTH = 375;

function setMobileViewport(width = MOBILE_WIDTH, height = 667) {
  Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: width });
  Object.defineProperty(window, 'innerHeight', { writable: true, configurable: true, value: height });
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes('max-width') ? width < 768 : width >= 768,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
  window.dispatchEvent(new Event('resize'));
}

function assertNoHorizontalOverflow(container: HTMLElement, viewport = MOBILE_WIDTH) {
  const offenders = Array.from(container.querySelectorAll('*')).filter(
    (el) => (el as HTMLElement).scrollWidth > viewport,
  );
  expect(offenders).toEqual([]);
}

const routerWrapper = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>
    <TooltipProvider>{children}</TooltipProvider>
  </BrowserRouter>
);

beforeEach(() => {
  vi.clearAllMocks();
  setMobileViewport();
});

describe('mobile viewport (375px): MobileConversationSheet', () => {
  it('fits viewport with close + new-conversation reachable', () => {
    const onClose = vi.fn();
    const { container } = render(
      <MobileConversationSheet
        isOpen
        onClose={onClose}
        onNewConversation={vi.fn()}
        onOpenSereneMind={vi.fn()}
      />,
      { wrapper: routerWrapper },
    );

    expect(window.innerWidth).toBe(375);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog.className).toContain('min(88vw');

    const closeBtn = screen.getByLabelText('Close menu');
    expect(closeBtn).toBeVisible();
    expect(closeBtn).toBeEnabled();
    expect(closeBtn.className).toContain('min-h-[44px]');

    expect(screen.getByRole('textbox', { name: /search conversations/i })).toBeInTheDocument();
    expect(screen.getByText(/new conversation/i)).toBeInTheDocument();

    assertNoHorizontalOverflow(container);
  });
});

describe('mobile viewport (375px): DesktopSidebar fallback', () => {
  it('stays hidden on mobile while toggle remains reachable', () => {
    const { container } = render(
      <DesktopSidebar
        isCollapsed={false}
        onToggleCollapse={vi.fn()}
        onNewConversation={vi.fn()}
        onOpenSereneMind={vi.fn()}
      />,
      { wrapper: routerWrapper },
    );

    const aside = container.querySelector('#sidebar-panel');
    expect(aside).not.toBeNull();
    expect(aside!.className).toContain('hidden');
    expect(aside!.className).toContain('sm:flex');

    expect(screen.getByTestId('sidebar-toggle')).toBeEnabled();

    assertNoHorizontalOverflow(container);
  });
});

describe('mobile viewport (375px): ChatComposer', () => {
  const inputRef = { current: null } as React.RefObject<HTMLTextAreaElement | null>;
  const baseProps = {
    inputRef,
    attachedFiles: [],
    onAddFile: vi.fn(),
    onRemoveFile: vi.fn(),
    onInputChange: vi.fn(),
    onKeyDown: vi.fn(),
    onSubmit: vi.fn(),
    onStop: vi.fn(),
    isTyping: false,
    isStreaming: false,
    isAwaitingSereneMind: false,
    isListening: false,
    currentLanguage: 'en',
    voiceEnabled: true,
    ttsEnabled: false,
    isSpeaking: false,
    inputFocused: false,
    showPipeline: false,
    pipelineSteps: [],
    pipelineHeartbeat: false,
    showInstantPill: false,
    isLandingMode: false,
    onVoiceToggle: vi.fn(),
    onTtsToggle: vi.fn(),
    onLanguageChange: vi.fn(),
    onSereneMind: vi.fn(),
    onGuidedMeditation: vi.fn(),
    onFocus: vi.fn(),
    onBlur: vi.fn(),
    onSlashCommand: vi.fn(),
  };

  it('fits viewport with send + voice actions tappable', () => {
    const { container } = render(<ChatComposer {...baseProps} inputValue="hello at 375px" />, {
      wrapper: routerWrapper,
    });

    const input = screen.getByRole('textbox');
    expect(input).toBeVisible();
    expect(input).toBeEnabled();

    const sendBtn = container.querySelector('button[type="submit"]');
    expect(sendBtn).not.toBeNull();
    expect(sendBtn!).toBeVisible();
    expect(sendBtn!).toBeEnabled();
    expect(sendBtn!.className).toContain('min-h-[44px]');

    const voiceBtn = screen.getByTestId('start-voice-input-button');
    expect(voiceBtn).toBeVisible();
    expect(voiceBtn).toBeEnabled();
    expect(voiceBtn.className).toContain('min-h-[44px]');

    const toolbarButtons = container.querySelectorAll('button');
    expect(toolbarButtons.length).toBeGreaterThanOrEqual(3);

    assertNoHorizontalOverflow(container);
  });
});

describe('mobile viewport (375px): SereneMindModal', () => {
  it('fits viewport with close + start reachable on audio tab', () => {
    const { container } = render(<SereneMindModal isOpen onClose={vi.fn()} initialTab="audio" />, {
      wrapper: routerWrapper,
    });

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();

    const card = container.querySelector('.glass-card');
    expect(card).not.toBeNull();
    expect(card!.className).toContain('max-h-[90vh]');
    expect(card!.className).toContain('overflow-y-auto');

    const closeBtn = screen.getByLabelText('Close');
    expect(closeBtn).toBeVisible();
    expect(closeBtn).toBeEnabled();

    const controls = container.querySelector('.flex.justify-center.gap-4');
    expect(controls).not.toBeNull();
    const startBtn = Array.from(controls!.querySelectorAll('button')).find(
      (b) => !(b as HTMLButtonElement).disabled,
    );
    expect(startBtn).not.toBeUndefined();
    expect(startBtn!).toBeVisible();
    expect(startBtn!).toBeEnabled();

    expect(screen.getByRole('tablist')).toBeInTheDocument();

    assertNoHorizontalOverflow(container);
  });

  it('fits viewport with video tab controls reachable', () => {
    const { container } = render(<SereneMindModal isOpen onClose={vi.fn()} initialTab="video" />, {
      wrapper: routerWrapper,
    });

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Close')).toBeEnabled();
    expect(screen.getByText(/continue chatting/i)).toBeVisible();

    assertNoHorizontalOverflow(container);
  });
});
