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

  it('anchors the language menu to the trigger instead of the viewport', () => {
    render(<LanguageSelector value="en" />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    const menu = screen.getByRole('dialog', { name: /select language/i });
    expect(menu.className).toContain('absolute');
    expect(menu.className).toContain('bottom-full');
    expect(menu.className).toContain('left-0');
  });

  it('renders all languages and supports searching by name or script', () => {
    render(<LanguageSelector value="en" />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    expect(screen.getByRole('textbox')).toBeInTheDocument();
    LANGUAGES.forEach((lang) => {
      expect(screen.getByText(lang.name)).toBeInTheDocument();
    });

    // Test search filter
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'telugu' } });
    expect(screen.getByText('Telugu')).toBeInTheDocument();
    expect(screen.queryByText('Hindi')).not.toBeInTheDocument();
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
    expect(screen.getByRole('button', { expanded: false })).toHaveFocus();
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

  it('renders compact mode with Languages icon and short native label', () => {
    render(<LanguageSelector value="hi" compact />);
    expect(screen.getByText('हिन्')).toBeInTheDocument();
  });

  it('renders language options with role="option" and aria-selected state', () => {
    render(<LanguageSelector value="en" />);
    const globeButton = screen.getByRole('button', { expanded: false });
    fireEvent.click(globeButton);

    const options = screen.getAllByRole('option');
    expect(options.length).toBe(LANGUAGES.length);

    const enOption = options.find((opt) => opt.textContent?.includes('English'));
    expect(enOption).toHaveAttribute('aria-selected', 'true');

    const hiOption = options.find((opt) => opt.textContent?.includes('Hindi'));
    expect(hiOption).toHaveAttribute('aria-selected', 'false');
  });
});
