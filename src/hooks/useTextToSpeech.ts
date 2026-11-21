import { useState, useEffect, useCallback, useRef } from 'react';
import { LANGUAGES } from '@/components/chat/LanguageSelector';
import { BACKEND_URL_OR_LOCAL } from '@/lib/backendUrl';
import { getAccessToken } from '@/lib/chat/auth';
import { normalizeForSpeech } from '@/lib/audio/spokenTextNormalizer';
import { StreamingAudioQueue } from '@/lib/audio/StreamingAudioQueue';

export interface UseTextToSpeechOptions {
  lang?: string;
  rate?: number;
  pitch?: number;
  volume?: number;
  speaker?: string;
  onError?: (error: string) => void;
}

export interface UseTextToSpeechReturn {
  speak: (text: string, langOverride?: string) => void;
  speakSentence: (sentence: string, isLast?: boolean, langOverride?: string) => Promise<void>;
  finishStream: () => void;
  stop: () => void;
  pause: () => void;
  resume: () => void;
  isSpeaking: boolean;
  isPaused: boolean;
  isSupported: boolean;
  voices: SpeechSynthesisVoice[];
  currentVoice: SpeechSynthesisVoice | null;
  currentSentence: string | null;
  error: string | null;
}

// Build language -> preferred BCP-47 tags from canonical LANGUAGES list.
const languageMap: Record<string, string[]> = LANGUAGES.reduce(
  (acc, l) => {
    acc[l.code] = l.code === 'en' ? ['en-IN', 'en-US', 'en-GB', 'en-AU'] : [l.bcp47, l.code];
    return acc;
  },
  {} as Record<string, string[]>,
);

