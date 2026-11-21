import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useVoiceConversation } from '@/hooks/useVoiceConversation';

// Mock useTextToSpeech
const mockSpeak = vi.fn();
const mockSpeakSentence = vi.fn();
const mockFinishStream = vi.fn();
const mockStop = vi.fn();

vi.mock('@/hooks/useTextToSpeech', () => ({
  useTextToSpeech: () => ({
    speak: mockSpeak,
    speakSentence: mockSpeakSentence,
    finishStream: mockFinishStream,
    stop: mockStop,
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

  it('handles speakText correctly', () => {
    const onSendMessage = vi.fn();
    const { result } = renderHook(() =>
      useVoiceConversation({
        onSendMessage,
      }),
    );

    act(() => {
      result.current.speakText('The sacred truth.');
    });

    expect(result.current.state).toBe('speaking');
    expect(result.current.responseTranscript).toBe('The sacred truth.');
    expect(mockSpeak).toHaveBeenCalledWith('The sacred truth.');
  });

  it('delegates speakSentence and finishStream to TTS', async () => {
    const onSendMessage = vi.fn();
    const { result } = renderHook(() =>
      useVoiceConversation({
        onSendMessage,
        language: 'en',
      }),
    );

    await act(async () => {
      await result.current.speakSentence('Sentence 1.', false);
    });

    expect(mockSpeakSentence).toHaveBeenCalledWith('Sentence 1.', false, 'en');

    act(() => {
      result.current.finishStream();
    });

    expect(mockFinishStream).toHaveBeenCalledTimes(1);
  });

  it('submits accumulated speech when submitCurrentSpeech is called', async () => {
    const onSendMessage = vi.fn().mockResolvedValue('Response');
    const { result } = renderHook(() =>
      useVoiceConversation({
        onSendMessage,
      }),
    );

    act(() => {
      // Simulate speaking text directly
      result.current.speakText('Greeting');
    });

    expect(result.current.state).toBe('speaking');

    // Calling interruptSpeaking resets speech
    act(() => {
      result.current.interruptSpeaking();
    });

    expect(mockStop).toHaveBeenCalled();
    expect(result.current.state).toBe('idle');
  });
});
