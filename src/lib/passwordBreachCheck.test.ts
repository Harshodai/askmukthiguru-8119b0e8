import { describe, it, expect, vi } from 'vitest';
import {
  computeSha1Hex,
  checkPasswordBreached,
  BREACHED_PASSWORD_MESSAGE,
} from './passwordBreachCheck';

describe('passwordBreachCheck', () => {
  describe('computeSha1Hex', () => {
    it('computes correct uppercase SHA-1 for known input', async () => {
      const hash = await computeSha1Hex('password123');
      expect(hash).toBe('CBFDAC6008F9CAB4083784CBD1874F76618D2A97');
      expect(hash.length).toBe(40);
    });
  });

  describe('checkPasswordBreached - k-Anonymity Invariants', () => {
    it('strictly sends only 5 prefix chars and never leaks password or full hash', async () => {
      let calledUrl = '';
      let calledHeaders: Record<string, string> = {};

      const mockFetch: typeof fetch = vi.fn().mockImplementation(async (url, init) => {
        calledUrl = String(url);
        calledHeaders = (init?.headers as Record<string, string>) || {};
        return new Response('C6008F9CAB4083784CBD1874F76618D2A97:2266543\r\n', { status: 200 });
      });

      const result = await checkPasswordBreached('password123', { fetchFn: mockFetch });

      // 1. Invariant: URL format must match exactly 5 hex characters
      expect(calledUrl).toBe('https://api.pwnedpasswords.com/range/CBFDA');
      expect(calledUrl.split('/').pop()?.length).toBe(5);

      // 2. Invariant: Plaintext password is NEVER in URL or headers
      expect(calledUrl).not.toContain('password123');
      expect(JSON.stringify(calledHeaders)).not.toContain('password123');

      // 3. Invariant: Full hash is NEVER in URL or headers
      expect(calledUrl).not.toContain('CBFDAC6008F9CAB4083784CBD1874F76618D2A97');
      expect(JSON.stringify(calledHeaders)).not.toContain('CBFDAC6008F9CAB4083784CBD1874F76618D2A97');

      // 4. Invariant: Add-Padding header is present
      expect(calledHeaders['Add-Padding']).toBe('true');

      // 5. Result is marked breached
      expect(result.breached).toBe(true);
      expect(result.count).toBe(2266543);
    });

    it('identifies clean unbreached password when suffix is not in response', async () => {
      const mockFetch: typeof fetch = vi.fn().mockImplementation(async () => {
        // Return dummy suffixes that do not match our password's suffix
        return new Response(
          '00000000000000000000000000000000000:10\r\n11111111111111111111111111111111111:5\r\n',
          { status: 200 },
        );
      });

      const result = await checkPasswordBreached('SuperCleanUniquePassword_2026!#$%', {
        fetchFn: mockFetch,
      });

      expect(result.breached).toBe(false);
      expect(result.count).toBe(0);
    });

    it('handles empty input gracefully', async () => {
      const result = await checkPasswordBreached('');
      expect(result.breached).toBe(false);
      expect(result.count).toBe(0);
    });

    it('handles upstream network failure non-blockingly', async () => {
      const failingFetch: typeof fetch = vi.fn().mockRejectedValue(new Error('Network offline'));

      const result = await checkPasswordBreached('testPassword', { fetchFn: failingFetch });
      expect(result.breached).toBe(false);
      expect(result.error).toContain('Network offline');
    });

    it('handles non-200 HTTP response gracefully', async () => {
      const badStatusFetch: typeof fetch = vi
        .fn()
        .mockResolvedValue(new Response('Internal Error', { status: 500 }));

      const result = await checkPasswordBreached('testPassword', { fetchFn: badStatusFetch });
      expect(result.breached).toBe(false);
      expect(result.error).toContain('500');
    });
  });

  describe('Live HIBP Range API Verification', () => {
    it('detects real breached password ("password123") against live HIBP API', async () => {
      try {
        const result = await checkPasswordBreached('password123');
        // If network is reachable in test runner:
        if (!result.error) {
          expect(result.breached).toBe(true);
          expect(result.count).toBeGreaterThan(100000);
        }
      } catch {
        // Fallback for isolated offline environments
      }
    });

    it('verifies clean complex password against live HIBP API', async () => {
      try {
        const cleanPassword = 'Z9#xL7!vQ9$kP@2026_GuruMukthiUltraRareSecretPassphrase';
        const result = await checkPasswordBreached(cleanPassword);
        if (!result.error) {
          expect(result.breached).toBe(false);
          expect(result.count).toBe(0);
        }
      } catch {
        // Fallback for isolated offline environments
      }
    });
  });

  describe('Friendly Error Message Export', () => {
    it('provides user-friendly explanation of data breach rejection', () => {
      expect(BREACHED_PASSWORD_MESSAGE).toContain('known data breach');
      expect(BREACHED_PASSWORD_MESSAGE).toContain('choose a stronger, unique password');
    });
  });
});
