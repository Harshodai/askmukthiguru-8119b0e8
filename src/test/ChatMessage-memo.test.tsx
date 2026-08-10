import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
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
      t: (key: string, opts?: Record<string, unknown>) => {
        const value = key
          .split('.')
          .reduce((acc: unknown, part: string) => (acc as Record<string, unknown> | null)?.[part], en);
        return (typeof value === 'string' ? value : key).replace(
          /\{\{(\w+)\}\}/g,
          (_, name: string) => String(opts?.[name] ?? `{{${name}}}`),
        );
      },
    }),
  };
});

const mockQueryText = vi.fn();
const mockOnSubmitEdit = vi.fn();
vi.mock('@/components/chat/InlineActions', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/chat/InlineActions')>();
  return {
    ...actual,
    EngagementCard: ({ queryText }: { queryText?: string }) => {
      mockQueryText(queryText);
      return <div data-testid="engagement-card" />;
    },
  };
});

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

/**
 * P1-AI-17 regression tests: the memo comparator previously omitted
 * queryText, onSubmitEdit and onEditUserMessage, so a changed prop never
 * reached the inner component (stale render, stale closures). Each test
 * re-renders with one changed prop and asserts the update lands inside
 * the memoized component.
 */
describe('ChatMessage memo comparator covers all props', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  it('re-renders when queryText changes (previously omitted from comparator)', () => {
    const message = makeGuruMessage();
    const { rerender } = render(<ChatMessage message={message} queryText="question one" isLastGuru />, { wrapper });

    expect(mockQueryText).toHaveBeenLastCalledWith('question one');

    rerender(<ChatMessage message={message} queryText="question two" isLastGuru />);
    expect(mockQueryText).toHaveBeenLastCalledWith('question two');
    expect(mockQueryText).toHaveBeenCalledTimes(2);
  });

  it('re-renders with the latest onSubmitEdit when its identity changes (stale closure guard)', () => {
    const first = vi.fn();
    const second = vi.fn();
    const message = makeGuruMessage({ role: 'user', content: 'hello' });

    const { rerender } = render(<ChatMessage message={message} onSubmitEdit={first} />, { wrapper });
    rerender(<ChatMessage message={message} onSubmitEdit={second} />);

    fireEvent.click(screen.getByTitle('Edit & resend'));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'hello edited' } });
    fireEvent.click(screen.getByRole('button', { name: /Save & resend/i }));

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledWith('msg-1', 'hello edited');
  });
});
