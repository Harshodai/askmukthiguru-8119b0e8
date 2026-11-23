import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearWhatsAppChallenge, normalizeWhatsAppStatus, readWhatsAppChallenge, rememberWhatsAppChallenge, safeWhatsAppReturnUrl, whatsappRequest } from '@/lib/whatsappConnection';

vi.mock('@/lib/backendUrl', () => ({ BACKEND_URL: 'https://backend.test' }));

describe('WhatsApp private challenges and return destinations', () => {
  beforeEach(() => sessionStorage.clear());

  it('expires a retained challenge at exactly 15 minutes', () => {
    const code = 'private_challenge_123456789';
    expect(rememberWhatsAppChallenge(code, 1000)).toBe(true);
    expect(readWhatsAppChallenge(1000 + 15 * 60 * 1000 - 1)).toBe(code);
    expect(readWhatsAppChallenge(1000 + 15 * 60 * 1000)).toBe('');
    expect(sessionStorage.getItem('pending_whatsapp_token')).toBeNull();
  });

  it('refuses legacy challenges with no expiration', () => {
    sessionStorage.setItem('pending_whatsapp_token', 'private_challenge_123456789');
    expect(readWhatsAppChallenge()).toBe('');
  });

  it('removes linking return secrets but preserves unrelated navigation', () => {
    rememberWhatsAppChallenge('private_challenge_123456789');
    sessionStorage.setItem('intendedPath', '/link-whatsapp#code=private_challenge_123456789');
    sessionStorage.setItem('auth_redirect_path', '/chat?conversation=123');
    clearWhatsAppChallenge();
    expect(sessionStorage.getItem('pending_whatsapp_token')).toBeNull();
    expect(sessionStorage.getItem('intendedPath')).toBeNull();
    expect(sessionStorage.getItem('auth_redirect_path')).toBe('/chat?conversation=123');
  });

  it.each(['https://evil.test/phish', 'https://wa.me@evil.test/919000000000', 'http://wa.me/919000000000', 'https://wa.me/', 'https://wa.me:444/919000000000', 'javascript:alert(1)'])('rejects unsafe WhatsApp return destination %s', value => {
    expect(safeWhatsAppReturnUrl(value)).toBeNull();
  });

  it('allows only a specific WhatsApp number and a START command', () => {
    expect(safeWhatsAppReturnUrl('https://wa.me/919000000000?text=secret&token=secret')).toBe('https://wa.me/919000000000?text=START');
  });

  it('does not infer consent from missing or nonboolean data', () => {
    const status = normalizeWhatsAppStatus({ linked: true, masked_phone: '+91 *** 000', sync_history_consent: 'true' });
    expect(status.sync_history_consent).toBe(false);
    expect(status.memory_write_consent).toBe(false);
  });

  it('rejects malformed status instead of pretending it is disconnected', () => {
    expect(() => normalizeWhatsAppStatus({ success: true })).toThrow();
    expect(() => normalizeWhatsAppStatus({ linked: true })).toThrow();
  });

  it('does not echo server details that may contain account secrets', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: 'private provider token' }) }));
    await expect(whatsappRequest('status', 'test-session')).rejects.toThrow('WhatsApp connection service is unavailable. Please try again.');
    vi.unstubAllGlobals();
  });
});