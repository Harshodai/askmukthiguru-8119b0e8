import { describe, it, expect } from 'vitest';
import { isSafeRelativePath } from '@/lib/safeRedirect';

describe('isSafeRelativePath', () => {
  it('accepts same-origin relative paths', () => {
    expect(isSafeRelativePath('/chat')).toBe(true);
    expect(isSafeRelativePath('/profile?tab=memory')).toBe(true);
  });

  it('rejects absolute, protocol-relative and credential-bearing targets', () => {
    const bad = [
      'https://evil.example',
      '//evil.example',
      '/@evil',
      '/a\\b',
      '/a@b',
      '/x://y',
      '',
      null,
      undefined,
    ];
    for (const url of bad) {
      expect(isSafeRelativePath(url)).toBe(false);
    }
  });
});
