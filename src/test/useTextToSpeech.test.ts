import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { StrictMode, createElement } from 'react';
import { useTextToSpeech } from '@/hooks/useTextToSpeech';

// Mock SpeechSynthesis
const mockSpeak = vi.fn();
const mockCancel = vi.fn();
const mockPause = vi.fn();
const mockResume = vi.fn();
const mockGetVoices = vi.fn();
const mockAddVoicesListener = vi.fn();
const mockRemoveVoicesListener = vi.fn();

let mockSpeaking = false;

describe('useTextToSpeech', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSpeaking = false;

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
        addEventListener: mockAddVoicesListener,
        removeEventListener: mockRemoveVoicesListener,
        get speaking() {
          return mockSpeaking;
        },
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

  it('should cancel its own speech on unmount only when it owns a speaking utterance', () => {
    const { result, unmount } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak('Hello world');
    });

    mockSpeaking = true;
    const cancelCallsBeforeUnmount = mockCancel.mock.calls.length;

    unmount();

    expect(mockCancel.mock.calls.length).toBe(cancelCallsBeforeUnmount + 1);
  });

  it('should not cancel global speech on unmount when this instance never started an utterance', () => {
    const { unmount } = renderHook(() => useTextToSpeech());

    mockSpeaking = true;
    unmount();

    expect(mockCancel).not.toHaveBeenCalled();
  });

  it('should register and remove the voiceschanged listener on mount and unmount', () => {
    const { unmount } = renderHook(() => useTextToSpeech());

    expect(mockAddVoicesListener).toHaveBeenCalledWith('voiceschanged', expect.any(Function));
    expect(mockRemoveVoicesListener).not.toHaveBeenCalled();

    unmount();

    expect(mockRemoveVoicesListener).toHaveBeenCalledWith('voiceschanged', expect.any(Function));
  });

  it('should reload voices when the voiceschanged event fires', () => {
    renderHook(() => useTextToSpeech());

    const handler = mockAddVoicesListener.mock.calls.find(
      ([type]) => type === 'voiceschanged'
    )?.[1] as (() => void) | undefined;
    expect(handler).toBeDefined();

    const getVoicesCallsBeforeEvent = mockGetVoices.mock.calls.length;
    act(() => {
      (handler as () => void)();
    });

    expect(mockGetVoices.mock.calls.length).toBe(getVoicesCallsBeforeEvent + 1);
  });

  it('should be double-cleanup safe under StrictMode remounting', () => {
    renderHook(() => useTextToSpeech(), {
      wrapper: ({ children }) => createElement(StrictMode, null, children),
    });

    // StrictMode dev runs effects as setup -> cleanup -> setup.
    expect(mockAddVoicesListener).toHaveBeenCalledTimes(2);
    expect(mockRemoveVoicesListener).toHaveBeenCalledTimes(1);
  });

  it('should tolerate double unmount without error', () => {
    const { result, unmount } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak('Hello world');
    });
    mockSpeaking = true;
    const cancelCallsBeforeUnmount = mockCancel.mock.calls.length;

    unmount();
    unmount();

    expect(mockCancel.mock.calls.length).toBe(cancelCallsBeforeUnmount + 1);
    expect(mockRemoveVoicesListener).toHaveBeenCalled();
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
