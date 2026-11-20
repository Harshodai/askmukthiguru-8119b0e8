/**
 * Every i18n key used in src/ must exist in en.json (2026-11-19 never-again guard).
 * A key that only has an inline English default is never translated: i18n:sync
 * reads en.json alone, so a Hindi seeker sees English. The existing backlog is
 * frozen in fixtures/i18n-missing-baseline.json and may only shrink.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const SRC = join(__dirname, '..');
const flat = (o: Record<string, unknown>, p = '', out: Record<string, unknown> = {}) => {
  for (const [k, v] of Object.entries(o)) {
    const key = p ? `${p}.${k}` : k;
    if (v && typeof v === 'object') flat(v as Record<string, unknown>, key, out);
    else out[key] = v;
  }
  return out;
};
const walk = (d: string): string[] =>
  readdirSync(d).flatMap((f) => {
    const p = join(d, f);
    if (statSync(p).isDirectory()) return f === 'test' || f === 'locales' ? [] : walk(p);
    return /\.(tsx?|jsx?)$/.test(f) && !/\.test\./.test(f) ? [p] : [];
  });

function extractCallArgs(str: string, startIndex: number): string {
  let depth = 1;
  let i = startIndex;
  while (i < str.length && depth > 0) {
    const ch = str[i];
    if (ch === '(') depth++;
    else if (ch === ')') depth--;
    else if (ch === '"' || ch === "'" || ch === '`') {
      const quote = ch;
      i++;
      while (i < str.length && str[i] !== quote) {
        if (str[i] === '\\') i++;
        i++;
      }
    }
    i++;
  }
  return str.slice(startIndex, i - 1);
}

function missingKeys(): string[] {
  const en = flat(JSON.parse(readFileSync(join(SRC, 'locales', 'en.json'), 'utf8')));
  const found = new Set<string>();
  const re = /\bt\(\s*['"`]([a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+)['"`]/g;
  for (const file of walk(SRC)) {
    const content = readFileSync(file, 'utf8');
    for (const m of content.matchAll(re)) {
      const key = m[1];
      const args = extractCallArgs(content, (m.index ?? 0) + m[0].length);
      const isCountCall = /\bcount\s*:/.test(args);
      if (isCountCall) {
        const hasPlurals = en[`${key}_one`] !== undefined && en[`${key}_other`] !== undefined;
        if (en[key] === undefined && !hasPlurals) {
          found.add(key);
        }
      } else {
        if (en[key] === undefined) {
          found.add(key);
        }
      }
    }
  }
  return [...found].sort();
}

describe('i18n keys exist in en.json', () => {
  const baseline: string[] = JSON.parse(readFileSync(join(SRC, 'test', 'fixtures', 'i18n-missing-baseline.json'), 'utf8'));
  it('no NEW key ships without an en.json entry', () => {
    const fresh = missingKeys().filter((k) => !baseline.includes(k));
    expect(fresh, 'add these keys to src/locales/en.json, then npm run i18n:sync').toEqual([]);
  });
  it('the baseline lists only keys that are still missing (it may only shrink)', () => {
    const missing = new Set(missingKeys());
    expect(baseline.filter((k) => !missing.has(k)), 'remove fixed keys from the baseline').toEqual([]);
  });
});