const splitIntoSentences = (text: string): string[] => {
  if (!text.trim()) return [];
  return text
    .split(/(?<=[.!?।\n])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
};

const findSentenceAtIndex = (text: string, charIndex: number): string | null => {
  const sentences = splitIntoSentences(text);
  let cursor = 0;
  for (const sentence of sentences) {
    const start = text.indexOf(sentence, cursor);
    if (start === -1) continue;
    const end = start + sentence.length;
    if (charIndex >= start && charIndex <= end) return sentence;
    cursor = end;
  }
  return sentences[0] ?? null;
};

export const useTextToSpeech = (options: UseTextToSpeechOptions = {}): UseTextToSpeechReturn => {
  const { lang = 'en', rate = 0.9, pitch = 1, volume = 1, speaker, onError } = options;

  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [currentVoice, setCurrentVoice] = useState<SpeechSynthesisVoice | null>(null);
  const [currentSentence, setCurrentSentence] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const sarvamAudioRef = useRef<HTMLAudioElement | null>(null);
  const currentTextRef = useRef<string>('');
  const sentencesRef = useRef<string[]>([]);
  const streamingQueueRef = useRef<StreamingAudioQueue | null>(null);

  const isSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;
  const onErrorRef = useRef(onError);

  // Each speak() or speakSentence() run takes a generation; stop() and a newer speak() bump it
  const generationRef = useRef(0);
  const pendingRequestsRef = useRef<Set<AbortController>>(new Set());

  // Sequenced streaming synthesis state to guarantee in-order queueing and gapless chaining
  const nextSeqRef = useRef(0);
  const enqueuedSeqRef = useRef(0);
  const pendingAudioMapRef = useRef<Map<number, { audioUrl: string; sentence: string }>>(new Map());
  const totalSentencesRef = useRef<number | null>(null);

  const cancelPending = useCallback(() => {
    generationRef.current += 1;
    pendingRequestsRef.current.forEach((controller) => {
      try {
        controller.abort();
      } catch {
        // Safe ignore
      }
    });
    pendingRequestsRef.current.clear();
    pendingAudioMapRef.current.clear();
    nextSeqRef.current = 0;
    enqueuedSeqRef.current = 0;
    totalSentencesRef.current = null;
  }, []);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  // Lazy-initialize the streaming audio queue
  const getStreamingQueue = useCallback(() => {
    if (!streamingQueueRef.current) {
      streamingQueueRef.current = new StreamingAudioQueue({
        onPlaybackStart: () => {
          setIsSpeaking(true);
          setIsPaused(false);
        },
        onPlaybackEnd: () => {
          setIsSpeaking(false);
          setIsPaused(false);
          setCurrentSentence(null);
        },
        onSentenceChange: (sentence) => {
          setCurrentSentence(sentence);
        },
        onError: (err) => {
          console.warn('[useTextToSpeech] Streaming audio error:', err);
          const errMsg = err.message || 'Streaming audio playback error';
          setError(errMsg);
          onErrorRef.current?.(errMsg);
        },
      });
    }
    return streamingQueueRef.current;
  }, []);

  // Load available voices
  useEffect(() => {
    if (!isSupported) return;

    const loadVoices = () => {
      const availableVoices = window.speechSynthesis.getVoices();
      setVoices(availableVoices);
    };

    loadVoices();
    window.speechSynthesis.addEventListener('voiceschanged', loadVoices);

    return () => {
      window.speechSynthesis.removeEventListener('voiceschanged', loadVoices);
    };
  }, [isSupported]);

  // Find the best voice for the current language
  useEffect(() => {
    if (voices.length === 0) return;

    const preferredLangs = languageMap[lang] || languageMap.en;

    for (const preferredLang of preferredLangs) {
      const matchingVoice = voices.find(
        (voice) => voice.lang.startsWith(preferredLang.split('-')[0]) || voice.lang === preferredLang
      );
      if (matchingVoice) {
        setCurrentVoice(matchingVoice);
        return;
      }
    }

    const fallbackVoice = voices.find((voice) => voice.lang.startsWith('en'));
    setCurrentVoice(fallbackVoice || voices[0] || null);
  }, [lang, voices]);

  const findVoiceForLanguage = useCallback((targetLang: string) => {
    const preferredLangs = languageMap[targetLang] || languageMap.en;
    for (const preferredLang of preferredLangs) {
      const matchingVoice = voices.find(
        (voice) => voice.lang.startsWith(preferredLang.split('-')[0]) || voice.lang === preferredLang,
      );
      if (matchingVoice) return matchingVoice;
    }
    return voices.find((voice) => voice.lang.startsWith('en')) || voices[0] || null;
  }, [voices]);

  const playNativeTTS = useCallback((text: string, languageOverride?: string) => {
    if (!isSupported) {
      const errMsg = 'Speech synthesis not supported in this browser.';
      setError(errMsg);
      onErrorRef.current?.(errMsg);
      return;
    }

    currentTextRef.current = text;
    sentencesRef.current = splitIntoSentences(text);

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = rate;
    utterance.pitch = pitch;
    utterance.volume = volume;

    const targetVoice = findVoiceForLanguage(languageOverride || lang);
    if (targetVoice) {
      utterance.voice = targetVoice;
      utterance.lang = targetVoice.lang;
    } else {
      const langCode = languageMap[languageOverride || lang]?.[0] || 'en-US';
      utterance.lang = langCode;
    }

    utterance.onstart = () => {
      setIsSpeaking(true);
      setIsPaused(false);
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      setIsPaused(false);
      setCurrentSentence(null);
    };

    utterance.onerror = (event) => {
      if (event.error !== 'interrupted' && event.error !== 'canceled') {
        const errMsg = `Speech synthesis failed (${event.error}).`;
        setError(errMsg);
        onErrorRef.current?.(errMsg);
      }
      setIsSpeaking(false);
      setIsPaused(false);
      setCurrentSentence(null);
    };

    utterance.onpause = () => {
      setIsPaused(true);
    };

    utterance.onresume = () => {
      setIsPaused(false);
    };

    utterance.onboundary = (event) => {
      const sentence = findSentenceAtIndex(text, event.charIndex);
      setCurrentSentence(sentence);
    };

    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }, [isSupported, findVoiceForLanguage, lang, rate, pitch, volume]);

  const flushOrderedQueue = useCallback(() => {
    const queue = getStreamingQueue();
    while (pendingAudioMapRef.current.has(enqueuedSeqRef.current)) {
      const item = pendingAudioMapRef.current.get(enqueuedSeqRef.current)!;
      pendingAudioMapRef.current.delete(enqueuedSeqRef.current);
      queue.enqueue(item.audioUrl, item.sentence);
      enqueuedSeqRef.current += 1;
    }

    if (
      totalSentencesRef.current !== null &&
      enqueuedSeqRef.current >= totalSentencesRef.current
    ) {
      queue.markStreamComplete();
    }
  }, [getStreamingQueue]);

  /**
   * Synthesize and enqueue an individual sentence incrementally (streaming TTS).
   * Guaranteed strictly in-order via pendingAudioMap and sequence counter.
   */
  const speakSentence = useCallback(
    async (sentence: string, isLast = false, langOverride?: string): Promise<void> => {
      const clean = normalizeForSpeech(sentence);
      if (!clean) {
        if (isLast) {
          totalSentencesRef.current = nextSeqRef.current;
          flushOrderedQueue();
        }
        return;
      }

      const seq = nextSeqRef.current++;
      if (isLast) {
        totalSentencesRef.current = nextSeqRef.current;
      }

      const generation = generationRef.current;
      const controller = new AbortController();
      pendingRequestsRef.current.add(controller);
      const isSuperseded = () => generation !== generationRef.current;

      setError(null);
      setIsSpeaking(true);

      try {
        const backendUrl = BACKEND_URL_OR_LOCAL;
        if (!backendUrl) throw new Error('Backend URL not configured');

        const token = await getAccessToken();
        if (isSuperseded()) return;

        const res = await fetch(`${backendUrl}/api/speech/tts`, {
          method: 'POST',
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            text: clean,
            target_language_code: langOverride || lang,
            speaker: speaker || 'shubh',
          }),
        });

        pendingRequestsRef.current.delete(controller);

        if (!res.ok) throw new Error(`TTS ${res.status}`);
        const data = await res.json();
        if (isSuperseded()) return;

        if (!data?.audio) throw new Error('No audio payload in response');

        const format = data.format || (data.audio?.startsWith('UklGR') ? 'wav' : 'mp3');
        const audioUrl = `data:audio/${format};base64,${data.audio}`;

        pendingAudioMapRef.current.set(seq, { audioUrl, sentence: clean });
        flushOrderedQueue();
      } catch (err) {
        pendingRequestsRef.current.delete(controller);
        if (isSuperseded()) return;

        console.warn(`[useTextToSpeech] speakSentence (seq ${seq}) failed:`, err);
        // Advance sequence so subsequent items don't stall waiting for this chunk
        enqueuedSeqRef.current = Math.max(enqueuedSeqRef.current, seq + 1);
        flushOrderedQueue();
      }
    },
    [lang, speaker, flushOrderedQueue]
  );

  /**
   * Finalizes streaming audio queue when all sentences have been dispatched.
   */
  const finishStream = useCallback(() => {
    totalSentencesRef.current = nextSeqRef.current;
    flushOrderedQueue();
  }, [flushOrderedQueue]);

  /**
   * Monolithic speak: Cleans and speaks entire text block (backward-compatible).
   */
  const speak = useCallback(
    async (text: string, langOverride?: string) => {
      cancelPending();
      const generation = generationRef.current;
      const controller = new AbortController();
      pendingRequestsRef.current.add(controller);
      const superseded = () => generation !== generationRef.current;

      setError(null);
      setCurrentSentence(null);

      // Stop any existing streaming queue
      if (streamingQueueRef.current) {
        streamingQueueRef.current.stop();
      }

      // Stop any existing Sarvam audio
      if (sarvamAudioRef.current) {
        sarvamAudioRef.current.pause();
        sarvamAudioRef.current = null;
      }

      // Stop native speech synthesis
      if (isSupported) {
        window.speechSynthesis.cancel();
      }

      const cleanText = normalizeForSpeech(text);
      if (!cleanText.trim()) return;

      try {
        setIsSpeaking(true);
        const backendUrl = BACKEND_URL_OR_LOCAL;
        if (!backendUrl) {
          throw new Error('Backend URL not configured');
        }
        const token = await getAccessToken();
        if (superseded()) return;

        const res = await fetch(`${backendUrl}/api/speech/tts`, {
          method: 'POST',
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            text: cleanText.slice(0, 5000),
            target_language_code: langOverride || lang,
            speaker: speaker || 'shubh',
          }),
        });

        pendingRequestsRef.current.delete(controller);

        if (!res.ok) throw new Error(`TTS ${res.status}`);
        const data = await res.json();
        if (superseded()) return;
        if (!data?.audio) throw new Error('No audio payload in response');

        currentTextRef.current = cleanText;
        sentencesRef.current = splitIntoSentences(cleanText);

        const format = data.format || (data.audio?.startsWith('UklGR') ? 'wav' : 'mp3');
        const audioUrl = `data:audio/${format};base64,${data.audio}`;
        const audio = new Audio(audioUrl);
        sarvamAudioRef.current = audio;

        const updateSentenceFromTime = () => {
          if (!audio.duration || !Number.isFinite(audio.duration) || sentencesRef.current.length === 0) {
            return;
          }
          const progress = audio.currentTime / audio.duration;
          const idx = Math.min(
            Math.max(0, Math.floor(progress * sentencesRef.current.length)),
            sentencesRef.current.length - 1,
          );
          setCurrentSentence(sentencesRef.current[idx]);
        };

        audio.addEventListener('timeupdate', updateSentenceFromTime);

        audio.onplay = () => {
          setIsSpeaking(true);
          setIsPaused(false);
          setCurrentSentence(sentencesRef.current[0] ?? null);
        };

        audio.onended = () => {
          setIsSpeaking(false);
          setIsPaused(false);
          setCurrentSentence(null);
          audio.removeEventListener('timeupdate', updateSentenceFromTime);
          sarvamAudioRef.current = null;
        };

        audio.onerror = () => {
          const errMsg = `Failed to play generated voice output.`;
          setError(errMsg);
          onErrorRef.current?.(errMsg);
          setIsSpeaking(false);
          setCurrentSentence(null);
          audio.removeEventListener('timeupdate', updateSentenceFromTime);
          sarvamAudioRef.current = null;
        };

        audio.play().catch(() => {
          const errMsg = `Audio playback blocked or failed.`;
          setError(errMsg);
          onErrorRef.current?.(errMsg);
          setIsSpeaking(false);
          setCurrentSentence(null);
        });
      } catch (err) {
        pendingRequestsRef.current.delete(controller);
        if (superseded()) return;
        console.warn('Sarvam TTS failed, falling back to native TTS:', err);
        setIsSpeaking(false);
        setCurrentSentence(null);
        playNativeTTS(cleanText, langOverride);
      }
    },
    [isSupported, playNativeTTS, lang, speaker, cancelPending]
  );

  const stop = useCallback(() => {
    cancelPending();
    if (streamingQueueRef.current) {
      streamingQueueRef.current.stop();
    }
    if (sarvamAudioRef.current) {
      sarvamAudioRef.current.pause();
      sarvamAudioRef.current = null;
    }
    if (isSupported) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
    setIsPaused(false);
    setCurrentSentence(null);
  }, [isSupported, cancelPending]);

  const pause = useCallback(() => {
    if (streamingQueueRef.current && streamingQueueRef.current.isPlaying) {
      streamingQueueRef.current.pause();
      setIsPaused(true);
    } else if (sarvamAudioRef.current) {
      sarvamAudioRef.current.pause();
      setIsPaused(true);
    } else if (isSupported) {
      window.speechSynthesis.pause();
      setIsPaused(true);
    }
  }, [isSupported]);

  const resume = useCallback(() => {
    if (streamingQueueRef.current && streamingQueueRef.current.isPaused) {
      streamingQueueRef.current.resume();
      setIsPaused(false);
    } else if (sarvamAudioRef.current) {
      sarvamAudioRef.current.play().catch(() => {});
      setIsPaused(false);
    } else if (isSupported) {
      window.speechSynthesis.resume();
      setIsPaused(false);
    }
  }, [isSupported]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cancelPending();
      if (streamingQueueRef.current) {
        streamingQueueRef.current.stop();
        streamingQueueRef.current = null;
      }
      if (sarvamAudioRef.current) {
        sarvamAudioRef.current.pause();
        sarvamAudioRef.current = null;
      }
      if (isSupported && utteranceRef.current != null && window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
      }
      utteranceRef.current = null;
      setCurrentSentence(null);
    };
  }, [isSupported, cancelPending]);

  return {
    speak,
    speakSentence,
    finishStream,
    stop,
    pause,
    resume,
    isSpeaking,
    isPaused,
    isSupported,
    voices,
    currentVoice,
    currentSentence,
    error,
  };
};
