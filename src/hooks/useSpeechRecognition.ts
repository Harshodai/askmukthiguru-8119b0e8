import { useState, useRef, useEffect, useCallback } from 'react';
import { LANGUAGES } from '@/components/chat/LanguageSelector';
import { supabase } from '@/integrations/supabase/client';

// Build BCP-47 lookup from the canonical LANGUAGES list (22 Indic + English).
const languageCodeMap: Record<string, string> = LANGUAGES.reduce(
  (acc, l) => {
    acc[l.code] = l.bcp47;
    return acc;
  },
  {} as Record<string, string>,
);

interface SpeechRecognitionEvent {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent {
  error: string;
  message: string;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResultList {
  length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognitionInstance;
    webkitSpeechRecognition: new () => SpeechRecognitionInstance;
  }
}

interface UseSpeechRecognitionOptions {
  lang?: string;
  continuous?: boolean;
  onTranscript?: (transcript: string, isFinal: boolean) => void;
  onError?: (error: string) => void;
  useSarvam?: boolean;
  onLanguageDetected?: (lang: string) => void;
}

interface UseSpeechRecognitionReturn {
  transcript: string;
  interimTranscript: string;
  isListening: boolean;
  isSupported: boolean;
  error: string | null;
  startListening: () => void;
  stopListening: () => void;
  resetTranscript: () => void;
}

export const useSpeechRecognition = (
  options: UseSpeechRecognitionOptions = {}
): UseSpeechRecognitionReturn => {
  const {
    lang = 'en',
    continuous = true,
    onTranscript,
    onError,
    useSarvam = true,
    onLanguageDetected,
  } = options;

  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSupported, setIsSupported] = useState(false);

  // Native SpeechRecognition refs
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const isListeningRef = useRef(false);

  // Sarvam (MediaRecorder) refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // Keep references updated to avoid closures issue
  const langRef = useRef(lang);
  const onTranscriptRef = useRef(onTranscript);
  const onErrorRef = useRef(onError);
  const onLanguageDetectedRef = useRef(onLanguageDetected);
  const useSarvamRef = useRef(useSarvam);

