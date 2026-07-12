/**
 * i18n parity regression test.
 *
 * Loads en.json, hi.json, te.json and asserts that no NEW missing user-facing
 * keys have appeared since the baseline snapshot was written.
 *
 * The baseline acknowledges that pre-existing gaps (admin section, etc.) are
 * out of scope — admin console is English-only by design. This test enforces
 * that no NEW user-facing keys are added without the corresponding hi/te
 * translations. When you add a key to en.json, also add it to hi.json and
 * te.json OR extend the baseline.
 *
 * Run: `npm test` or `npm run test:watch`
 */

import { describe, it, expect } from 'vitest';
import en from '../locales/en.json';
import hi from '../locales/hi.json';
import te from '../locales/te.json';
import baselineHi from './__snapshots__/i18n_baseline_hi.txt?raw';
import baselineTe from './__snapshots__/i18n_baseline_te.txt?raw';

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

const USER_NAMESPACES = [
  'chat.', 'profile.', 'meditation.', 'common.', 'mood.', 'engagement.',
  'practices.', 'practice.', 'greeting.', 'support.', 'language.',
  'tour.', 'welcome.', 'nav.', 'sereneMind.', 'serene.',
];

const isUserFacing = (k: string) => USER_NAMESPACES.some((ns) => k.startsWith(ns));

const enKeys = Object.keys(flatten(en as NestedDict)).filter(isUserFacing);
const hiKeys = Object.keys(flatten(hi as NestedDict));
const teKeys = Object.keys(flatten(te as NestedDict));

const baselineMissingHi = new Set(
  baselineHi.trim().split('\n').filter(Boolean),
);
const baselineMissingTe = new Set(
  baselineTe.trim().split('\n').filter(Boolean),
);

const newMissingHi = enKeys.filter(
  (k) => !hiKeys.includes(k) && !baselineMissingHi.has(k),
);
const newMissingTe = enKeys.filter(
  (k) => !teKeys.includes(k) && !baselineMissingTe.has(k),
);

describe('i18n parity regression', () => {
  it('no NEW user-facing keys missing in hi.json', () => {
    expect(
      newMissingHi,
      `Hi missing ${newMissingHi.length} NEW user-facing keys. Add them to src/locales/hi.json or extend the baseline at src/test/__snapshots__/i18n_baseline_hi.txt:\n${newMissingHi.slice(0, 20).join('\n')}`,
    ).toEqual([]);
  });

  it('no NEW user-facing keys missing in te.json', () => {
    expect(
      newMissingTe,
      `Te missing ${newMissingTe.length} NEW user-facing keys. Add them to src/locales/te.json or extend the baseline at src/test/__snapshots__/i18n_baseline_te.txt:\n${newMissingTe.slice(0, 20).join('\n')}`,
    ).toEqual([]);
  });
});
