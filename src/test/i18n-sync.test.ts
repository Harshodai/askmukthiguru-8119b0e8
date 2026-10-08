/**
 * Guards the "English is the single source of truth" i18n sync tooling.
 * Pure-function tests (no network) plus an on-disk check that every shipped
 * locale is in sync with en.json and the committed source-hash manifest.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import * as lib from '../../scripts/i18n/lib.mjs';

const ROOT = join(__dirname, '..', '..');
const read = (p: string) => JSON.parse(readFileSync(join(ROOT, p), 'utf8'));

describe('i18n sync helpers', () => {
  const en = { 'a.hello': 'Hello {{name}}', 'a.call': 'Call 14416 now', 'a.quote': 'Be still and know.', 'a.ok': 'OK' };
  const hashes = Object.fromEntries(Object.entries(en).map(([k, v]) => [k, lib.hashValue(v)]));

  it('accepts a faithful translation', () => {
    expect(lib.validateTranslation('a.hello', en['a.hello'], 'नमस्ते {{name}}')).toBeNull();
  });
  it('rejects dropped placeholders, changed helpline digits and leftover English', () => {
    expect(lib.validateTranslation('a.hello', en['a.hello'], 'नमस्ते')).toBe('placeholder mismatch');
    expect(lib.validateTranslation('a.call', en['a.call'], 'अभी 14417 पर कॉल करें')).toMatch(/digits/);
    expect(lib.validateTranslation('a.hello', en['a.hello'], en['a.hello'])).toBe('still English');
    expect(lib.validateTranslation('a.hello', en['a.hello'], '  ')).toBe('empty');
  });
  it('detects missing, extra and stale keys, and never re-translates protected quotes', () => {
    const d = lib.diagnoseLocale({ ...en, 'a.new': 'New text' }, { 'a.hello': 'x {{name}}', 'a.call': 'y 14416', 'a.quote': 'q', 'a.gone': 'z' }, hashes);
    expect(d.missing).toEqual(expect.arrayContaining(['a.ok', 'a.new']));
    expect(d.extra).toEqual(['a.gone']);
    expect(lib.keysToTranslate(d)).not.toContain('a.quote');
    const edited = lib.diagnoseLocale({ ...en, 'a.hello': 'Hi {{name}}!' }, { 'a.hello': 'x {{name}}', 'a.call': 'y 14416', 'a.quote': 'q', 'a.ok': 'ठीक' }, hashes);
    expect(edited.stale).toEqual(['a.hello']);
  });
  it('patches in place: keeps existing order, appends new keys, prunes deleted ones', () => {
    const nested = { z: { b: 'B', a: 'A' }, only: { gone: 'x' } };
    lib.patchNested(nested, { 'z.a': 'A2', 'z.c': 'C', 'n.k': 'K' }, ['only.gone']);
    expect(nested).toEqual({ z: { b: 'B', a: 'A2', c: 'C' }, n: { k: 'K' } });
    expect(Object.keys(nested.z)).toEqual(['b', 'a', 'c']);
  });
});

describe('shipped locales are synced from English', () => {
  const enFlat = lib.flatten(read('src/locales/en.json'));
  const { hashes } = read('scripts/i18n/source-hashes.json');
  for (const l of lib.TARGET_LOCALES as string[]) {
    it(`${l}: no missing, extra, stale, English or broken values`, () => {
      const d = lib.diagnoseLocale(enFlat, lib.flatten(read(`src/locales/${l}.json`)), hashes);
      expect(d).toEqual({ missing: [], extra: [], stale: [], leftover: [], invalid: [] });
    });
  }
});
