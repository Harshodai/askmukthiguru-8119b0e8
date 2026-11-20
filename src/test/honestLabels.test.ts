/**
 * Honest provenance labels (2026-11-19). The English locale once overrode the
 * component's honest default "Unverified attribution" with "General Spiritual
 * Context", and described a static abstain as an offered "contemplation".
 * Labels a seeker uses to judge teacher words must say what is (not) verified.
 */
import { describe, it, expect } from 'vitest';
import en from '../locales/en.json';

describe('provenance labels stay honest', () => {
  const tc = (en as { chat: { teachingContext: Record<string, string> } }).chat.teachingContext;
  it('an unverified attribution is called unverified', () => {
    expect(tc.unverifiedBadge).toBe('Unverified attribution');
    expect(tc.unverifiedNote.toLowerCase()).toContain('unverified');
  });
  it('an abstain never claims something was offered', () => {
    expect(tc.noDirectDiscourse).toBe('No direct discourse match');
    expect(tc.abstainedDescription).not.toMatch(/offered|contemplation/i);
  });
  it('no badge reuses a reassuring phrase for unverified content', () => {
    for (const key of ['unverifiedBadge', 'unverifiedNote', 'abstainedDescription']) {
      expect(tc[key]).not.toMatch(/General Spiritual Context|Verified Sacred/i);
    }
  });
});

describe('translated provenance labels stay distinct from "verified"', () => {
  const locales = import.meta.glob('../locales/*.json', { eager: true }) as Record<string, { default: Record<string, any> }>;
  for (const [path, mod] of Object.entries(locales)) {
    const chat = (mod.default ?? mod).chat ?? {};
    it(`${path}: unverified/related labels never equal the verified label`, () => {
      const tc = chat.teachingContext ?? {};
      const gt = chat.guruTeaching ?? {};
      if (tc.unverifiedBadge && tc.verifiedBadge) expect(tc.unverifiedBadge).not.toBe(tc.verifiedBadge);
      if (gt.unverifiedBadge && gt.verifiedBadge) expect(gt.unverifiedBadge).not.toBe(gt.verifiedBadge);
      if (gt.personalizedNote && gt.verifiedBadge) expect(gt.personalizedNote).not.toBe(gt.verifiedBadge);
    });
  }
});

