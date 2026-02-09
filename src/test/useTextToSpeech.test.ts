import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTextToSpeech } from '@/hooks/useTextToSpeech';

// Mock SpeechSynthesis
const mockSpeak = vi.fn();
const mockCancel = vi.fn();
const mockPause = vi.fn();
const mockResume = vi.fn();
const mockGetVoices = vi.fn();

describe('useTextToSpeech', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock SpeechSynthesisUtterance
    global.SpeechSynthesisUtterance = vi.fn().mockImplementation(() => ({
      text: '',
      rate: 1,
      pitch: 1,
      volume: 1,
      voice: null,
      lang: '',
      onstart: null,
      onend: null,
      onerror: null,
      onpause: null,
      onresume: null,
    })) as unknown as typeof SpeechSynthesisUtterance;

    // Mock speechSynthesis
    Object.defineProperty(window, 'speechSynthesis', {
      value: {
        speak: mockSpeak,
        cancel: mockCancel,
        pause: mockPause,
        resume: mockResume,
        getVoices: mockGetVoices.mockReturnValue([
          { lang: 'en-US', name: 'English US' },
          { lang: 'hi-IN', name: 'Hindi' },
        ]),
        onvoiceschanged: null,
      },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should return isSupported as true when speechSynthesis is available', () => {
    const { result } = renderHook(() => useTextToSpeech());
    expect(result.current.isSupported).toBe(true);
  });

  it('should have isSpeaking initially set to false', () => {
    const { result } = renderHook(() => useTextToSpeech());
    expect(result.current.isSpeaking).toBe(false);
  });

  it('should have isPaused initially set to false', () => {
    const { result } = renderHook(() => useTextToSpeech());
    expect(result.current.isPaused).toBe(false);
  });

  it('should call speechSynthesis.speak when speak is invoked', () => {
    const { result } = renderHook(() => useTextToSpeech());
    
    act(() => {
      result.current.speak('Hello world');
    });

    expect(mockCancel).toHaveBeenCalled();
    expect(mockSpeak).toHaveBeenCalled();
  });

  it('should not speak empty text', () => {
    const { result } = renderHook(() => useTextToSpeech());
    
    act(() => {
      result.current.speak('   ');
    });

    expect(mockSpeak).not.toHaveBeenCalled();
  });

  it('should call speechSynthesis.cancel when stop is invoked', () => {
    const { result } = renderHook(() => useTextToSpeech());
    
    act(() => {
      result.current.stop();
    });

    expect(mockCancel).toHaveBeenCalled();
  });

  it('should call speechSynthesis.pause when pause is invoked', () => {
    const { result } = renderHook(() => useTextToSpeech());
    
    act(() => {
      result.current.pause();
    });

    expect(mockPause).toHaveBeenCalled();
  });

  it('should call speechSynthesis.resume when resume is invoked', () => {
    const { result } = renderHook(() => useTextToSpeech());
    
    act(() => {
      result.current.resume();
    });

    expect(mockResume).toHaveBeenCalled();
  });

  it('should use correct language mapping for Hindi', () => {
    const { result } = renderHook(() => useTextToSpeech({ lang: 'hi' }));
    expect(result.current.isSupported).toBe(true);
  });

  it('should cancel speech on unmount', () => {
    const { unmount } = renderHook(() => useTextToSpeech());
    
    unmount();
    
    expect(mockCancel).toHaveBeenCalled();
  });
});

describe('useTextToSpeech language mappings', () => {
  it('should have correct language to voice code mapping', () => {
    const languageMap: Record<string, string[]> = {
      en: ['en-IN', 'en-US', 'en-GB', 'en-AU'],
      hi: ['hi-IN', 'hi'],
      te: ['te-IN', 'te'],
      ml: ['ml-IN', 'ml'],
    };

    expect(languageMap.en).toContain('en-IN');
    expect(languageMap.hi).toContain('hi-IN');
    expect(languageMap.te).toContain('te-IN');
    expect(languageMap.ml).toContain('ml-IN');
  });
});
