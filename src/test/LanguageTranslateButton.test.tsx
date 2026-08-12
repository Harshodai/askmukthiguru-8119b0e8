import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LanguageTranslateButton } from '@/components/chat/ChatMessage';
import type { Message } from '@/lib/chatStorage';
import { translateText } from '@/lib/aiService';

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

describe('LanguageTranslateButton', () => {
  beforeEach(() => {
    langMock.mockReset();
    vi.mocked(translateText).mockReset();
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

    langMock.mockReturnValue('en');
    rerender(<LanguageTranslateButton message={makeMessage()} />);
    expect(screen.queryByTitle('Translate to hi')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Show original')).not.toBeInTheDocument();
  });

  it('translates from the answer language to the preferred target language', async () => {
    langMock.mockReturnValue('hi');
    vi.mocked(translateText).mockResolvedValue('नमस्ते');
    render(<LanguageTranslateButton message={makeMessage()} />);

    fireEvent.click(screen.getByTitle('Translate to hi'));

    await waitFor(() => {
      expect(translateText).toHaveBeenCalledWith('Namaste', 'hi-IN', 'en-IN');
    });
  });
});
