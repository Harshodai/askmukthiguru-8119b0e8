import { useCallback, useEffect, useRef, useState } from 'react';
import i18n from '@/i18n';
import { useTextToSpeech } from './useTextToSpeech';
import { BACKEND_URL_OR_LOCAL } from '@/lib/backendUrl';
import { getAccessToken } from '@/lib/chat/auth';

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
// Recorded-audio fallback (browsers without working Web Speech, e.g. Brave).
const FALLBACK_VOICE_LEVEL = 0.06; // same 0..1 scale as the visualizer
const FALLBACK_SILENCE_MS = 1500;
const FALLBACK_MAX_MS = 30000;
const STT_LANGUAGES = new Set(['hi', 'te', 'ta', 'kn', 'ml', 'mr']);
// Recognition errors that mean the browser cannot transcribe at all (Brave blocks the speech service).
// Brave starts recognition without a single event (no start, no error), so detect it and use recording.
const RECOGNITION_START_WATCHDOG_MS = 3500;
const MIC_PERMISSION_HINT_MS = 4000;
const isBraveBrowser = (): boolean =>
  typeof navigator !== 'undefined' && Boolean((navigator as unknown as { brave?: unknown }).brave);
const UNUSABLE_RECOGNITION_ERRORS = new Set(['network', 'service-not-allowed', 'language-not-supported']);

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
  onstart: (() => void) | null;
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
  const fallbackRecorderRef = useRef<MediaRecorder | null>(null);
  const fallbackTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fallbackCancelledRef = useRef(false);
  const useRecordedFallbackRef = useRef(false);
  const listenAgainRef = useRef<() => void>(() => {});
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
      // A context created outside a fresh gesture starts suspended and returns silence.
      if (ctx.state === 'suspended') void ctx.resume();

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

  // Stop the recorded fallback. cancel=true discards what was recorded (we are about to speak or end).
  const stopFallbackRecorder = useCallback((cancel: boolean) => {
    if (fallbackTimerRef.current) {
      clearInterval(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
    const recorder = fallbackRecorderRef.current;
    fallbackRecorderRef.current = null;
    if (recorder && recorder.state !== 'inactive') {
      fallbackCancelledRef.current = cancel;
      try {
        recorder.stop();
      } catch (err) {
        warnStopFailed(err);
      }
    }
  }, []);

  // Browsers without working Web Speech: record, detect the end of speech from the mic level,
  // then transcribe on the backend (/api/speech/stt).
  const startRecordedListening = useCallback((stream: MediaStream) => {
    if (typeof MediaRecorder === 'undefined' || !analyserRef.current) {
      setError('Voice input is not supported in this browser. Please type your question.');
      setState('idle');
      return;
    }
    stopFallbackRecorder(true);
    fallbackCancelledRef.current = false;
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream);
    fallbackRecorderRef.current = recorder;
    const analyser = analyserRef.current;
    const buffer = new Uint8Array(analyser.frequencyBinCount);
    const startedAt = Date.now();
    let heardVoice = false;
    let lastVoiceAt = startedAt;

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = async () => {
      if (fallbackCancelledRef.current || !activeRef.current) return;
      if (!heardVoice) {
        listenAgainRef.current();
        return;
      }
      setState('thinking');
      try {
        const token = await getAccessToken();
        const form = new FormData();
        form.append('file', new Blob(chunks, { type: (recorder.mimeType || 'audio/webm').split(';')[0] }), 'voice.webm');
        form.append('language_code', `${STT_LANGUAGES.has(currentLanguage) ? currentLanguage : 'en'}-IN`);
        const resp = await fetch(`${BACKEND_URL_OR_LOCAL}/api/speech/stt`, {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: form,
        });
        if (!resp.ok) throw new Error(`Speech service unavailable (HTTP ${resp.status})`);
        const data = await resp.json();
        const text = String(data?.transcript || data?.text || '').trim();
        if (!activeRef.current) return;
        if (!text) {
          setError("I didn't catch that. Please try again.");
          listenAgainRef.current();
          return;
        }
        submitSpeech(text);
      } catch (err) {
        setError((err instanceof Error && err.message) || 'Could not understand the recording.');
        setState('idle');
      }
    };

    recorder.start();
    fallbackTimerRef.current = setInterval(() => {
      analyser.getByteFrequencyData(buffer);
      let sum = 0;
      for (let i = 0; i < buffer.length; i++) sum += buffer[i];
      const level = Math.min(1, Math.max(0, (sum / buffer.length / 128) * 1.2));
      const now = Date.now();
      if (level > FALLBACK_VOICE_LEVEL) {
        heardVoice = true;
        lastVoiceAt = now;
      }
      const spokeThenPaused = heardVoice && now - lastVoiceAt > FALLBACK_SILENCE_MS;
      if (spokeThenPaused || now - startedAt > FALLBACK_MAX_MS) {
        stopFallbackRecorder(false);
      }
    }, 100);
  }, [currentLanguage, stopFallbackRecorder, submitSpeech]);

  const startListeningLoop = useCallback(async () => {
    if (!activeRef.current || isMuted) return;

    stopSpeaking();
    setTranscript('');
    setInterimTranscript('');
    setError(null);
    setState('listening');

    // Acquire mic for audio visualizer if not already active
    if (!mediaStreamRef.current) {
      // If the browser is still waiting for the user to answer the permission prompt, say so
      // instead of showing "Listening" over a dead microphone.
      const permissionHint = window.setTimeout(() => {
        setError('Waiting for microphone permission. Click Allow in the address bar (Brave: the lock icon, then Site settings, then Microphone).');
      }, MIC_PERMISSION_HINT_MS);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        window.clearTimeout(permissionHint);
        setError(null);
        mediaStreamRef.current = stream;
        startAudioMeter(stream);
      } catch {
        window.clearTimeout(permissionHint);
        setError('Microphone access denied. Please grant permission to continue.');
        setState('idle');
        return;
      }
    }

    // Initialize Web Speech Recognition
    const SpeechRecognition =
      (window as unknown as SpeechWindow).SpeechRecognition || (window as unknown as SpeechWindow).webkitSpeechRecognition;

    if (isBraveBrowser()) useRecordedFallbackRef.current = true;
    if (!SpeechRecognition || useRecordedFallbackRef.current) {
      if (mediaStreamRef.current) startRecordedListening(mediaStreamRef.current);
      return;
    }

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
            : 'en-IN';

        let accumulatedFinal = '';
        let recognitionAlive = false;
        recognition.onstart = () => { recognitionAlive = true; };
        // Some browsers accept start() and then never produce any event. Switch to recording.
        window.setTimeout(() => {
          if (recognitionAlive || !activeRef.current || useRecordedFallbackRef.current || !mediaStreamRef.current) return;
          useRecordedFallbackRef.current = true;
          recognitionRef.current = null;
          try { recognition.stop(); } catch (err) { warnStopFailed(err); }
          startRecordedListening(mediaStreamRef.current);
        }, RECOGNITION_START_WATCHDOG_MS);

        recognition.onresult = (event: WebSpeechEvent) => {
          recognitionAlive = true;
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
          if (UNUSABLE_RECOGNITION_ERRORS.has(e.error) && mediaStreamRef.current) {
            // The browser cannot transcribe (e.g. Brave). Switch to recorded audio for this session.
            useRecordedFallbackRef.current = true;
            recognitionRef.current = null;
            try { recognition.stop(); } catch (err) { warnStopFailed(err); }
            startRecordedListening(mediaStreamRef.current);
          }
        };

        recognition.onend = () => {
          // If still in listening state and active, restart recognition
          if (activeRef.current && state === 'listening' && !isMuted && !useRecordedFallbackRef.current) {
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
        useRecordedFallbackRef.current = true;
        if (mediaStreamRef.current) startRecordedListening(mediaStreamRef.current);
      }
    }
  }, [currentLanguage, isMuted, state, stopSpeaking, startAudioMeter, submitSpeech, startRecordedListening]);

  listenAgainRef.current = () => { void startListeningLoop(); };

  const speakText = useCallback((text: string) => {
    if (!text.trim()) return;
    lastSpokenTextRef.current = text;
    setResponseTranscript(text);
    setState('speaking');

    stopFallbackRecorder(true);
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (err) {
        warnStopFailed(err);
      }
    }

    speak(text);
  }, [speak, stopFallbackRecorder]);

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
    useRecordedFallbackRef.current = false;
    stopFallbackRecorder(true);
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
  }, [stopSpeaking, cleanupAudio, stopFallbackRecorder]);

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const next = !prev;
      if (next) {
        stopFallbackRecorder(true);
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
  }, [startListeningLoop, stopFallbackRecorder]);

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
