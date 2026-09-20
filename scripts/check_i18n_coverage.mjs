#!/usr/bin/env node
/**
 * check_i18n_coverage.mjs
 *
 * Verifies deep translation-key parity across the real locales
 * (all exposed locales). Every leaf key present in en.json must exist at the
 * same nested path in each real locale; missing or extra leaf keys fail the check.
 *
 * Usage:
 *   node scripts/check_i18n_coverage.mjs
 */
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const LOCALES_DIR = join(ROOT, 'src', 'locales');

// All locale bundles exposed by LanguageSelector.tsx must participate in the
// deep parity gate. Keep this list aligned with the product's public locale set.
const REAL_LOCALES = ['en', 'hi', 'te', 'kn', 'ta', 'mr', 'bn', 'gu', 'ml', 'ur', 'pa', 'or', 'as', 'sa'];

const read = (lng) => JSON.parse(readFileSync(join(LOCALES_DIR, `${lng}.json`), 'utf8'));

const en = read('en');
const flattenLeaves = (value, prefix = '', out = []) => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      flattenLeaves(child, prefix ? `${prefix}.${key}` : key, out);
    }
  } else {
    out.push(prefix);
  }
  return out;
};

const enKeys = flattenLeaves(en);
const enKeySet = new Set(enKeys);

let failed = false;
for (const lng of REAL_LOCALES) {
  if (lng === 'en') continue;
  const data = read(lng);
  const localeKeys = flattenLeaves(data);
  const localeKeySet = new Set(localeKeys);

  for (const key of enKeys) {
    if (!localeKeySet.has(key)) {
      console.error(`[fail] ${lng}.json is missing leaf key "${key}" (present in en.json)`);
      failed = true;
    }
  }

  for (const key of localeKeys) {
    if (!enKeySet.has(key)) {
      console.error(`[fail] ${lng}.json contains extra leaf key "${key}" (not present in en.json)`);
      failed = true;
    }
  }
}

if (failed) {
  console.error('i18n coverage check FAILED — every real locale must match en.json at the leaf-key level.');
  process.exit(1);
}
console.log(`i18n coverage OK: all ${enKeys.length} leaf keys match across ${REAL_LOCALES.join(', ')}.`);