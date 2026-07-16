import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useMeditationTTS } from '@/components/meditation/useMeditationTTS';
import type { MeditationStep } from '@/components/meditation/meditationSteps';

const mockSpeak = vi.fn();

const steps: MeditationStep[] = [
  { id: 'with-clip', title: 'With Clip', instruction: 'Breathe in.', durationSeconds: 10, audioSrc: '/audio/meditation/with-clip.mp3' },
];

describe('useMeditationTTS fallback for missing/broken clips', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    global.SpeechSynthesisUtterance = vi.fn().mockImplementation((text: string) => ({ text })) as unknown as typeof SpeechSynthesisUtterance;
    Object.defineProperty(window, 'speechSynthesis', {
      value: {
        speak: mockSpeak,
        cancel: vi.fn(),
        pause: vi.fn(),
        resume: vi.fn(),
        getVoices: () => [{ name: 'Samantha', lang: 'en-US' }],
        addEventListener: vi.fn(),
      },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('stays silent while the clip is expected to play (audioFailed=false)', () => {
    renderHook(() => useMeditationTTS(steps, 0, true, false, false));
    vi.advanceTimersByTime(1000);
    expect(mockSpeak).not.toHaveBeenCalled();
  });

  it('speaks the instruction once the clip fails to load (audioFailed=true)', () => {
    renderHook(() => useMeditationTTS(steps, 0, true, false, true));
    vi.advanceTimersByTime(1000);
    expect(mockSpeak).toHaveBeenCalledTimes(1);
  });
});
