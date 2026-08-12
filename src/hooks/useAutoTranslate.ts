/**
 * useAutoTranslate.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * Auto-translate hook for AskMukthiGuru.
 *
 * WHAT IT DOES
 * ────────────
 * When the user has selected a non-English language:
 * 1. translateToEnglish(text) — translates user input → English before AI call
 * 2. translateFromEnglish(text) — translates AI response → selected language
 *    (optional, off by default — user must opt-in via `autoTranslateResponse`)
 *
 * TRANSLATION ENGINE
 * ──────────────────
 * Routes through the existing backend `/api/translate` endpoint via
 * `translateText` in `src/lib/chat/transport.ts`. This keeps user messages off
 * public third-party services and lets the backend handle provider selection,
 * rate limiting, and authentication.
 *
 * The hook caches translations in a session-scoped Map to avoid re-translating
 * identical strings (e.g., repeated "Tell me more" clicks).
 *
 * FAIL-SAFE
 * ─────────
 * All translation failures return the original text unchanged so the chat
 * never breaks. Errors are surfaced through `lastError` and logged with a
 * short prefix.
 */

import { useCallback, useRef, useState } from 'react';
import { translateText } from '@/lib/chat/transport';

const CACHE_MAX = 200;

interface TranslationCache {
  get(key: string): string | undefined;
  set(key: string, value: string): void;
  size: number;
}

function makeCache(): TranslationCache {
  const map = new Map<string, string>();
  return {
    get: (k) => map.get(k),
    set: (k, v) => {
      if (map.size >= CACHE_MAX) {
        const first = map.keys().next().value;
        if (first !== undefined) map.delete(first);
      }
      map.set(k, v);
    },
    get size() { return map.size; },
  };
}

async function backendTranslate(
  text: string,
  fromCode: string,
  toCode: string,
): Promise<string> {
  if (!text.trim()) return text;
  const result = await translateText(text, toCode, fromCode);
  if (!result || result === text) return text;
  return result;
}

export interface UseAutoTranslateOptions {
  /** Currently selected language code (e.g., 'hi', 'te', 'en'). */
  languageCode: string;
  /** If true, will also translate AI responses back to the user's language. */
  autoTranslateResponse?: boolean;
}

export interface UseAutoTranslateResult {
  /** Translate user message → English. Returns original text on error or if already English. */
  translateToEnglish: (text: string) => Promise<string>;
  /** Translate English AI response → user's selected language. Returns original on error. */
  translateFromEnglish: (text: string) => Promise<string>;
  /** True if translation is in progress (useful to show a spinner). */
  isTranslating: boolean;
  /** True if auto-translate is active (language !== 'en'). */
  isActive: boolean;
  /** Error message from last translation attempt, or null. */
  lastError: string | null;
}

const TO_BACKEND: Record<string, string> = {
  en: 'en-IN', hi: 'hi-IN', bn: 'bn-IN', te: 'te-IN', mr: 'mr-IN', ta: 'ta-IN',
  ur: 'ur-IN', gu: 'gu-IN', kn: 'kn-IN', ml: 'ml-IN', or: 'or-IN', pa: 'pa-IN',
  as: 'as-IN', sa: 'sa-IN', mai: 'mai-IN', ks: 'ks-IN', ne: 'ne-IN', sd: 'sd-IN',
  kok: 'kok-IN', doi: 'doi-IN', mni: 'mni-IN', sat: 'sat-IN', brx: 'brx-IN',
};

export function useAutoTranslate({
  languageCode,
  autoTranslateResponse = false,
}: UseAutoTranslateOptions): UseAutoTranslateResult {
  const [isTranslating, setIsTranslating] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const cacheRef = useRef<TranslationCache>(makeCache());
  const isActive = languageCode !== 'en';
  const langTag = TO_BACKEND[languageCode] ?? `${languageCode}-IN`;

  const translateToEnglish = useCallback(async (text: string): Promise<string> => {
    if (!isActive || !text.trim()) return text;
    const cacheKey = `to_en:${languageCode}:${text}`;
    const cached = cacheRef.current.get(cacheKey);
    if (cached) return cached;

    setIsTranslating(true);
    setLastError(null);
    try {
      const result = await backendTranslate(text, langTag, 'en-IN');
      cacheRef.current.set(cacheKey, result);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(msg);
      console.warn('[AutoTranslate] Failed to translate to English:', msg);
      return text;
    } finally {
      setIsTranslating(false);
    }
  }, [isActive, languageCode, langTag]);

  const translateFromEnglish = useCallback(async (text: string): Promise<string> => {
    if (!isActive || !autoTranslateResponse || !text.trim()) return text;
    const cacheKey = `from_en:${languageCode}:${text.slice(0, 80)}`;
    const cached = cacheRef.current.get(cacheKey);
    if (cached) return cached;

    setIsTranslating(true);
    setLastError(null);
    try {
      const result = await backendTranslate(text, 'en-IN', langTag);
      cacheRef.current.set(cacheKey, result);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(msg);
      console.warn('[AutoTranslate] Failed to translate from English:', msg);
      return text;
    } finally {
      setIsTranslating(false);
    }
  }, [isActive, autoTranslateResponse, languageCode, langTag]);

  return { translateToEnglish, translateFromEnglish, isTranslating, isActive, lastError };
}
