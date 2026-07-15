/**
 * Meditation narration via the browser's built-in SpeechSynthesis API.
 * Zero cost, zero backend, works offline. When a step has a real `audioSrc`
 * MP3, `useMeditationAudio` takes over and this hook stays silent.
 */
import { useEffect, useRef, useCallback } from 'react';
import type { MeditationStep } from './meditationSteps';

function getBestVoice(): SpeechSynthesisVoice | null {
  if (typeof window === 'undefined' || !window.speechSynthesis) return null;
  const voices = window.speechSynthesis.getVoices();
  const ranked = [
    voices.find((v) => v.name === 'Samantha'),
    voices.find((v) => v.name.includes('Google UK English Female')),
    voices.find((v) => v.name.includes('Karen')),
    voices.find((v) => v.lang === 'en-GB' && !v.name.toLowerCase().includes('male')),
    voices.find((v) => v.lang === 'en-IN'),
    voices.find((v) => v.lang.startsWith('en') && !v.name.toLowerCase().includes('male')),
    voices[0],
  ];
  return ranked.find(Boolean) ?? null;
}

export function useMeditationTTS(
  steps: MeditationStep[],
  stepIndex: number,
  isPlaying: boolean,
  muted = false,
) {
  const spokenIndexRef = useRef<number>(-1);

  const speak = useCallback((text: string) => {
    if (typeof window === 'undefined' || !window.speechSynthesis || muted) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.82;
    u.pitch = 0.9;
    u.volume = 1;
    const assignVoice = () => {
      const voice = getBestVoice();
      if (voice) u.voice = voice;
    };
    if (window.speechSynthesis.getVoices().length === 0) {
      window.speechSynthesis.addEventListener('voiceschanged', assignVoice, { once: true });
    } else {
      assignVoice();
    }
    window.speechSynthesis.speak(u);
  }, [muted]);

  useEffect(() => {
    if (!isPlaying || muted) return;
    if (spokenIndexRef.current === stepIndex) return;
    const step = steps[stepIndex];
    if (!step || step.audioSrc) return; // real MP3 takes priority
    spokenIndexRef.current = stepIndex;
    const t = setTimeout(() => speak(step.instruction), 600);
    return () => clearTimeout(t);
  }, [steps, stepIndex, isPlaying, muted, speak]);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;
    if (!isPlaying || muted) {
      window.speechSynthesis.pause();
    } else {
      window.speechSynthesis.resume();
    }
  }, [isPlaying, muted]);

  useEffect(() => {
    if (muted && typeof window !== 'undefined') window.speechSynthesis?.cancel();
  }, [muted]);

  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined') window.speechSynthesis?.cancel();
    };
  }, []);
}
