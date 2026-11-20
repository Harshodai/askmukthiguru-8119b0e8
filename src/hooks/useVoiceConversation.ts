import { useCallback, useEffect, useRef, useState } from 'react';
import i18n from '@/i18n';
import { useTextToSpeech } from './useTextToSpeech';

export type VoiceConversationState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface UseVoiceConversationOptions {
  onSendMessage: (text: string) => Promise<string | void> | void;
  language?: string;
  speaker?: string;
  autoLoop?: boolean;
}

export interface UseVoiceConversationReturn {
  state: VoiceConversationState;
  transcript: string;
  interimTranscript: string;
  responseTranscript: string;
  isMuted: boolean;
  error: string | null;
  audioLevel: number; // 0 to 1, reactive to live microphone
  isSpeaking: boolean;
  currentLanguage: string;
  currentSpeaker: string;
  setLanguage: (lang: string) => void;
  setSpeaker: (speaker: string) => void;
  startSession: () => Promise<void>;
  endSession: () => void;
  toggleMute: () => void;
  interruptSpeaking: () => void;
  submitCurrentSpeech: () => void;
  speakText: (text: string) => void;
}

const SILENCE_TIMEOUT_MS = 2000;

// Minimal Web Speech API types (not in this project's lib.dom).
interface WebSpeechResult {
  isFinal: boolean;
  0: { transcript: string };
}
interface WebSpeechEvent {
  resultIndex: number;
  results: ArrayLike<WebSpeechResult>;
}
interface WebSpeechErrorEvent {
  error: string;
}
interface WebSpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: WebSpeechEvent) => void) | null;
  onerror: ((event: WebSpeechErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}
type SpeechWindow = {
  SpeechRecognition?: new () => WebSpeechRecognition;
  webkitSpeechRecognition?: new () => WebSpeechRecognition;
  webkitAudioContext?: typeof AudioContext;
};

function warnStopFailed(err: unknown): void {
  // stop() throws InvalidStateError when recognition is not running; harmless.
  console.warn('[VoiceConversation] recognition.stop() failed (not running):', err);
}

export function useVoiceConversation({
  onSendMessage,
  language: initialLanguage = 'en',
  speaker: initialSpeaker = 'priya',
  autoLoop = true,
}: UseVoiceConversationOptions): UseVoiceConversationReturn {
  const [currentLanguage, setCurrentLanguage] = useState(initialLanguage);
  const [currentSpeaker, setCurrentSpeaker] = useState(initialSpeaker);
  const [state, setState] = useState<VoiceConversationState>('idle');
  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [responseTranscript, setResponseTranscript] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);

  const recognitionRef = useRef<WebSpeechRecognition | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const activeRef = useRef(false);
  const lastSpokenTextRef = useRef('');

  // TTS Hook
  const { speak, stop: stopSpeaking, isSpeaking } = useTextToSpeech({
    lang: currentLanguage,
    speaker: currentSpeaker,
    onError: (err) => {
      console.warn('[VoiceConversation] TTS error:', err);
      if (activeRef.current && autoLoop) {
        startListeningLoop();
      }
    },
  });

  // Clean up audio analyser
  const cleanupAudio = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch((err) => console.warn('[VoiceConversation] AudioContext close failed:', err));
      audioContextRef.current = null;
    }
    setAudioLevel(0);
  }, []);

  // Web Audio Visualizer Loop
  const startAudioMeter = useCallback((stream: MediaStream) => {
    try {
      const AudioCtx = window.AudioContext || (window as unknown as SpeechWindow).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      audioContextRef.current = ctx;

      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.5;
      analyserRef.current = analyser;

      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);

      const buffer = new Uint8Array(analyser.frequencyBinCount);
      const updateMeter = () => {
        if (!activeRef.current) return;
        analyser.getByteFrequencyData(buffer);
        let sum = 0;
        for (let i = 0; i < buffer.length; i++) {
          sum += buffer[i];
        }
        const avg = sum / buffer.length;
        // Normalize to 0..1 range with gentle boost
        const level = Math.min(1, Math.max(0, (avg / 128) * 1.2));
        setAudioLevel(level);

        // Barge-in detection: if AI is speaking and user starts talking loudly
        if (state === 'speaking' && level > 0.4) {
          interruptSpeaking();
        }

        animFrameRef.current = requestAnimationFrame(updateMeter);
      };
      updateMeter();
    } catch (err) {
      console.warn('[VoiceConversation] Audio meter init error:', err);
    }
  }, [state]);

  const submitSpeech = useCallback(async (finalText: string) => {
    const textToSend = finalText.trim();
    if (!textToSend) return;

    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (err) {
        warnStopFailed(err);
      }
    }

    setState('thinking');
    setTranscript(textToSend);
    setInterimTranscript('');

    try {
      const response = await onSendMessage(textToSend);
      if (typeof response === 'string' && response.trim()) {
        speakText(response);
      } else {
        // If onSendMessage didn't return string directly, wait for next cycle
        setState('speaking');
      }
    } catch (err) {
      setError((err instanceof Error && err.message) || 'Failed to process voice request');
      setState('idle');
    }
  }, [onSendMessage]);

  const startListeningLoop = useCallback(async () => {
    if (!activeRef.current || isMuted) return;

    stopSpeaking();
    setTranscript('');
    setInterimTranscript('');
    setError(null);
    setState('listening');

    // Acquire mic for audio visualizer if not already active
    if (!mediaStreamRef.current) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaStreamRef.current = stream;
        startAudioMeter(stream);
      } catch {
        setError('Microphone access denied. Please grant permission to continue.');
        setState('idle');
        return;
      }
    }

    // Initialize Web Speech Recognition
    const SpeechRecognition =
      (window as unknown as SpeechWindow).SpeechRecognition || (window as unknown as SpeechWindow).webkitSpeechRecognition;

    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition();
        recognitionRef.current = recognition;
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang =
          currentLanguage === 'hi'
            ? 'hi-IN'
            : currentLanguage === 'te'
            ? 'te-IN'
            : currentLanguage === 'ta'
            ? 'ta-IN'
            : currentLanguage === 'kn'
            ? 'kn-IN'
            : currentLanguage === 'ml'
            ? 'ml-IN'
            : currentLanguage === 'mr'
            ? 'mr-IN'
            : currentLanguage === 'bn'
            ? 'bn-IN'
            : currentLanguage === 'gu'
            ? 'gu-IN'
            : 'en-IN';

        let accumulatedFinal = '';

        recognition.onresult = (event: WebSpeechEvent) => {
          let interim = '';
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            const piece = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
              accumulatedFinal += (accumulatedFinal ? ' ' : '') + piece;
            } else {
              interim += piece;
            }
          }
          setInterimTranscript(interim);
          if (accumulatedFinal) {
            setTranscript(accumulatedFinal);
          }

          // Reset silence timer on any speech
          if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
          const currentTotal = (accumulatedFinal + ' ' + interim).trim();
          if (currentTotal) {
            silenceTimerRef.current = setTimeout(() => {
              if (activeRef.current && (accumulatedFinal || interim)) {
                submitSpeech(accumulatedFinal || interim);
              }
            }, SILENCE_TIMEOUT_MS);
          }
        };

        recognition.onerror = (e: WebSpeechErrorEvent) => {
          if (e.error === 'no-speech') {
            // Normal silence; keep listening
            return;
          }
          console.warn('[VoiceConversation] Recognition error:', e.error);
        };

        recognition.onend = () => {
          // If still in listening state and active, restart recognition
          if (activeRef.current && state === 'listening' && !isMuted) {
            try {
              recognition.start();
            } catch (err) {
        warnStopFailed(err);
      }
          }
        };

        recognition.start();
      } catch (err) {
        console.warn('[VoiceConversation] Failed to start SpeechRecognition:', err);
      }
    }
  }, [currentLanguage, isMuted, state, stopSpeaking, startAudioMeter, submitSpeech]);

  const speakText = useCallback((text: string) => {
    if (!text.trim()) return;
    lastSpokenTextRef.current = text;
    setResponseTranscript(text);
    setState('speaking');

    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (err) {
        warnStopFailed(err);
      }
    }

    speak(text);
  }, [speak]);

  // When TTS stops speaking, transition back to listening if session is active
  useEffect(() => {
    if (state === 'speaking' && !isSpeaking && activeRef.current) {
      if (autoLoop) {
        const timer = setTimeout(() => {
          startListeningLoop();
        }, 400);
        return () => clearTimeout(timer);
      } else {
        setState('idle');
      }
    }
  }, [isSpeaking, state, autoLoop, startListeningLoop]);

  const interruptSpeaking = useCallback(() => {
    stopSpeaking();
    if (activeRef.current) {
      startListeningLoop();
    } else {
      setState('idle');
    }
  }, [stopSpeaking, startListeningLoop]);

  const startSession = useCallback(async () => {
    activeRef.current = true;
    setError(null);
    await startListeningLoop();
  }, [startListeningLoop]);

  const endSession = useCallback(() => {
    activeRef.current = false;
    stopSpeaking();
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (err) {
        warnStopFailed(err);
      }
      recognitionRef.current = null;
    }
    cleanupAudio();
    setState('idle');
    setTranscript('');
    setInterimTranscript('');
  }, [stopSpeaking, cleanupAudio]);

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const next = !prev;
      if (next) {
        if (recognitionRef.current) {
          try {
            recognitionRef.current.stop();
          } catch (err) {
        warnStopFailed(err);
      }
        }
        setState('idle');
      } else if (activeRef.current) {
        startListeningLoop();
      }
      return next;
    });
  }, [startListeningLoop]);

  const submitCurrentSpeech = useCallback(() => {
    const text = (transcript + ' ' + interimTranscript).trim();
    if (text) {
      submitSpeech(text);
    }
  }, [transcript, interimTranscript, submitSpeech]);

  useEffect(() => {
    return () => {
      endSession();
    };
  }, [endSession]);

  return {
    state,
    transcript,
    interimTranscript,
    responseTranscript,
    isMuted,
    error,
    audioLevel,
    isSpeaking,
    currentLanguage,
    currentSpeaker,
    setLanguage: setCurrentLanguage,
    setSpeaker: setCurrentSpeaker,
    startSession,
    endSession,
    toggleMute,
    interruptSpeaking,
    submitCurrentSpeech,
    speakText,
  };
}
