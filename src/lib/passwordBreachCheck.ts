/**
 * Mukthi Guru — Free Tier Leaked Password Protection (k-Anonymity)
 * =================================================================
 * Provides breach verification using the HaveIBeenPwned Range API:
 *   https://api.pwnedpasswords.com/range/{first-5-chars-of-SHA1}
 *
 * Security Invariants:
 * 1. The plaintext password is NEVER sent over the network.
 * 2. The full SHA-1 hash is NEVER sent over the network.
 * 3. Only the first 5 hexadecimal characters of the SHA-1 hash (prefix) are sent.
 * 4. The remaining 35 characters (suffix) are matched locally in the client.
 * 5. Free, unauthenticated, rate-limit friendly, and works without Supabase Pro.
 */

export interface BreachCheckResult {
  breached: boolean;
  count: number;
  error?: string;
}

export const BREACHED_PASSWORD_MESSAGE =
  'This password has appeared in a known data breach. For your security, please choose a stronger, unique password.';

/**
 * Compute uppercase SHA-1 hexadecimal string of the provided input using Web Crypto.
 */
export async function computeSha1Hex(text: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hashBuffer = await crypto.subtle.digest('SHA-1', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('').toUpperCase();
}

export interface BreachCheckOptions {
  timeoutMs?: number;
  fetchFn?: typeof fetch;
}

/**
 * Check if a password has been compromised in known data breaches.
 * Uses k-Anonymity: only the first 5 characters of the SHA-1 hash leave the client.
 */
export async function checkPasswordBreached(
  password: string,
  options: BreachCheckOptions = {},
): Promise<BreachCheckResult> {
  if (!password) {
    return { breached: false, count: 0 };
  }

  const { timeoutMs = 5000, fetchFn = fetch } = options;

  try {
    const fullHash = await computeSha1Hex(password);
    if (fullHash.length !== 40) {
      throw new Error(`Unexpected SHA-1 length: ${fullHash.length}`);
    }

    const prefix = fullHash.slice(0, 5);
    const suffix = fullHash.slice(5);

    // Strict invariant: verify prefix length is exactly 5 before any network request
    if (prefix.length !== 5 || prefix.length + suffix.length !== 40) {
      throw new Error('k-Anonymity constraint failed: prefix must be exactly 5 hex characters');
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const url = `https://api.pwnedpasswords.com/range/${prefix}`;
    const response = await fetchFn(url, {
      method: 'GET',
      headers: {
        'Add-Padding': 'true', // Prevents response-length analysis
      },
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!response.ok) {
      console.warn(`[BreachCheck] HIBP API responded with status ${response.status}`);
      return { breached: false, count: 0, error: `API status ${response.status}` };
    }

    const text = await response.text();
    const lines = text.split(/\r?\n/);

    for (const line of lines) {
      if (!line) continue;
      const colonIndex = line.indexOf(':');
      if (colonIndex === -1) continue;

      const lineSuffix = line.slice(0, colonIndex).trim().toUpperCase();
      const countStr = line.slice(colonIndex + 1).trim();

      if (lineSuffix === suffix) {
        const count = parseInt(countStr, 10) || 1;
        return { breached: true, count };
      }
    }

    return { breached: false, count: 0 };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.warn('[BreachCheck] Password breach check encountered an error:', message);
    // Non-blocking fail-open for network errors to prevent denial-of-service on upstream outage
    return { breached: false, count: 0, error: message };
  }
}