  useEffect(() => { langRef.current = lang; }, [lang]);
  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { onErrorRef.current = onError; }, [onError]);
  useEffect(() => { onLanguageDetectedRef.current = onLanguageDetected; }, [onLanguageDetected]);
  useEffect(() => { useSarvamRef.current = useSarvam; }, [useSarvam]);

  // Handle support check and native SpeechRecognition creation
  useEffect(() => {
    if (useSarvam) {
      const supported = !!(navigator.mediaDevices && window.MediaRecorder);
      setIsSupported(supported);
      if (!supported) {
        setError('Audio recording is not supported in this browser');
      }
      return;
    }

    const SpeechRecognitionAPI =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionAPI) {
      setIsSupported(false);
      setError('Speech recognition is not supported in this browser');
      return;
    }

    setIsSupported(true);
    const recognition = new SpeechRecognitionAPI();

    recognition.continuous = continuous;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.lang = languageCodeMap[langRef.current] || 'en-US';

    recognition.onstart = () => {
      setIsListening(true);
      setError(null);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final += result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }

      if (final) {
        setTranscript((prev) => prev + final);
        onTranscriptRef.current?.(final, true);
      }

      setInterimTranscript(interim);
      if (interim) {
        onTranscriptRef.current?.(interim, false);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const errorMessages: Record<string, string> = {
        'not-allowed': 'Microphone access denied. Please enable microphone permissions.',
        'no-speech': 'No speech detected. Please try again.',
        'audio-capture': 'No microphone found. Please check your microphone.',
        'network': 'Network error occurred. Please check your connection.',
        'aborted': 'Recognition was stopped.',
        'service-not-allowed': 'Speech service not allowed.',
      };

      const errorMessage = errorMessages[event.error] || `Speech recognition error: ${event.error}`;
      setError(errorMessage);
      onErrorRef.current?.(errorMessage);
      setIsListening(false);
      isListeningRef.current = false;
    };

    recognition.onend = () => {
      setIsListening(false);
      if (isListeningRef.current) {
        try {
          recognition.lang = languageCodeMap[langRef.current] || 'en-US';
          recognition.start();
        } catch {
          // Ignore errors during restart
        }
      }
    };

    recognitionRef.current = recognition;

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
    };
  }, [useSarvam, continuous]);

  const startListening = useCallback(async () => {
    setError(null);
    setTranscript('');
    setInterimTranscript('');

    if (useSarvamRef.current) {
      if (!navigator.mediaDevices || !window.MediaRecorder) {
        setError('Audio recording is not supported in this browser');
        return;
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRef.current = stream;
        chunksRef.current = [];

        // Check browser-supported mime types
        const options = { mimeType: 'audio/webm' };
        if (!MediaRecorder.isTypeSupported(options.mimeType)) {
          options.mimeType = 'audio/mp4';
          if (!MediaRecorder.isTypeSupported(options.mimeType)) {
            options.mimeType = 'audio/ogg';
            if (!MediaRecorder.isTypeSupported(options.mimeType)) {
              options.mimeType = ''; // Let browser decide
            }
          }
        }

        const mediaRecorder = new MediaRecorder(stream, options);
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) {
            chunksRef.current.push(e.data);
          }
        };

        mediaRecorder.onstop = async () => {
          console.log("[STT] mediaRecorder.onstop triggered");
          const mimeType = mediaRecorder.mimeType || 'audio/webm';
          const audioBlob = new Blob(chunksRef.current, { type: mimeType });
          console.log("[STT] audioBlob size:", audioBlob.size, "mimeType:", mimeType);
          chunksRef.current = [];

          // Upload audio blob to Sarvam STT edge function
          try {
            const formData = new FormData();
            formData.append('file', audioBlob, `audio.${mimeType.split('/')[1] || 'webm'}`);

            // Map our selected lang code to standard language code map
            const targetLang = languageCodeMap[langRef.current] || 'en-IN';
            formData.append('language_code', targetLang);

            console.log('[STT] Invoking sarvam-stt edge function with lang:', targetLang);
            const { data, error: fnError } = await supabase.functions.invoke('sarvam-stt', {
              body: formData,
            });

            if (fnError) {
              throw new Error(fnError.message || 'STT edge function failed');
            }

            console.log('[STT] Response data:', JSON.stringify(data));
            const text = data?.transcript || '';
            const detectedLang = data?.language_code || targetLang;

            if (!text) {
              throw new Error('No speech detected. Please try again.');
            }

            setTranscript(text);
            onTranscriptRef.current?.(text, true);

            if (onLanguageDetectedRef.current && detectedLang) {
              console.log('[STT] Triggering onLanguageDetected with:', detectedLang);
              onLanguageDetectedRef.current(detectedLang);
            }
          } catch (err) {
            const msg = (err as Error).message || 'Failed to process speech input';
            console.error('[STT] Error during processing:', msg);
            setError(msg);
            onErrorRef.current?.(msg);
          } finally {
            // Clean up stream tracks
            if (streamRef.current) {
              streamRef.current.getTracks().forEach((track) => track.stop());
              streamRef.current = null;
            }
            setIsListening(false);
          }
        };

        mediaRecorder.start();
        setIsListening(true);
      } catch (err) {
        const msg = 'Microphone permission denied or microphone not found.';
        setError(msg);
        onErrorRef.current?.(msg);
        setIsListening(false);
      }
    } else {
      // Native SpeechRecognition flow
      if (!recognitionRef.current || !isSupported) {
        setError('Speech recognition is not supported');
        return;
      }

      try {
        isListeningRef.current = true;
        recognitionRef.current.lang = languageCodeMap[langRef.current] || 'en-US';
        recognitionRef.current.start();
      } catch (err) {
        if ((err as Error).message?.includes('already started')) {
          recognitionRef.current.stop();
          setTimeout(() => {
            recognitionRef.current?.start();
          }, 100);
        } else {
          setError('Failed to start speech recognition');
          isListeningRef.current = false;
        }
      }
    }
  }, [isSupported]);

  const stopListening = useCallback(() => {
    if (useSarvamRef.current) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    } else {
      isListeningRef.current = false;
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setIsListening(false);
    }
  }, []);

  const resetTranscript = useCallback(() => {
    setTranscript('');
    setInterimTranscript('');
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Auto-dismiss errors after 5 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => {
        setError(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  return {
    transcript,
    interimTranscript,
    isListening,
    isSupported,
    error,
    clearError,
    startListening,
    stopListening,
    resetTranscript,
  };
};

