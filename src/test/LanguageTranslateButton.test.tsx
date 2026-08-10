import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LanguageTranslateButton } from '@/components/chat/ChatMessage';
import type { Message } from '@/lib/chatStorage';

const langMock = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({ profile: { preferredLanguage: langMock() } }),
}));

vi.mock('@/lib/aiService', () => ({
  translateText: vi.fn(),
  submitFeedbackToBackend: vi.fn(),
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

const makeMessage = (): Message => ({
  id: 'm-1',
  role: 'guru',
  content: 'Namaste',
  timestamp: new Date(),
});

describe('LanguageTranslateButton (Rules of Hooks)', () => {
  beforeEach(() => {
    langMock.mockReset();
  });

  it('renders a translate button when preferred language is not English', () => {
    langMock.mockReturnValue('hi');
    render(<LanguageTranslateButton message={makeMessage()} />);
    expect(screen.getByTitle('Translate to hi')).toBeInTheDocument();
  });

  it('does not crash when language changes from non-English to English', () => {
    langMock.mockReturnValue('hi');
    const { rerender } = render(<LanguageTranslateButton message={makeMessage()} />);
    expect(screen.getByTitle('Translate to hi')).toBeInTheDocument();

    // Flip to English — the component must not throw "Rendered fewer hooks
    // than expected" and must stay mounted (as an empty fragment).
    langMock.mockReturnValue('en');
    rerender(<LanguageTranslateButton message={makeMessage()} />);

    expect(screen.queryByTitle('Translate to hi')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Show original')).not.toBeInTheDocument();
  });
});
