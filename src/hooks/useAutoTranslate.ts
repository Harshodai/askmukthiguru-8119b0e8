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
 * Uses MyMemory free API (https://api.mymemory.translated.net) — no API key
 * needed, supports all 22 scheduled Indian languages + English.
 * Daily limit: 5,000 words (more than enough for a spiritual chat session).
 *
 * The hook caches translations in a session-scoped Map to avoid re-translating
 * identical strings (e.g., repeated "Tell me more" clicks).
 *
 * FAIL-SAFE
 * ─────────
 * All translation failures return the original text unchanged so the chat
 * never breaks. Errors are silently logged (no UI crash).
 */

import { useCallback, useRef, useState } from 'react';

const MYMEMORY_BASE = 'https://api.mymemory.translated.net/get';
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
        // Evict oldest entry
        const first = map.keys().next().value;
        if (first !== undefined) map.delete(first);
      }
      map.set(k, v);
    },
    get size() { return map.size; },
  };
}

async function myMemoryTranslate(
  text: string,
  fromCode: string,
  toCode: string,
): Promise<string> {
  if (!text.trim()) return text;
  const url = new URL(MYMEMORY_BASE);
  url.searchParams.set('q', text);
  url.searchParams.set('langpair', `${fromCode}|${toCode}`);
  const res = await fetch(url.toString(), { signal: AbortSignal.timeout(6000) });
  if (!res.ok) throw new Error(`MyMemory ${res.status}`);
  const json = await res.json() as {
    responseData: { translatedText: string; match: number };
    responseStatus: number;
  };
  if (json.responseStatus !== 200 && json.responseStatus !== 206) {
    throw new Error(`MyMemory status ${json.responseStatus}`);
  }
  const translated = json.responseData.translatedText;
  if (!translated || translated === text) return text;
  return translated;
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

/**
 * Maps our language codes to BCP-47 tags that MyMemory understands.
 * Most codes are the same; a few need remapping.
 */
const TO_MYMEMORY: Record<string, string> = {
  en:  'en-GB',
  hi:  'hi-IN',
  bn:  'bn-IN',
  te:  'te-IN',
  mr:  'mr-IN',
  ta:  'ta-IN',
  ur:  'ur-PK',
  gu:  'gu-IN',
  kn:  'kn-IN',
  ml:  'ml-IN',
  or:  'or-IN',
  pa:  'pa-IN',
  as:  'as-IN',
  mai: 'mai-IN',
  sa:  'sa-IN',
  ks:  'ks-IN',
  ne:  'ne-NP',
  sd:  'sd-IN',
  kok: 'kok-IN',
  doi: 'doi-IN',
  mni: 'mni-IN',
  sat: 'sat-IN',
  brx: 'brx-IN',
};

export function useAutoTranslate({
  languageCode,
  autoTranslateResponse = false,
}: UseAutoTranslateOptions): UseAutoTranslateResult {
  const [isTranslating, setIsTranslating] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const cacheRef = useRef<TranslationCache>(makeCache());
  const isActive = languageCode !== 'en';
  const langTag = TO_MYMEMORY[languageCode] ?? languageCode;

  const translateToEnglish = useCallback(async (text: string): Promise<string> => {
    if (!isActive || !text.trim()) return text;
    const cacheKey = `to_en:${languageCode}:${text}`;
    const cached = cacheRef.current.get(cacheKey);
    if (cached) return cached;

    setIsTranslating(true);
    setLastError(null);
    try {
      const result = await myMemoryTranslate(text, langTag, 'en-GB');
      cacheRef.current.set(cacheKey, result);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(msg);
      console.warn('[AutoTranslate] Failed to translate to English:', msg);
      return text; // fail-safe: return original
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
      const result = await myMemoryTranslate(text, 'en-GB', langTag);
      cacheRef.current.set(cacheKey, result);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(msg);
      console.warn('[AutoTranslate] Failed to translate from English:', msg);
      return text; // fail-safe
    } finally {
      setIsTranslating(false);
    }
  }, [isActive, autoTranslateResponse, languageCode, langTag]);

  return { translateToEnglish, translateFromEnglish, isTranslating, isActive, lastError };
}
