import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatComposer } from './ChatComposer';

vi.mock('./LanguageSelector', () => ({
  LanguageSelector: () => <div data-testid="language-selector" />,
}));

vi.mock('./AssistantSwitcher', () => ({
  AssistantSwitcher: () => <div data-testid="assistant-switcher" />,
}));

vi.mock('./SlashCommandMenu', () => ({
  SlashCommandMenu: () => <div data-testid="slash-command-menu" />,
}));

const renderComposer = (overrides: Partial<React.ComponentProps<typeof ChatComposer>> = {}) => {
  const onSubmit = vi.fn();
  const onKeyDown = vi.fn();
  const props: React.ComponentProps<typeof ChatComposer> = {
    inputValue: 'How do I find peace?',
    inputRef: { current: null },
    attachedFiles: [],
    onAddFile: vi.fn(),
    onRemoveFile: vi.fn(),
    onInputChange: vi.fn(),
    onKeyDown,
    onSubmit,
    onStop: vi.fn(),
    isTyping: false,
    isStreaming: false,
    isAwaitingSereneMind: false,
    isQuotaExceeded: false,
    isListening: false,
    isHandsFreeVoice: false,
    currentLanguage: 'en',
    voiceEnabled: false,
    ttsEnabled: false,
    isSpeaking: false,
    inputFocused: false,
    isLandingMode: true,
    onVoiceToggle: vi.fn(),
    onHandsFreeVoiceToggle: vi.fn(),
    onTtsToggle: vi.fn(),
    onLanguageChange: vi.fn(),
    capabilities: {
      sereneMind: false,
      guidedMeditation: false,
      textAttachments: false,
      voiceInput: false,
    },
    onSereneMind: vi.fn(),
    onGuidedMeditation: vi.fn(),
    onFocus: vi.fn(),
    onBlur: vi.fn(),
    onSlashCommand: vi.fn(),
    ...overrides,
  };

  render(<ChatComposer {...props} />);
  return { onKeyDown, onSubmit };
};

