import { describe, expect, it } from 'vitest';
import { deriveBrainUnlock } from '../lib/secondBrainApi';

describe('secondBrainApi - deriveBrainUnlock', () => {
  it('returns undefined if passphrase is empty or undefined', async () => {
    expect(await deriveBrainUnlock(undefined)).toBeUndefined();
    expect(await deriveBrainUnlock('')).toBeUndefined();
  });

  it('matches backend PBKDF2-HMAC-SHA256 cryptographic parity with 600,000 iterations', async () => {
    // Backend: hashlib.pbkdf2_hmac("sha256", b"testpass", b"second_brain_vault_unlock_salt", 600000).hex()
    const expected = '55adc9f56ca9c20c3d4031164e5c7da29b7bedc8132e3dbdb4395fd39b91b170';
    const derived = await deriveBrainUnlock('testpass');
    expect(derived).toBe(expected);
  });
});
