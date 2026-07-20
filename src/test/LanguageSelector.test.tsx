import { describe, it, expect } from 'vitest';
import { LANGUAGES } from '@/components/chat/LanguageSelector';

describe('LanguageSelector — language list', () => {
  it('exposes the dynamically configured languages based on i18n translation resources (14 total)', () => {
    expect(LANGUAGES.length).toBe(14);
  });

  it('has English first as the default', () => {
    expect(LANGUAGES[0].code).toBe('en');
  });

  it('includes the 14 supported translation languages', () => {
    const codes = LANGUAGES.map((l) => l.code);
    expect(codes).toContain('en');
    expect(codes).toContain('hi');
    expect(codes).toContain('te');
    expect(codes).toContain('kn');
    expect(codes).toContain('ta');
    expect(codes).toContain('mr');
    expect(codes).toContain('bn');
    expect(codes).toContain('gu');
    expect(codes).toContain('ml');
    expect(codes).toContain('ur');
    expect(codes).toContain('or');
    expect(codes).toContain('pa');
    expect(codes).toContain('as');
    expect(codes).toContain('sa');
  });

  it('every language has a BCP-47 tag', () => {
    LANGUAGES.forEach((lang) => {
      expect(lang.bcp47).toMatch(/^[a-z]{2,3}-[A-Z]{2}$/);
    });
  });

  it('every language has a native script name', () => {
    LANGUAGES.forEach((lang) => {
      expect(lang.native.length).toBeGreaterThan(0);
    });
  });

  it('codes are unique', () => {
    const codes = LANGUAGES.map((l) => l.code);
    expect(new Set(codes).size).toBe(codes.length);
  });
});
