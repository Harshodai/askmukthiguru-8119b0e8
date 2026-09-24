import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

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
  it('submits exactly once when Enter is pressed', () => {
    const { onKeyDown, onSubmit } = renderComposer();

    fireEvent.keyDown(screen.getByRole('textbox', { name: /your message/i }), {
      key: 'Enter',
      code: 'Enter',
    });

    expect(onKeyDown).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledOnce();
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
    fireEvent.click(textarea);
    expect(textarea).toHaveFocus();
  });
});