import { describe, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ChatInterface } from '@/components/chat/ChatInterface';

// Mock heavy dependencies so the chat input renders in isolation.
vi.mock('@/components/chat/MessageList', () => ({
  MessageList: () => <div data-testid="message-list" />,
}));

vi.mock('@/lib/aiService', () => ({
  getAIConfig: () => ({ endpoint: 'http://localhost/api/chat', mode: 'custom' }),
  streamChat: () => ({ [Symbol.asyncIterator]: () => ({ next: () => Promise.resolve({ done: true, value: undefined }) }) }),
  setLanguage: vi.fn(),
}));

vi.mock('@/lib/i18n', () => ({
  default: { changeLanguage: vi.fn() },
}));

vi.mock('@/components/common/SereneMindProvider', () => ({
  useSereneMind: () => ({ open: vi.fn(), setOnComplete: vi.fn() }),
  SereneMindProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/hooks/useVisitContext', () => ({
  useVisitContext: () => ({ greetingContext: 'first_visit', totalVisits: 0, isFirstVisit: true }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: 'thirdParty' as const },
}));

const renderWithRouter = (ui: React.ReactElement) => render(ui, { wrapper: MemoryRouter });

describe('ChatInterface IME composition guard', () => {
  it('does not send on Enter while composing', async () => {
    renderWithRouter(<ChatInterface />);
    const textarea = screen.getByLabelText(/your message/i) as HTMLTextAreaElement;

    fireEvent.compositionStart(textarea);
    fireEvent.change(textarea, { target: { value: 'namaste' } });
    await waitFor(() => expect(textarea).toHaveValue('namaste'));

    fireEvent.keyDown(textarea, {
      key: 'Enter',
      nativeEvent: { isComposing: true },
    });

    await waitFor(() => expect(textarea).toHaveValue('namaste'));
  });

  it('does not send on Enter when keyCode is 229', async () => {
    renderWithRouter(<ChatInterface />);
    const textarea = screen.getByLabelText(/your message/i) as HTMLTextAreaElement;

    fireEvent.compositionStart(textarea);
    fireEvent.change(textarea, { target: { value: 'hello' } });
    await waitFor(() => expect(textarea).toHaveValue('hello'));

    fireEvent.keyDown(textarea, {
      key: 'Enter',
      nativeEvent: { isComposing: false, keyCode: 229 },
    });

    await waitFor(() => expect(textarea).toHaveValue('hello'));
  });
});
