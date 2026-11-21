import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VoiceModeModal } from '@/components/chat/VoiceModeModal';

describe('VoiceModeModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    state: 'listening' as const,
    transcript: '',
    interimTranscript: '',
    responseTranscript: '',
    audioLevel: 0.3,
    isMuted: false,
    isSpeaking: false,
    error: null,
    currentLanguage: 'en',
    currentSpeaker: 'priya',
    onToggleMute: vi.fn(),
    onInterrupt: vi.fn(),
    onSubmitSpeech: vi.fn(),
    onLanguageChange: vi.fn(),
    onSpeakerChange: vi.fn(),
    onRetry: vi.fn(),
  };

  it('renders modal with title, status, and voice orb when open', () => {
    render(<VoiceModeModal {...defaultProps} />);

    expect(screen.getByTestId('voice-mode-modal')).toBeDefined();
    expect(screen.getByTestId('voice-orb-container')).toBeDefined();
    expect(screen.getByTestId('voice-mute-toggle-button')).toBeDefined();
    expect(screen.getByTestId('voice-language-selector')).toBeDefined();
    expect(screen.getByTestId('voice-speaker-selector')).toBeDefined();
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(<VoiceModeModal {...defaultProps} onClose={onClose} />);

    const closeBtn = screen.getByTestId('voice-mode-close-button');
    fireEvent.click(closeBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onToggleMute when mic button is clicked', () => {
    const onToggleMute = vi.fn();
    render(<VoiceModeModal {...defaultProps} onToggleMute={onToggleMute} />);

    const muteBtn = screen.getByTestId('voice-mute-toggle-button');
    fireEvent.click(muteBtn);

    expect(onToggleMute).toHaveBeenCalledTimes(1);
  });

  it('displays seeker transcript and guru response when present', () => {
    render(
      <VoiceModeModal
        {...defaultProps}
        state="speaking"
        transcript="How do I overcome anxiety?"
        responseTranscript="Anxiety arises when the mind is caught in self-centric thinking."
      />,
    );

    expect(screen.getByTestId('voice-seeker-transcript')).toBeDefined();
    expect(screen.getByText(/"How do I overcome anxiety\?"/)).toBeDefined();
    expect(screen.getByTestId('voice-guru-response')).toBeDefined();
    expect(screen.getByText(/Anxiety arises when the mind is caught/)).toBeDefined();
  });

  it('displays interrupt button when Guru is speaking', () => {
    const onInterrupt = vi.fn();
    render(
      <VoiceModeModal
        {...defaultProps}
        state="speaking"
        isSpeaking={true}
        onInterrupt={onInterrupt}
      />,
    );

    const interruptBtn = screen.getByTestId('voice-interrupt-button');
    expect(interruptBtn).toBeDefined();

    fireEvent.click(interruptBtn);
    expect(onInterrupt).toHaveBeenCalledTimes(1);
  });

  it('highlights currentSentence within the Guru response transcript when speaking', () => {
    render(
      <VoiceModeModal
        {...defaultProps}
        state="speaking"
        isSpeaking={true}
        responseTranscript="Peace begins within yourself. When you observe without judgment, clarity emerges."
        currentSentence="When you observe without judgment, clarity emerges."
      />,
    );

    const highlighted = screen.getByText('When you observe without judgment, clarity emerges.');
    expect(highlighted).toBeDefined();
    expect(highlighted.className).toContain('bg-amber-400/20');
  });
});
