/**
 * Lightweight in-memory LRU response cache with TTL.
 * Used to skip redundant API calls for repeated/identical queries.
 */

interface CacheEntry {
  content: string;
  ts: number;
  citations?: string[];
}

const MAX_ENTRIES = 50;
const TTL_MS = 5 * 60 * 1000; // 5 minutes

const cache = new Map<string, CacheEntry>();

/**
 * Simple hash of the last N messages to use as cache key.
 * Not cryptographic — just needs to be deterministic and fast.
 */
export const hashMessages = (messages: { role: string; content: string }[], count = 3): string => {
  const tail = messages.slice(-count);
  let hash = 0;
  const str = tail.map((m) => `${m.role}:${m.content}`).join('|');
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash + char) | 0;
  }
  return hash.toString(36);
};

export const getCachedResponse = (key: string): CacheEntry | null => {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.ts > TTL_MS) {
    cache.delete(key);
    return null;
  }
  // Move to end (LRU refresh)
  cache.delete(key);
  cache.set(key, entry);
  return entry;
};

export const setCachedResponse = (
  key: string,
  content: string,
  citations?: string[],
): void => {
  // Evict oldest if at capacity
  if (cache.size >= MAX_ENTRIES) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) {
      cache.delete(oldest);
    }
  }
  cache.set(key, { content, ts: Date.now(), citations });
};

export const clearResponseCache = (): void => {
  cache.clear();
};
