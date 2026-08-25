import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMeditationAudio } from '@/components/meditation/useMeditationAudio';
import type { MeditationStep } from '@/components/meditation/meditationSteps';

// A controllable fake <audio> element. Tests trigger onerror/ontimeupdate
// manually to simulate what a real broken/working media element would do.
class FakeAudio {
  src = '';
  currentTime = 0;
  volume = 1;
  muted = false;
  preload = '';
  error: { code: number } | null = null;
  networkState = 0;
  readyState = 0;
  onerror: (() => void) | null = null;
  ontimeupdate: (() => void) | null = null;
  onended: (() => void) | null = null;
  play = vi.fn(() => Promise.resolve());
  pause = vi.fn();
  removeAttribute(name: string) {
    if (name === 'src') this.src = '';
  }
}

const SHARED_SRC = 'https://cdn.example.com/serene-mind.mp3';

const STEPS: MeditationStep[] = [
  { id: 'arrive', title: 'Arrive', instruction: '...', durationSeconds: 21, audioSrc: SHARED_SRC },
  { id: 'observe-body', title: 'Observe the Body', instruction: '...', durationSeconds: 47, audioSrc: SHARED_SRC },
  { id: 'observe-breath', title: 'Observe the Breath', instruction: '...', durationSeconds: 63, audioSrc: SHARED_SRC },
];

let instances: FakeAudio[] = [];

describe('useMeditationAudio', () => {
  beforeEach(() => {
    instances = [];
    vi.stubGlobal(
      'Audio',
      function AudioMock() {
        const el = new FakeAudio();
        instances.push(el);
        return el;
      },
    );
  });

  it('never retries a shared src once it has failed, regardless of stepIndex', () => {
    const { result, rerender } = renderHook(
      ({ stepIndex }) => useMeditationAudio(STEPS, stepIndex, true, false, {}),
      { initialProps: { stepIndex: 0 } },
    );

    const primary = instances[0];
    // Simulate the browser failing to load the shared track for step 0.
    act(() => {
      primary.onerror?.();
    });
    expect(result.current.audioFailed).toBe(true);
    const playCallsAfterFirstFailure = primary.play.mock.calls.length;

    // Advance to step 1 — same shared src. It must not be retried.
    rerender({ stepIndex: 1 });
    expect(result.current.audioFailed).toBe(true);
    expect(primary.play.mock.calls.length).toBe(playCallsAfterFirstFailure);

    // Advance to step 2 — still the same shared src, still no retry.
    rerender({ stepIndex: 2 });
    expect(result.current.audioFailed).toBe(true);
    expect(primary.play.mock.calls.length).toBe(playCallsAfterFirstFailure);
  });

  it('ignores a stray ontimeupdate fired after the src has failed', () => {
    const onTimeUpdate = vi.fn();
    const { result, rerender } = renderHook(
      ({ stepIndex }) => useMeditationAudio(STEPS, stepIndex, true, false, { onTimeUpdate }),
      { initialProps: { stepIndex: 0 } },
    );

    const primary = instances[0];
    act(() => {
      primary.onerror?.();
    });
    expect(result.current.audioFailed).toBe(true);

    rerender({ stepIndex: 1 });

    // A late/stray event from the dead element must not reach the caller —
    // this is exactly what previously reset currentStepIndex back to 0.
    act(() => {
      primary.currentTime = 0;
      primary.ontimeupdate?.();
    });
    expect(onTimeUpdate).not.toHaveBeenCalled();
  });

  it('does not treat a working shared track as failed across step changes', () => {
    const { result, rerender } = renderHook(
      ({ stepIndex }) => useMeditationAudio(STEPS, stepIndex, true, false, {}),
      { initialProps: { stepIndex: 0 } },
    );

    expect(result.current.audioFailed).toBe(false);
    rerender({ stepIndex: 1 });
    expect(result.current.audioFailed).toBe(false);
    rerender({ stepIndex: 2 });
    expect(result.current.audioFailed).toBe(false);
  });
});
