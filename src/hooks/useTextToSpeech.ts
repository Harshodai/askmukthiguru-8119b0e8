import { useState, useEffect, useCallback, useRef } from 'react';
import { LANGUAGES } from '@/components/chat/LanguageSelector';
import { BACKEND_URL_OR_LOCAL } from '@/lib/backendUrl';
import { getAccessToken } from '@/lib/chat/auth';

interface UseTextToSpeechOptions {
  lang?: string;
  rate?: number;
  pitch?: number;
  volume?: number;
  speaker?: string;
  onError?: (error: string) => void;
}

interface UseTextToSpeechReturn {
  speak: (text: string) => void;
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
  // Split on sentence terminators followed by space or end of string, preserving the delimiter.
  return text
    .split(/(?<=[.!?।?\n])\s+/)
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

  const isSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  // Load available voices
  useEffect(() => {
    if (!isSupported) return;

    const loadVoices = () => {
      const availableVoices = window.speechSynthesis.getVoices();
      setVoices(availableVoices);
    };

    loadVoices();

    // Voices may load asynchronously
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

    // Fallback to any English voice
    const fallbackVoice = voices.find((voice) => voice.lang.startsWith('en'));
    setCurrentVoice(fallbackVoice || voices[0] || null);
  }, [lang, voices]);

  const playNativeTTS = useCallback((text: string) => {
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

    if (currentVoice) {
      utterance.voice = currentVoice;
      utterance.lang = currentVoice.lang;
    } else {
      const langCode = languageMap[lang]?.[0] || 'en-US';
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
      console.error('Speech synthesis error:', event.error);
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
  }, [isSupported, currentVoice, lang, rate, pitch, volume]);

  const speak = useCallback(
    async (text: string) => {
      setError(null);
      setCurrentSentence(null);

      // Stop any existing Sarvam audio
      if (sarvamAudioRef.current) {
        sarvamAudioRef.current.pause();
        sarvamAudioRef.current = null;
      }

      // Stop native speech synthesis
      if (isSupported) {
        window.speechSynthesis.cancel();
      }

      if (!text.trim()) return;

      // Sarvam neural TTS is the default for all languages.
      try {
        setIsSpeaking(true);
        const backendUrl = BACKEND_URL_OR_LOCAL;
        if (!backendUrl) {
          throw new Error('Backend URL not configured');
        }
        const token = await getAccessToken();
        const res = await fetch(`${backendUrl}/api/speech/tts`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            text: text.slice(0, 5000),
            target_language_code: lang,
            speaker: speaker || 'shubh',
          }),
        });

        if (!res.ok) throw new Error(`TTS ${res.status}`);
        const data = await res.json();
        if (!data?.audio) throw new Error('No audio payload in response');

        currentTextRef.current = text;
        sentencesRef.current = splitIntoSentences(text);

        const audioUrl = `data:audio/mp3;base64,${data.audio}`;
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
        // Fall back to native speech synthesis on backend failure.
        console.warn('Sarvam TTS failed, falling back to native TTS:', err);
        setIsSpeaking(false);
        setCurrentSentence(null);
        playNativeTTS(text);
      }
    },
    [isSupported, playNativeTTS, lang, speaker]
  );

  const stop = useCallback(() => {
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
  }, [isSupported]);

  const pause = useCallback(() => {
    if (sarvamAudioRef.current) {
      sarvamAudioRef.current.pause();
      setIsPaused(true);
    } else if (isSupported) {
      window.speechSynthesis.pause();
      setIsPaused(true);
    }
  }, [isSupported]);

  const resume = useCallback(() => {
    if (sarvamAudioRef.current) {
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
  }, [isSupported]);

  return {
    speak,
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
