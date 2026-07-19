import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LanguageSelector, LANGUAGES } from '@/components/chat/LanguageSelector';

const setLanguageMock = vi.fn();
const toastMock = vi.fn();

vi.mock('@/lib/aiService', () => ({
  setLanguage: (code: string) => setLanguageMock(code),
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

describe('LanguageSelector (regression)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'speechSynthesis', {
      writable: true,
      value: {
        getVoices: vi.fn(() => []),
        onvoiceschanged: null,
      },
    });
  });

  it('renders the selected language native name', () => {
    render(<LanguageSelector value="hi" />);
    expect(screen.getByText('हिन्दी')).toBeInTheDocument();
  });

  it('opens language dropdown when globe button is clicked', () => {
    render(<LanguageSelector value="en" />);
    const globeButton = screen.getByRole('button', { expanded: false });
    fireEvent.click(globeButton);

    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByText('English (India)')).toBeInTheDocument();
    expect(screen.getByText('Hindi')).toBeInTheDocument();
  });

  it('renders all languages as a flat list with no search input', () => {
    render(<LanguageSelector value="en" />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    // Search box was removed — 7 languages is short enough for a flat list
    // (matches Claude.ai/ChatGPT's <10-item picker pattern). Assert every
    // supported language renders, not just two of them, so a future filter
    // regression (e.g. dropping a language from LANGUAGES) is caught here.
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    LANGUAGES.forEach((lang) => {
      expect(screen.getByText(lang.name)).toBeInTheDocument();
    });
  });

  it('calls onLanguageChange and setLanguage when a language is selected, without a toast', () => {
    const onLanguageChange = vi.fn();
    render(<LanguageSelector value="en" onLanguageChange={onLanguageChange} />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    fireEvent.click(screen.getByText('हिन्दी'));
    expect(setLanguageMock).toHaveBeenCalledWith('hi');
    expect(onLanguageChange).toHaveBeenCalledWith('hi');
    // The parent (ChatInterface) owns the confirmation toast now — showing
    // one here too was a double-toast on every language switch.
    expect(toastMock).not.toHaveBeenCalled();
  });

  it('toggles voice mode when microphone button is clicked', () => {
    const onVoiceToggle = vi.fn();
    render(<LanguageSelector value="en" voiceEnabled={false} onVoiceToggle={onVoiceToggle} />);

    const voiceButton = screen.getByLabelText('Start voice input');
    fireEvent.click(voiceButton);
    expect(onVoiceToggle).toHaveBeenCalled();
  });

  it('toggles TTS when volume button is clicked', () => {
    const onTtsToggle = vi.fn();
    render(<LanguageSelector value="en" ttsEnabled={false} onTtsToggle={onTtsToggle} />);

    const ttsButton = screen.getByLabelText('Enable voice output');
    fireEvent.click(ttsButton);
    expect(onTtsToggle).toHaveBeenCalled();
  });

  it('shows listening animation when isListening is true', () => {
    render(<LanguageSelector value="en" voiceEnabled isListening />);
    expect(screen.getByLabelText('Stop recording')).toBeInTheDocument();
  });

  it('shows speaking animation when isSpeaking is true', () => {
    render(<LanguageSelector value="en" ttsEnabled isSpeaking onTtsToggle={vi.fn()} />);
    expect(screen.getByLabelText('Disable voice output')).toBeInTheDocument();
  });
});
