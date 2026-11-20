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

describe('useTextToSpeech races and errors', () => {
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


  // 2026-11-19: a TTS request still in flight (a Railway cold start can take 25-40 s)
  // must not start playing after the seeker pressed stop or asked for another answer.
  function deferredFetch() {
    let resolve!: (v: unknown) => void;
    let capturedSignal: AbortSignal | undefined;
    const p = new Promise((r) => (resolve = r));
    (fetch as unknown as ReturnType<typeof vi.fn>).mockImplementationOnce((_url: string, init?: RequestInit) => {
      capturedSignal = init?.signal as AbortSignal | undefined;
      return p;
    });
    return {
      resolve: (audio: string) => resolve({ ok: true, json: () => Promise.resolve({ audio, format: 'mp3' }) }),
      get signal() {
        return capturedSignal;
      },
    };
  }

  function trackAudio() {
    const played: string[] = [];
    vi.stubGlobal('Audio', vi.fn(function AudioMock(this: Record<string, unknown>, src: string) {
      this.src = src;
      this.play = vi.fn(() => { played.push(src); return Promise.resolve(); });
      this.pause = vi.fn();
      this.addEventListener = vi.fn();
      this.removeEventListener = vi.fn();
    }));
    return played;
  }

  it('does not play a pending answer after stop()', async () => {
    const played = trackAudio();
    const deferred = deferredFetch();
    const { result } = renderHook(() => useTextToSpeech());
    let pending!: Promise<void>;
    act(() => { pending = Promise.resolve(result.current.speak('first answer')); });
    await act(async () => { await Promise.resolve(); });
    expect(deferred.signal).toBeDefined();
    expect(deferred.signal?.aborted).toBe(false);
    act(() => result.current.stop());
    expect(deferred.signal?.aborted).toBe(true);
    await act(async () => { deferred.resolve('AAAA'); await pending; });
    expect(played).toEqual([]);
    expect(result.current.isSpeaking).toBe(false);
  });

  it('a newer speak() supersedes a pending older one', async () => {
    const played = trackAudio();
    const finishOld = deferredFetch();
    const finishNew = deferredFetch();
    const { result } = renderHook(() => useTextToSpeech());
    let oldP!: Promise<void>;
    let newP!: Promise<void>;
    act(() => { oldP = Promise.resolve(result.current.speak('old')); });
    await act(async () => { await Promise.resolve(); });
    expect(finishOld.signal?.aborted).toBe(false);
    act(() => { newP = Promise.resolve(result.current.speak('new')); });
    await act(async () => { await Promise.resolve(); });
    expect(finishOld.signal?.aborted).toBe(true);
    expect(finishNew.signal?.aborted).toBe(false);
    await act(async () => { finishNew.resolve('NEW'); await newP; });
    await act(async () => { finishOld.resolve('OLD'); await oldP; });
    expect(played).toEqual(['data:audio/mp3;base64,NEW']);
  });

  it('reports a native speech error to onError (not only the console)', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('down'));
    const onError = vi.fn();
    const { result } = renderHook(() => useTextToSpeech({ onError }));
    await act(async () => { await result.current.speak('hello'); });
    const utterance = (global.SpeechSynthesisUtterance as unknown as ReturnType<typeof vi.fn>).mock.results[0].value;
    act(() => utterance.onerror({ error: 'synthesis-failed' }));
    expect(onError).toHaveBeenCalledTimes(1);
    act(() => utterance.onerror({ error: 'interrupted' }));  // a user stop is not an error
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('does not play a pending answer after the component unmounts', async () => {
    const played = trackAudio();
    const deferred = deferredFetch();
    const { result, unmount } = renderHook(() => useTextToSpeech());
    let pending!: Promise<void>;
    act(() => { pending = Promise.resolve(result.current.speak('answer')); });
    await act(async () => { await Promise.resolve(); });
    expect(deferred.signal?.aborted).toBe(false);
    unmount();
    expect(deferred.signal?.aborted).toBe(true);
    await act(async () => { deferred.resolve('LATE'); await pending; });
    expect(played).toEqual([]);
  });
});