describe('ChatComposer keyboard behavior', () => {
  beforeEach(() => {
    vi.spyOn(HTMLFormElement.prototype, 'requestSubmit').mockImplementation(function requestSubmit(this: HTMLFormElement) {
      this.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
  });

  it('leaves plain Enter unhandled for PromptInput submission', async () => {
    const { onKeyDown } = renderComposer();
    const textarea = screen.getByRole('textbox', { name: /your message/i });
    const event = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true });

    await act(async () => {
      fireEvent(textarea, event);
    });

    expect(onKeyDown).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);
  });

  it('keeps Shift+Enter as a newline without submitting', () => {
    const { onSubmit } = renderComposer();

    fireEvent.keyDown(screen.getByRole('textbox', { name: /your message/i }), {
      key: 'Enter',
      code: 'Enter',
      shiftKey: true,
    });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('does not submit Enter while an IME composition is active', () => {
    const { onSubmit } = renderComposer();
    const textarea = screen.getByRole('textbox', { name: /your message/i });

    fireEvent.compositionStart(textarea);
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter', isComposing: true });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('uses the whole visible 44px text region as the textarea target', () => {
    renderComposer();
    const textarea = screen.getByRole('textbox', { name: /your message/i });

    expect(textarea).toHaveClass('min-h-12', 'cursor-text');
    expect(screen.queryByTestId('slash-command-menu')).not.toBeInTheDocument();
    textarea.focus();
    expect(textarea).toHaveFocus();
  });

  it('shows a 2px focus ring at full ojas strength (NEW-A11Y-8, A11Y-15, WCAG 1.4.11)', () => {
    renderComposer();
    const textarea = screen.getByRole('textbox', { name: /your message/i });
    expect(textarea.className).toContain('focus-visible:ring-2');
    expect(textarea.className).toContain('focus-visible:ring-ojas');
    // the old 1px, 30%-opacity ring is under the 3:1 non-text contrast minimum
    expect(textarea.className).not.toContain('focus:ring-ojas/30');
  });

  it('keeps a long draft editable without a separate scroll-control button', () => {
    const longDraft = 'A long draft '.repeat(80);
    renderComposer({ inputValue: longDraft });
    const textarea = screen.getByRole('textbox', { name: /your message/i });

    expect(textarea).toHaveValue(longDraft);
    expect(screen.queryByRole('button', { name: /go to start/i })).not.toBeInTheDocument();
  });

  it('debounces rapid double-submits of identical text to prevent duplicate messages', async () => {
    const { onSubmit } = renderComposer();
    const sendButton = screen.getByRole('button', { name: /send message/i });

    await act(async () => {
      fireEvent.click(sendButton);
      fireEvent.click(sendButton);
    });

    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('permits rapid consecutive submissions when the text is different (queueing follow-ups)', async () => {
    const onSubmit = vi.fn();
    const { rerender } = render(
      <ChatComposer
        inputValue="Question 1"
        inputRef={{ current: null }}
        attachedFiles={[]}
        onAddFile={vi.fn()}
        onRemoveFile={vi.fn()}
        onInputChange={vi.fn()}
        onKeyDown={vi.fn()}
        onSubmit={onSubmit}
        onStop={vi.fn()}
        isTyping={false}
        isStreaming={false}
        isAwaitingSereneMind={false}
        isQuotaExceeded={false}
        isListening={false}
        isHandsFreeVoice={false}
        currentLanguage="en"
        voiceEnabled={false}
        ttsEnabled={false}
        isSpeaking={false}
        inputFocused={false}
        isLandingMode={false}
        onVoiceToggle={vi.fn()}
        onHandsFreeVoiceToggle={vi.fn()}
        onTtsToggle={vi.fn()}
        onLanguageChange={vi.fn()}
        capabilities={{
          sereneMind: false,
          guidedMeditation: false,
          textAttachments: false,
          voiceInput: false,
        }}
        onSereneMind={vi.fn()}
        onGuidedMeditation={vi.fn()}
        onFocus={vi.fn()}
        onBlur={vi.fn()}
        onSlashCommand={vi.fn()}
      />
    );

    const button1 = screen.getByRole('button', { name: /send message/i });
    await act(async () => {
      fireEvent.click(button1);
    });
    expect(onSubmit).toHaveBeenCalledWith(expect.anything(), 'Question 1');

    // Rerender immediately with different text and generation active
    rerender(
      <ChatComposer
        inputValue="Question 2"
        inputRef={{ current: null }}
        attachedFiles={[]}
        onAddFile={vi.fn()}
        onRemoveFile={vi.fn()}
        onInputChange={vi.fn()}
        onKeyDown={vi.fn()}
        onSubmit={onSubmit}
        onStop={vi.fn()}
        isTyping={true}
        isStreaming={true}
        isAwaitingSereneMind={false}
        isQuotaExceeded={false}
        isListening={false}
        isHandsFreeVoice={false}
        currentLanguage="en"
        voiceEnabled={false}
        ttsEnabled={false}
        isSpeaking={false}
        inputFocused={false}
        isLandingMode={false}
        onVoiceToggle={vi.fn()}
        onHandsFreeVoiceToggle={vi.fn()}
        onTtsToggle={vi.fn()}
        onLanguageChange={vi.fn()}
        capabilities={{
          sereneMind: false,
          guidedMeditation: false,
          textAttachments: false,
          voiceInput: false,
        }}
        onSereneMind={vi.fn()}
        onGuidedMeditation={vi.fn()}
        onFocus={vi.fn()}
        onBlur={vi.fn()}
        onSlashCommand={vi.fn()}
      />
    );

    const queueButton = screen.getByRole('button', { name: /queue message/i });
    await act(async () => {
      fireEvent.click(queueButton);
    });

    expect(onSubmit).toHaveBeenCalledTimes(2);
    expect(onSubmit).toHaveBeenLastCalledWith(expect.anything(), 'Question 2');
  });
});
