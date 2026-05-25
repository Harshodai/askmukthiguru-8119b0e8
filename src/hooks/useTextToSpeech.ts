import { useState, useEffect, useCallback, useRef } from 'react';
import { LANGUAGES } from '@/components/chat/LanguageSelector';
import { supabase } from '@/integrations/supabase/client';

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

export const useTextToSpeech = (options: UseTextToSpeechOptions = {}): UseTextToSpeechReturn => {
  const { lang = 'en', rate = 0.9, pitch = 1, volume = 1, speaker, onError } = options;

  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [currentVoice, setCurrentVoice] = useState<SpeechSynthesisVoice | null>(null);
  const [error, setError] = useState<string | null>(null);

  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const sarvamAudioRef = useRef<HTMLAudioElement | null>(null);

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
    window.speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      window.speechSynthesis.onvoiceschanged = null;
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

  const speak = useCallback(
    (text: string) => {
      setError(null);

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

      // Determine if a native browser voice supports the selected language.
      const preferredLangs = languageMap[lang] || [];
      const hasLocalVoice = voices.some((voice) => {
        return preferredLangs.some(
          (pref) => voice.lang.startsWith(pref.split('-')[0]) || voice.lang === pref
        );
      });

      // Fallback to Sarvam TTS edge function if no local voice for Indic languages
      if (!hasLocalVoice && lang !== 'en') {
        setIsSpeaking(true);
        supabase.functions
          .invoke('sarvam-tts', {
            body: {
              text,
              target_language_code: lang,
              ...(speaker ? { speaker } : {}),
            },
          })
          .then(({ data, error }) => {
            if (error) throw error;
            if (!data?.audio) throw new Error('No audio payload in response');

            const audioUrl = `data:audio/mp3;base64,${data.audio}`;
            const audio = new Audio(audioUrl);
            sarvamAudioRef.current = audio;

            audio.onplay = () => {
              setIsSpeaking(true);
              setIsPaused(false);
            };

            audio.onended = () => {
              setIsSpeaking(false);
              setIsPaused(false);
              sarvamAudioRef.current = null;
            };

            audio.onerror = () => {
              const errMsg = `Failed to play generated voice output.`;
              setError(errMsg);
              onErrorRef.current?.(errMsg);
              setIsSpeaking(false);
              sarvamAudioRef.current = null;
            };

            audio.play().catch(() => {
              const errMsg = `Audio playback blocked or failed.`;
              setError(errMsg);
              onErrorRef.current?.(errMsg);
              setIsSpeaking(false);
            });
          })
          .catch((err) => {
            const langName = LANGUAGES.find((l) => l.code === lang)?.name ?? lang;
            const errMsg = `Voice output isn't available for ${langName} right now. Showing text only.`;
            setError(errMsg);
            onErrorRef.current?.(errMsg);
            setIsSpeaking(false);
            console.warn('Sarvam TTS failed:', err);
          });
      } else {
        // Native SpeechSynthesis fallback/flow
        if (!isSupported) {
          const errMsg = 'Speech synthesis not supported in this browser.';
          setError(errMsg);
          onErrorRef.current?.(errMsg);
          return;
        }

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
        };

        utterance.onerror = (event) => {
          console.error('Speech synthesis error:', event.error);
          setIsSpeaking(false);
          setIsPaused(false);
        };

        utterance.onpause = () => {
          setIsPaused(true);
        };

        utterance.onresume = () => {
          setIsPaused(false);
        };

        utteranceRef.current = utterance;
        window.speechSynthesis.speak(utterance);
      }
    },
    [isSupported, currentVoice, lang, rate, pitch, volume, voices, speaker]
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
      if (isSupported) {
        window.speechSynthesis.cancel();
      }
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
    error,
  };
};
