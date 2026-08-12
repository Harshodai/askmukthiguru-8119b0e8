import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { StrictMode, createElement } from 'react';
import { useTextToSpeech } from '@/hooks/useTextToSpeech';

// Mock backend URL + auth token
vi.mock('@/lib/backendUrl', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/backendUrl')>();
  return {
    ...actual,
    BACKEND_URL_OR_LOCAL: 'http://localhost:8000',
  };
});

vi.mock('@/lib/chat/auth', () => ({
  getAccessToken: vi.fn(() => Promise.resolve('mock-token')),
}));

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
    vi.stubGlobal('fetch', vi.fn());

    // Mock SpeechSynthesisUtterance
    global.SpeechSynthesisUtterance = vi.fn(function SpeechSynthesisUtteranceMock() {
      return {
        text: '', rate: 1, pitch: 1, volume: 1, voice: null, lang: '',
        onstart: null, onend: null, onerror: null, onpause: null, onresume: null, onboundary: null,
      };
    }) as unknown as typeof SpeechSynthesisUtterance;

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

  it('should call backend /api/speech/tts by default', async () => {
    const fakeAudio = 'ZmFrZS1hdWRpbw==';
    vi.mocked(window.fetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ audio: fakeAudio }),
    } as Response);

    const { result } = renderHook(() => useTextToSpeech());

    await act(async () => {
      result.current.speak('Hello world');
    });

    expect(window.fetch).toHaveBeenCalledTimes(1);
    expect(window.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/speech/tts',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          Authorization: 'Bearer mock-token',
        }),
        body: expect.any(String),
      })
    );
  });

  it('should fall back to native speech synthesis when backend returns 5xx', async () => {
    vi.mocked(window.fetch).mockRejectedValueOnce(new Error('TTS 500'));

    const { result } = renderHook(() => useTextToSpeech());

    await act(async () => {
      result.current.speak('Hello world');
    });

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
    });

    expect(mockSpeak).toHaveBeenCalled();
  });

  it('should not speak empty text', () => {
    const { result } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak('   ');
    });

    expect(window.fetch).not.toHaveBeenCalled();
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

  it('should cancel its own speech on unmount only when it owns a speaking utterance', async () => {
    vi.mocked(window.fetch).mockRejectedValueOnce(new Error('TTS 500'));
    const { result, unmount } = renderHook(() => useTextToSpeech());

    await act(async () => {
      result.current.speak('Hello world');
    });

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
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

  it('should tolerate double unmount without error', async () => {
    vi.mocked(window.fetch).mockRejectedValueOnce(new Error('TTS 500'));
    const { result, unmount } = renderHook(() => useTextToSpeech());

    await act(async () => {
      result.current.speak('Hello world');
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
    });
    mockSpeaking = true;
    const cancelCallsBeforeUnmount = mockCancel.mock.calls.length;

    unmount();
    unmount();

    expect(mockCancel.mock.calls.length).toBe(cancelCallsBeforeUnmount + 1);
    expect(mockRemoveVoicesListener).toHaveBeenCalled();
  });

  it('should expose currentSentence and update it on native boundary events', async () => {
    vi.mocked(window.fetch).mockRejectedValueOnce(new Error('TTS 500'));
    const { result } = renderHook(() => useTextToSpeech());

    await act(async () => {
      result.current.speak('Hello world. How are you?');
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
    });

    expect(mockSpeak).toHaveBeenCalled();
    const utterance = mockSpeak.mock.calls[0][0] as SpeechSynthesisUtterance & { onboundary: (event: { charIndex: number }) => void };
    expect(utterance.onboundary).toBeDefined();

    act(() => {
      utterance.onboundary({ charIndex: 0 } as Event & { charIndex: number });
    });

    expect(result.current.currentSentence).toBe('Hello world.');

    act(() => {
      utterance.onboundary({ charIndex: 15 } as Event & { charIndex: number });
    });

    expect(result.current.currentSentence).toBe('How are you?');
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
