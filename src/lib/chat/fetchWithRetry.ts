/**
 * Fetch wrapper with exponential backoff. Retries on 429 + 5xx-ish so the UI
 * heals itself when Railway/OpenRouter is momentarily busy. Respects
 * `Retry-After` when the server sets it.
 */
import { INDIA_CRISIS_LINES } from '@/lib/crisisHelplines';

export const DEFAULT_RETRYABLE_STATUSES = [429, 502, 503, 504] as const;

/**
 * Backpressure only. The non-streaming chat POST runs for up to 120s, so
 * retrying a 502/504 there costs the seeker minutes of silence for a request
 * that already burned its budget. A 503 from the admission semaphore
 * (max_concurrent_chat) comes back immediately with Retry-After and is the
 * one status worth re-sending.
 */
export const BACKPRESSURE_ONLY_STATUSES = [503] as const;

/**
 * Last-resort shedding copy (RP-A2, review P3-7). Owner ruling 2026-10-13:
 * name only Tele-MANAS (call-verified) and Emergency 112 (national emergency
 * number). The other registry lines stay available to answered turns; they
 * are not call-verified, so they do not belong in ungated last-resort copy.
 */
const SHEDDING_LINES = INDIA_CRISIS_LINES.filter((line) =>
  ['Tele-MANAS', 'Emergency'].includes(line.label),
);

/**
 * Final-503 copy (RP-A2). When retries are exhausted and the server is still
 * shedding load, the seeker sees helpline text — never a generic error. The
 * numbers are rendered from the crisis registry (config/helplines.yaml via
 * `@/lib/crisisHelplines`), never retyped, so they cannot drift from it.
 */
export const SERVER_BUSY_HELPLINE_MESSAGE =
  'AskMukthiGuru is very busy right now. Please try again in a moment. ' +
  `If you are in distress, help is available now: ${SHEDDING_LINES.map(
    (line) => `${line.label} ${line.display} (${line.hours})`,
  ).join(', ')}.`;

export async function fetchWithRetry(
  url: string,
  options: RequestInit,
  maxAttempts = 3,
  signal?: AbortSignal,
  retryOn: readonly number[] = DEFAULT_RETRYABLE_STATUSES,
): Promise<Response> {
  const RETRYABLE = new Set(retryOn);

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');

    let res: Response;
    try {
      res = await fetch(url, { ...options, signal });
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') throw err;
      if (attempt < maxAttempts - 1) {
        await sleep(backoffMs(attempt), signal);
        continue;
      }
      throw err;
    }

    if (!RETRYABLE.has(res.status) || attempt === maxAttempts - 1) return res;

    const retryAfter = res.headers?.get?.('Retry-After') ?? null;
    await sleep(retryDelayMs(retryAfter, attempt), signal);
  }
  throw new Error('fetchWithRetry exhausted');
}

/**
 * Delay before the next attempt (RP-A8). The server randomizes Retry-After
 * across 3-8s; the client adds 0-1s of jitter on the header path so shed
 * clients do not all return on the same second. Pure (takes the header as
 * an argument) so the jitter contract is unit-testable.
 */
export function retryDelayMs(retryAfterHeader: string | null, attempt: number): number {
  if (retryAfterHeader != null) {
    // Review P2-2: a malformed header yields NaN, and sleep(NaN) fires
    // immediately — a shedding server would be hammered with zero-delay
    // retries. Fall back to backoff on anything non-finite.
    const parsed = parseInt(retryAfterHeader, 10) * 1000;
    if (Number.isFinite(parsed) && parsed >= 0) return parsed + Math.random() * 1000;
  }
  return backoffMs(attempt);
}

function backoffMs(attempt: number): number {
  return Math.min(1000 * 2 ** attempt + Math.random() * 400, 20_000);
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new DOMException('Aborted', 'AbortError'));
    });
  });
}
