/**
 * Fetch wrapper with exponential backoff. Retries on 429 + 5xx-ish so the UI
 * heals itself when Railway/OpenRouter is momentarily busy. Respects
 * `Retry-After` when the server sets it.
 */
export async function fetchWithRetry(
  url: string,
  options: RequestInit,
  maxAttempts = 3,
  signal?: AbortSignal,
): Promise<Response> {
  const RETRYABLE = new Set([429, 502, 503, 504]);

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

    const retryAfter = res.headers.get('Retry-After');
    const delay = retryAfter ? parseInt(retryAfter, 10) * 1000 : backoffMs(attempt);
    await sleep(delay, signal);
  }
  throw new Error('fetchWithRetry exhausted');
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
