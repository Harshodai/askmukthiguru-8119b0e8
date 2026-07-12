import { useCallback, useEffect, useRef, useState } from 'react';

const API_BASE =
  (import.meta as unknown as { env?: { VITE_API_BASE_URL?: string } }).env?.VITE_API_BASE_URL ?? '';

export interface UseVoiceInputResult {
  isListening: boolean;
  transcript: string;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
  setTranscript: (text: string) => void;
  supported: boolean;
}

export const useVoiceInput = (): UseVoiceInputResult => {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const generationRef = useRef(0);

  const supported =
    typeof window !== 'undefined' &&
    'MediaRecorder' in window &&
    !!navigator.mediaDevices?.getUserMedia;

  const cleanup = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
  }, []);

  const stop = useCallback(() => {
    generationRef.current += 1;
    const rec = recorderRef.current;
    if (rec && rec.state !== 'inactive') {
      rec.stop();
    }
    setIsListening(false);
    cleanup();
  }, [cleanup]);

  const getExtensionFromMimeType = (mimeType: string): string => {
    const map: Record<string, string> = {
      'audio/webm': 'webm',
      'audio/ogg': 'ogg',
      'audio/mp4': 'mp4',
      'audio/mpeg': 'mp3',
      'audio/wav': 'wav',
    };
    return map[mimeType] || 'webm';
  };

  const start = useCallback(async () => {
    setError(null);
    if (!supported) {
      setError('Voice input not supported');
      return;
    }
    const currentGen = ++generationRef.current;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (generationRef.current !== currentGen) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        if (generationRef.current !== currentGen) {
          return;
        }
        const mimeType = recorder.mimeType || 'audio/webm';
        const extension = getExtensionFromMimeType(mimeType);
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const form = new FormData();
        form.append('audio', blob, `voice.${extension}`);
        try {
          if (!API_BASE) {
            setError('Voice endpoint not configured');
            return;
          }
          const res = await fetch(`${API_BASE}/api/stt`, { method: 'POST', body: form });
          if (!res.ok) {
            setError('Transcription failed');
            return;
          }
          const data = (await res.json()) as { text?: string };
          if (data.text) {
            setTranscript((prev) => (prev ? `${prev} ${data.text}` : data.text ?? ''));
          }
        } catch {
          setError('Transcription failed');
        } finally {
          cleanup();
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setIsListening(true);
    } catch {
      if (generationRef.current === currentGen) {
        setError('Microphone access denied');
        cleanup();
      }
    }
  }, [supported, cleanup]);

  useEffect(() => () => cleanup(), [cleanup]);

  const reset = useCallback(() => {
    setTranscript('');
    setError(null);
  }, []);

  return {
    isListening,
    transcript,
    error,
    start,
    stop,
    reset,
    setTranscript,
    supported,
  };
};
