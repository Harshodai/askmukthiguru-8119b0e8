import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Regression guard (lessons.md L-OUTCOME-CLAIMS-2): the first rewrite searched only three terms and missed
// medical or guaranteed-outcome wording. Scan the whole class in English copy.
const BANNED: [RegExp, string][] = [
  [/vagal/i, 'vagal nerve'],
  [/nervous system/i, 'nervous system'],
  [/amygdala|cortisol|heart rate variability/i, 'physiology'],
  [/manifest(ing)?\s+(destiny|it)\b|manifests? destiny/i, 'manifestation promise'],
  [/restful sleep|deep rest\b/i, 'sleep outcome'],
  [/\bimmediate calm\b|\bquickly (settles|calm)|instantly calm/i, 'instant calm'],
  [/\b(cure|cures|heals? your|reduce[s]? (stress|anxiety)\b)/i, 'treatment/cure'],
  [/\bdissolves? (self-cent\w+ )?suffering/i, 'dissolves suffering'],
];

const root = resolve(__dirname, '../..');
const files = ['src/locales/en.json', 'src/lib/practicesContent.ts', 'src/pages/Index.tsx', 'src/components/landing/HeroSection.tsx'];

describe('English copy carries no medical or guaranteed-outcome claims', () => {
  for (const f of files) {
    it(f, () => {
      const text = readFileSync(resolve(root, f), 'utf8');
      const hits = BANNED.filter(([re]) => re.test(text)).map(([, n]) => n);
      expect(hits).toEqual([]);
    });
  }
});
