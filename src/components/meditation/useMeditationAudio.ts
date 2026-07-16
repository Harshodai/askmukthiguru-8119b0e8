import { useEffect, useRef, useState } from 'react';
import type { MeditationStep } from './meditationSteps';

/**
 * Plays per-step narration audio in sync with the meditation timeline.
 *
 * Contract:
 * - Owns a single <audio> element (reused across steps to avoid iOS autoplay stalls).
 * - When `stepIndex` changes and the new step has an `audioSrc`, cross-fades in the new track.
 * - When `isPlaying` toggles false, pauses. When true, resumes at current position.
 * - When a step has no `audioSrc`, the previous audio fades out — timeline continues silently.
 * - Preloads the next step's audio so transitions feel seamless.
 * - A missing/broken clip (`onerror`) is reported via the returned `audioFailed` flag so the
 *   caller can fall back to `useMeditationTTS` instead of going silent.
 *
 * The hook takes an optional `muted` flag so the player's mute button just routes here.
 */
export function useMeditationAudio(
  steps: MeditationStep[],
  stepIndex: number,
  isPlaying: boolean,
  muted = false,
) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const preloadRef = useRef<HTMLAudioElement | null>(null);
  const loadingStepRef = useRef<number>(-1);
  const [failedStep, setFailedStep] = useState<number | null>(null);

  // Lazy-create the audio elements once, on the client.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!audioRef.current) {
      const el = new Audio();
      el.preload = 'auto';
      el.crossOrigin = 'anonymous';
      // Missing/corrupt clip — drop the src and flag the step so TTS can take over.
      el.onerror = () => {
        el.removeAttribute('src');
        setFailedStep(loadingStepRef.current);
      };
      audioRef.current = el;
    }
    if (!preloadRef.current) {
      const el = new Audio();
      el.preload = 'auto';
      el.crossOrigin = 'anonymous';
      el.onerror = () => { el.removeAttribute('src'); };
      preloadRef.current = el;
    }
    return () => {
      audioRef.current?.pause();
      preloadRef.current?.pause();
    };
  }, []);

  // Load + fade in current step audio when stepIndex changes.
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const step = steps[stepIndex];
    const src = step?.audioSrc;

    // No audio for this step → fade out and stop.
    if (!src) {
      fadeOut(el);
      return;
    }

    // Same src (e.g. React re-render) → do nothing.
    if (el.src.endsWith(src)) return;

    loadingStepRef.current = stepIndex;
    el.src = src;
    el.currentTime = 0;
    el.volume = 0;
    if (isPlaying && !muted) {
      el.play().catch(() => {
        /* autoplay blocked — not a missing-file case, TTS fallback stays silent here */
      });
      fadeIn(el);
    }

    // Preload the next step.
    const next = steps[stepIndex + 1]?.audioSrc;
    if (next && preloadRef.current) {
      preloadRef.current.src = next;
    }
  }, [steps, stepIndex, isPlaying, muted]);

  // React to play/pause toggle.
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (isPlaying && !muted && el.src) {
      el.play().catch(() => {
        /* silent */
      });
    } else {
      el.pause();
    }
  }, [isPlaying, muted]);

  // React to mute toggle.
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    el.muted = muted;
  }, [muted]);

  return { audioFailed: failedStep === stepIndex };
}

function fadeIn(el: HTMLAudioElement, targetVolume = 1, durationMs = 400) {
  const steps = 20;
  const stepMs = durationMs / steps;
  let i = 0;
  const timer = window.setInterval(() => {
    i += 1;
    el.volume = Math.min(targetVolume, (i / steps) * targetVolume);
    if (i >= steps) window.clearInterval(timer);
  }, stepMs);
}

function fadeOut(el: HTMLAudioElement, durationMs = 300) {
  const start = el.volume;
  if (start === 0) {
    el.pause();
    return;
  }
  const steps = 15;
  const stepMs = durationMs / steps;
  let i = 0;
  const timer = window.setInterval(() => {
    i += 1;
    el.volume = Math.max(0, start * (1 - i / steps));
    if (i >= steps) {
      window.clearInterval(timer);
      el.pause();
    }
  }, stepMs);
}
