import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useVoiceConversation } from '@/hooks/useVoiceConversation';

// Mock useTextToSpeech
vi.mock('@/hooks/useTextToSpeech', () => ({
  useTextToSpeech: () => ({
    speak: vi.fn(),
    stop: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    isSpeaking: false,
    isPaused: false,
    isSupported: true,
    voices: [],
    currentVoice: null,
    currentSentence: null,
    error: null,
  }),
}));

describe('useVoiceConversation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes in idle state with provided defaults', () => {
    const onSendMessage = vi.fn();
    const { result } = renderHook(() =>
      useVoiceConversation({
        onSendMessage,
        language: 'hi',
        speaker: 'ishita',
      }),
    );

    expect(result.current.state).toBe('idle');
    expect(result.current.transcript).toBe('');
    expect(result.current.interimTranscript).toBe('');
    expect(result.current.responseTranscript).toBe('');
    expect(result.current.isMuted).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.audioLevel).toBe(0);
    expect(result.current.currentLanguage).toBe('hi');
    expect(result.current.currentSpeaker).toBe('ishita');
  });

  it('toggles mute correctly', () => {
    const onSendMessage = vi.fn();
    const { result } = renderHook(() =>
      useVoiceConversation({
        onSendMessage,
      }),
    );

    expect(result.current.isMuted).toBe(false);

    act(() => {
      result.current.toggleMute();
    });

    expect(result.current.isMuted).toBe(true);

    act(() => {
      result.current.toggleMute();
    });

    expect(result.current.isMuted).toBe(false);
  });

  it('allows dynamic language and speaker switching', () => {
    const onSendMessage = vi.fn();
    const { result } = renderHook(() =>
      useVoiceConversation({
        onSendMessage,
        language: 'en',
        speaker: 'priya',
      }),
    );

    act(() => {
      result.current.setLanguage('te');
      result.current.setSpeaker('shubh');
    });

    expect(result.current.currentLanguage).toBe('te');
    expect(result.current.currentSpeaker).toBe('shubh');
  });

  it('interruptSpeaking cleanly transitions state to idle if session inactive', () => {
    const onSendMessage = vi.fn();
    const { result } = renderHook(() =>
      useVoiceConversation({
        onSendMessage,
      }),
    );

    act(() => {
      result.current.interruptSpeaking();
    });

    expect(result.current.state).toBe('idle');
  });
});
