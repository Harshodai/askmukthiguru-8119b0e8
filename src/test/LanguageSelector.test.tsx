import { describe, it, expect } from 'vitest';
import { LANGUAGES } from '@/components/chat/LanguageSelector';

describe('LanguageSelector — language list', () => {
  it('exposes all 22 scheduled Indian languages plus English (23 total)', () => {
    expect(LANGUAGES.length).toBe(23);
  });

  it('has English first as the default', () => {
    expect(LANGUAGES[0].code).toBe('en');
  });

  it('includes the four originally supported languages', () => {
    const codes = LANGUAGES.map((l) => l.code);
    expect(codes).toContain('en');
    expect(codes).toContain('hi');
    expect(codes).toContain('te');
    expect(codes).toContain('ml');
  });

  it('includes the major scheduled Indian languages', () => {
    const codes = LANGUAGES.map((l) => l.code);
    ['bn', 'mr', 'ta', 'ur', 'gu', 'kn', 'or', 'pa', 'as', 'sa'].forEach((c) => {
      expect(codes).toContain(c);
    });
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
