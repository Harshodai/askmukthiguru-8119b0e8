import { describe, expect, it, vi } from 'vitest';
import { QUOTA_EVENT, parseQuota, publishQuota } from '@/lib/chat/quotaEvents';

describe('quota events (UX-011)', () => {
  it('parses the backend quota object', () => {
    expect(parseQuota({ remaining: 4, limit: 5 })).toEqual({ remaining: 4, limit: 5 });
  });
  it('rejects anything that is not two numbers (signed-in users get no quota field)', () => {
    expect(parseQuota(undefined)).toBeNull();
    expect(parseQuota({ remaining: '4', limit: 5 })).toBeNull();
    expect(parseQuota({ remaining: 1, limit: 0 })).toBeNull();
  });
  it('clamps a negative remaining to 0', () => {
    expect(parseQuota({ remaining: -2, limit: 5 })).toEqual({ remaining: 0, limit: 5 });
  });
  it('publishes only a valid quota', () => {
    const seen = vi.fn();
    window.addEventListener(QUOTA_EVENT, seen);
    publishQuota(undefined);
    expect(seen).not.toHaveBeenCalled();
    publishQuota({ remaining: 3, limit: 5 });
    expect(seen).toHaveBeenCalledTimes(1);
    window.removeEventListener(QUOTA_EVENT, seen);
  });
});

describe('UX-011 locale strings', () => {
  const files = import.meta.glob('../locales/*.json', { eager: true }) as Record<
    string,
    { default: { chat?: Record<string, string> } }
  >;
  it('every locale has the counter and reset strings with their placeholders', () => {
    const entries = Object.entries(files);
    expect(entries.length).toBeGreaterThanOrEqual(7);
    for (const [path, mod] of entries) {
      const chat = mod.default.chat ?? {};
      expect(chat.quotaLeft, path).toContain('{{remaining}}');
      expect(chat.quotaLeft, path).toContain('{{limit}}');
      expect(chat.quotaResetsIn, path).toContain('{{count}}');
    }
  });
});
