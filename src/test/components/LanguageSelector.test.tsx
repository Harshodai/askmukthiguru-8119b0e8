import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LanguageSelector } from '@/components/chat/LanguageSelector';

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

  it('filters languages by search input', () => {
    render(<LanguageSelector value="en" />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    const searchInput = screen.getByPlaceholderText(/Search 23 languages/i);
    fireEvent.change(searchInput, { target: { value: 'telugu' } });

    expect(screen.getByText('Telugu')).toBeInTheDocument();
    expect(screen.queryByText('Hindi')).not.toBeInTheDocument();
  });

  it('calls onLanguageChange and setLanguage when a language is selected', () => {
    const onLanguageChange = vi.fn();
    render(<LanguageSelector value="en" onLanguageChange={onLanguageChange} />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    fireEvent.click(screen.getByText('हिन्दी'));
    expect(setLanguageMock).toHaveBeenCalledWith('hi');
    expect(onLanguageChange).toHaveBeenCalledWith('hi');
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ title: expect.stringContaining('Language Changed') }),
    );
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
