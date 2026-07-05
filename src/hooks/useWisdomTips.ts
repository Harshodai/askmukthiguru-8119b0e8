/**
 * Wisdom tips shown while an answer is generating.
 *
 * Fetches `GET /api/teachings/tips` from the same backend base the chat uses,
 * caches the payload in localStorage for 7 days, and degrades silently to a
 * curated static list when the endpoint is unavailable — the waiting UI must
 * work identically either way.
 */

import { useEffect, useRef, useState } from 'react';

import { getAIConfig } from '@/lib/chat/config';

export interface WisdomTip {
  id: string;
  text: string;
  source: string;
  teacher: string;
}

const STORAGE_KEY = 'mukthi_wisdom_tips_v1';
const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const ROTATE_INTERVAL_MS = 8000;
const SHOW_DELAY_MS = 2000;
const FETCH_TIMEOUT_MS = 4000;

const TEACHER = 'Sri Preethaji & Sri Krishnaji';

/** Paraphrased core teachings — used whenever the tips endpoint is unreachable. */
export const STATIC_FALLBACK_TIPS: WisdomTip[] = [
  { id: 'static-1', source: 'curated', teacher: TEACHER, text: 'In every moment you live from either a beautiful state or a suffering state. Simply noticing which one you are in begins the shift.' },
  { id: 'static-2', source: 'curated', teacher: TEACHER, text: 'Suffering grows from obsessive self-engagement. When attention softens away from “me and my story”, calm arises on its own.' },
  { id: 'static-3', source: 'curated', teacher: TEACHER, text: 'Do not battle an inner state. Observe it with unhurried attention, and it loosens its grip.' },
  { id: 'static-4', source: 'curated', teacher: TEACHER, text: 'A calm mind is not an empty mind — it is a mind no longer at war with what is.' },
  { id: 'static-5', source: 'curated', teacher: TEACHER, text: 'Connection dissolves anxiety. When you feel part of something larger, clarity follows naturally.' },
  { id: 'static-6', source: 'curated', teacher: TEACHER, text: 'Your inner state silently shapes every decision you make. Tend the state first; right action follows.' },
  { id: 'static-7', source: 'curated', teacher: TEACHER, text: 'Gratitude is not a technique — it is what remains when the noise of wanting quiets down.' },
  { id: 'static-8', source: 'curated', teacher: TEACHER, text: 'The breath is a doorway: slow it gently, and the mind follows it into stillness.' },
  { id: 'static-9', source: 'curated', teacher: TEACHER, text: 'Truth is not something you acquire; it is what you see when you stop looking away from this moment.' },
  { id: 'static-10', source: 'curated', teacher: TEACHER, text: 'Transformation is not becoming someone else — it is meeting this moment without resistance.' },
];

interface CachedTips {
  fetchedAt: number;
  tips: WisdomTip[];
}

const loadCachedTips = (): WisdomTip[] | null => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: CachedTips = JSON.parse(raw);
    if (!parsed.tips?.length || Date.now() - parsed.fetchedAt > CACHE_TTL_MS) return null;
    return parsed.tips;
  } catch {
    return null;
  }
};

const saveCachedTips = (tips: WisdomTip[]): void => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ fetchedAt: Date.now(), tips } satisfies CachedTips));
  } catch {
    // storage full/blocked — non-fatal
  }
};

const backendBaseUrl = (): string => {
  const endpoint = getAIConfig().endpoint || '';
  return endpoint.replace(/\/api\/chat\/?$/, '').replace(/\/functions\/v1\/guru-chat\/?$/, '');
};

export const fetchWisdomTips = async (): Promise<WisdomTip[]> => {
  const cached = loadCachedTips();
  if (cached) return cached;

  const base = backendBaseUrl();
  try {
    const res = await fetch(`${base}/api/teachings/tips`, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!res.ok) throw new Error(`tips endpoint ${res.status}`);
    const data = await res.json();
    const tips: WisdomTip[] = Array.isArray(data?.tips) && data.tips.length ? data.tips : STATIC_FALLBACK_TIPS;
    saveCachedTips(tips);
    return tips;
  } catch {
    return STATIC_FALLBACK_TIPS;
  }
};

/**
 * Returns the tip to display while `active` is true, rotating every 8s.
 * Waits 2s before showing anything so instant answers never flash a tip.
 */
export const useWisdomTips = (active: boolean): WisdomTip | null => {
  const [tip, setTip] = useState<WisdomTip | null>(null);
  const tipsRef = useRef<WisdomTip[]>([]);
  const indexRef = useRef(0);

  useEffect(() => {
    if (!active) {
      setTip(null);
      return;
    }
    let cancelled = false;
    let rotateTimer: number | undefined;

    const showTimer = window.setTimeout(async () => {
      if (tipsRef.current.length === 0) tipsRef.current = await fetchWisdomTips();
      if (cancelled || tipsRef.current.length === 0) return;
      indexRef.current = Math.floor(Math.random() * tipsRef.current.length);
      setTip(tipsRef.current[indexRef.current]);
      rotateTimer = window.setInterval(() => {
        indexRef.current = (indexRef.current + 1) % tipsRef.current.length;
        setTip(tipsRef.current[indexRef.current]);
      }, ROTATE_INTERVAL_MS);
    }, SHOW_DELAY_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(showTimer);
      if (rotateTimer !== undefined) window.clearInterval(rotateTimer);
    };
  }, [active]);

  return tip;
};
