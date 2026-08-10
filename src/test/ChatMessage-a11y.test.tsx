import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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

describe('ChatMessage action buttons — a11y', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('guru action toolbar reveals on keyboard focus (md:group-focus-within)', () => {
    render(<ChatMessage message={makeGuruMessage()} isLastGuru />, { wrapper });

    const copyButton = screen.getByTitle('Copy response');
    const toolbar = copyButton.closest('div') as HTMLElement;

    expect(toolbar.classList.contains('md:group-focus-within:opacity-100')).toBe(true);
    // Hover reveal is preserved for mouse users
    expect(toolbar.classList.contains('md:group-hover:opacity-100')).toBe(true);
  });

  it('guru action toolbar is always visible on touch/small screens (max-md)', () => {
    render(<ChatMessage message={makeGuruMessage()} isLastGuru />, { wrapper });

    const copyButton = screen.getByTitle('Copy response');
    const toolbar = copyButton.closest('div') as HTMLElement;

    expect(toolbar.classList.contains('max-md:opacity-100')).toBe(true);
  });

  it('user action toolbar reveals on focus and stays visible on small screens', () => {
    render(<ChatMessage message={makeUserMessage()} />, { wrapper });

    const copyButton = screen.getByTitle('Copy question');
    const toolbar = copyButton.closest('div') as HTMLElement;

    expect(toolbar.classList.contains('md:group-focus-within:opacity-100')).toBe(true);
    expect(toolbar.classList.contains('max-md:opacity-100')).toBe(true);
  });
});
