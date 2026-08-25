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
export interface MeditationAudioOptions {
  onTimeUpdate?: (seconds: number) => void;
  onEnded?: () => void;
  seekTo?: number | null;
}

export function useMeditationAudio(
  steps: MeditationStep[],
  stepIndex: number,
  isPlaying: boolean,
  muted = false,
  options: MeditationAudioOptions = {},
) {
  const { onTimeUpdate, onEnded, seekTo } = options;
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const preloadRef = useRef<HTMLAudioElement | null>(null);
  const loadingSrcRef = useRef<string | null>(null);
  // Failure is tracked by audio URL, not step index. GUIDED_STEPS commonly
  // has every step share one continuous track (see meditationSteps.ts), so a
  // broken URL is broken for every step referencing it — not just the step
  // that happened to hit the error first. Indexing by stepIndex let a later
  // step retry (and reset currentTime to 0) a URL already known dead, and
  // the stray timeupdate from that retry raced the caller's fallback timer,
  // snapping progress back to step 0 right at the step boundary.
  const permanentlyFailedSrcRef = useRef<Set<string>>(new Set());
  const [failedVersion, setFailedVersion] = useState(0);

  const currentSrc = steps[stepIndex]?.audioSrc;
  // Recomputed every render from the ref's current contents; failedVersion
  // only exists to force that recompute when onerror mutates the ref.
  const audioFailed = !!currentSrc && permanentlyFailedSrcRef.current.has(currentSrc);
  void failedVersion;

  // Lazy-create the audio elements once, on the client.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!audioRef.current) {
      const el = new Audio();
      el.preload = 'auto';
      // No crossOrigin: the Lovable asset CDN does not send CORS headers for
      // <audio>, and setting it to 'anonymous' blocks the load entirely,
      // which was leaving Serene Mind silent in production.
      el.onerror = () => {
        console.error('[useMeditationAudio] failed to load src=', el.src, 'error code=', el.error?.code, 'network state=', el.networkState, 'ready state=', el.readyState);
        el.removeAttribute('src');
        if (loadingSrcRef.current) permanentlyFailedSrcRef.current.add(loadingSrcRef.current);
        setFailedVersion((v) => v + 1);
      };
      audioRef.current = el;
    }
    if (!preloadRef.current) {
      const el = new Audio();
      el.preload = 'auto';
      el.onerror = () => { el.removeAttribute('src'); };
      preloadRef.current = el;
    }
    return () => {
      audioRef.current?.pause();
      preloadRef.current?.pause();
    };
  }, []);

  // Keep callbacks current; the media element is created once but the flow
  // callbacks change as the active step and practice state change.
  //
  // Once the current src has failed, the element can still emit a stray
  // timeupdate/ended at currentTime=0 — without this guard that reset the
  // caller's step/elapsed state back to 0.
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    el.ontimeupdate = () => {
      if (audioFailed) return;
      onTimeUpdate?.(el.currentTime);
    };
    el.onended = () => {
      if (audioFailed) return;
      onEnded?.();
    };
  }, [onTimeUpdate, onEnded, audioFailed]);

  // Load + fade in current step audio when stepIndex (or its src) changes.
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const src = currentSrc;

    // No audio for this step, or its src already failed once → fade out and
    // stay silent rather than retrying a load we know is broken.
    if (!src || permanentlyFailedSrcRef.current.has(src)) {
      fadeOut(el);
      return;
    }

    // Same src already loaded (e.g. steps sharing one continuous track, or a
    // React re-render) → do nothing; this is what keeps currentTime — and
    // therefore the caller's cumulative step/elapsed math — continuous
    // across a multi-step shared track instead of resetting every step.
    if (el.src.endsWith(src)) return;

    loadingSrcRef.current = src;
    el.src = src;
    el.currentTime = 0;
    el.volume = 0;
    if (isPlaying && !muted) {
      el.play().catch((e) => {
        if (e instanceof DOMException && e.name !== 'AbortError') console.warn('[useMeditationAudio] play rejected:', e.message);
      });
      fadeIn(el);
    }

    // Preload the next step.
    const next = steps[stepIndex + 1]?.audioSrc;
    if (next && preloadRef.current) {
      preloadRef.current.src = next;
    }
  }, [steps, stepIndex, isPlaying, muted, currentSrc]);

  // Resume or user-requested seek is applied to the canonical audio timeline.
  useEffect(() => {
    const el = audioRef.current;
    if (!el || seekTo == null || !Number.isFinite(seekTo)) return;
    try {
      el.currentTime = Math.max(0, seekTo);
      onTimeUpdate?.(el.currentTime);
    } catch {
      // Media may not be ready yet; the next playback event will retry safely.
    }
  }, [seekTo, onTimeUpdate]);

  // React to play/pause toggle.
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (isPlaying && !muted && el.src) {
      el.play().catch((e) => {
        if (e instanceof DOMException && e.name !== 'AbortError') console.warn('[useMeditationAudio] play rejected:', e.message);
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

  return { audioFailed };
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
