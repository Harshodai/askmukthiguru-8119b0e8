/**
 * NEW-LOV-03: UI copy that Lovable (or anyone) adds must keep the voice rules.
 *
 * - The teachers' words appear only as verbatim spans. UI copy must never speak
 *   in a teacher's first person ("I invite you", "When I speak of").
 * - Promotional copy must not promise what the product does not do (T6-10,
 *   PRD-010): the teaching lane answers with a clip or a static abstain, not as a
 *   conversational "AI companion".
 *
 * No copy was rewritten here. Promo strings that still say "AI companion" are
 * listed in KNOWN_PROMO_CLAIMS as a shrink-only ratchet; the owner decides the
 * rewording and native speakers translate it (human gates).
 */
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = process.cwd();
const LOCALES = join(ROOT, 'src', 'locales');
const LANDING = join(ROOT, 'src', 'components', 'landing');

const TEACHER_FIRST_PERSON = [
  /\bI invite you\b/i,
  /\bwhen I speak of\b/i,
  /\bI (?:teach|guide) you\b/i,
  /\bin my (?:teachings?|discourses?)\b/i,
];

// Keys whose value is promotion, not a disclaimer. A disclaimer that says
// "this is an AI companion" is an honest label and is allowed.
const PROMO_KEY = /(?:^|\.)(?:tagline|welcomeDesc|heading|subtitle|description)$/;
const PROMISE = /\bAI companion\b|\bconversational (?:companion|guide|AI)\b/i;

/** Locale key paths that still promise a companion. Shrink only; never add. */
const KNOWN_PROMO_CLAIMS = new Set<string>([
  'en.json:guides.aiSpiritualCompanion.breathwork.heading',
]);

function flatten(node: unknown, prefix = ''): Array<[string, string]> {
  if (typeof node === 'string') return [[prefix, node]];
  if (node && typeof node === 'object') {
    return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
      flatten(v, prefix ? `${prefix}.${k}` : k),
    );
  }
  return [];
}

const localeFiles = readdirSync(LOCALES).filter((f) => f.endsWith('.json'));
const strings = localeFiles.flatMap((file) =>
  flatten(JSON.parse(readFileSync(join(LOCALES, file), 'utf8'))).map(
    ([key, value]) => ({ file, key, value }) as const,
  ),
);

describe('voice rules for UI copy (NEW-LOV-03)', () => {
  it('the patterns catch what they are meant to catch', () => {
    expect(TEACHER_FIRST_PERSON.some((re) => re.test('I invite you to sit in silence.'))).toBe(true);
    expect(TEACHER_FIRST_PERSON.some((re) => re.test('When I speak of the beautiful state'))).toBe(true);
    expect(TEACHER_FIRST_PERSON.some((re) => re.test('Sri Krishnaji invites you to sit.'))).toBe(false);
    expect(PROMO_KEY.test('landing.hero.tagline')).toBe(true);
    expect(PROMO_KEY.test('landing.safety.disclaimer')).toBe(false);
    expect(PROMISE.test('Your spiritual AI companion')).toBe(true);
  });

  it('scans every locale file', () => {
    expect(localeFiles.length).toBeGreaterThanOrEqual(7);
    expect(strings.length).toBeGreaterThan(1000);
  });

  it('no locale string speaks in a teacher\'s first person', () => {
    const hits = strings
      .filter((s) => TEACHER_FIRST_PERSON.some((re) => re.test(s.value)))
      .map((s) => `${s.file}:${s.key}`);
    expect(hits).toEqual([]);
  });

  it('no landing component text speaks in a teacher\'s first person', () => {
    const hits: string[] = [];
    for (const file of readdirSync(LANDING).filter((f) => f.endsWith('.tsx'))) {
      const text = readFileSync(join(LANDING, file), 'utf8');
      if (TEACHER_FIRST_PERSON.some((re) => re.test(text))) hits.push(file);
    }
    expect(hits).toEqual([]);
  });

  it('promotional copy does not promise a conversational companion (known items only)', () => {
    const found = new Set(
      strings
        .filter((s) => PROMO_KEY.test(s.key) && PROMISE.test(s.value))
        .map((s) => `${s.file}:${s.key}`),
    );
    const added = [...found].filter((k) => !KNOWN_PROMO_CLAIMS.has(k)).sort();
    const stale = [...KNOWN_PROMO_CLAIMS].filter((k) => !found.has(k)).sort();
    expect(added, 'new promo claim; reword it or ask the owner').toEqual([]);
    expect(stale, 'fixed; delete it from KNOWN_PROMO_CLAIMS').toEqual([]);
  });
});
