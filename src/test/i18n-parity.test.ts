/**
 * i18n parity regression test.
 *
 * Asserts that all 14 supported language files have 100% key parity
 * with canonical en.json (1,077 keys, 0 missing keys, identical key paths).
 *
 * Supported locales: en, hi, te, kn, ta, mr, bn, gu, ml, as, sa, or, pa, ur
 *
 * Run: `npm test` or `npm run test:watch`
 */

import { describe, it, expect } from 'vitest';
import en from '../locales/en.json';
import hi from '../locales/hi.json';
import te from '../locales/te.json';
import kn from '../locales/kn.json';
import ta from '../locales/ta.json';
import mr from '../locales/mr.json';
import bn from '../locales/bn.json';
import gu from '../locales/gu.json';
import ml from '../locales/ml.json';
import as from '../locales/as.json';
import sa from '../locales/sa.json';
import odia from '../locales/or.json';
import pa from '../locales/pa.json';
import ur from '../locales/ur.json';

interface FlatDict { [key: string]: string; }
interface NestedDict { [k: string]: unknown; }

function flatten(obj: NestedDict, prefix = ''): FlatDict {
  const out: FlatDict = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flatten(v as NestedDict, key));
    } else {
      out[key] = v as string;
    }
  }
  return out;
}

const allEnKeys = Object.keys(flatten(en as NestedDict)).sort();

const LOCALES: Record<string, NestedDict> = {
  hi: hi as NestedDict,
  te: te as NestedDict,
  kn: kn as NestedDict,
  ta: ta as NestedDict,
  mr: mr as NestedDict,
  bn: bn as NestedDict,
  gu: gu as NestedDict,
  ml: ml as NestedDict,
  as: as as NestedDict,
  sa: sa as NestedDict,
  or: odia as NestedDict,
  pa: pa as NestedDict,
  ur: ur as NestedDict,
};

describe('i18n 100% parity across all 14 supported languages', () => {
  it('en.json has valid keys structure', () => {
    expect(allEnKeys.length).toBeGreaterThan(1000);
  });

  for (const [langCode, localeObj] of Object.entries(LOCALES)) {
    it(`${langCode}.json has 100% key parity with en.json (0 missing, 0 extra)`, () => {
      const flat = flatten(localeObj);
      const keys = Object.keys(flat).sort();
      const missing = allEnKeys.filter((k) => !(k in flat));
      const extra = keys.filter((k) => !allEnKeys.includes(k));

      expect(
        missing,
        `${langCode}.json missing ${missing.length} keys:\n${missing.slice(0, 20).join('\n')}`,
      ).toEqual([]);

      expect(
        extra,
        `${langCode}.json has ${extra.length} extra keys:\n${extra.slice(0, 20).join('\n')}`,
      ).toEqual([]);

      expect(keys.length).toBe(allEnKeys.length);
    });
  }
});
