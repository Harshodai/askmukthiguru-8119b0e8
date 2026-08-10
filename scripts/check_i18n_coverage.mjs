#!/usr/bin/env node
/**
 * check_i18n_coverage.mjs
 *
 * Verifies top-level translation-key parity across the "real" locales
 * (en + hi/te/kn/ta/mr). Every top-level namespace present in en.json must
 * exist in each of the other 5 real locales; missing keys fail the check
 * with a non-zero exit.
 *
 * Usage:
 *   node scripts/check_i18n_coverage.mjs
 */
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const LOCALES_DIR = join(ROOT, 'src', 'locales');

const REAL_LOCALES = ['en', 'hi', 'te', 'kn', 'ta', 'mr'];

const read = (lng) => JSON.parse(readFileSync(join(LOCALES_DIR, `${lng}.json`), 'utf8'));

const en = read('en');
const enKeys = Object.keys(en);

let failed = false;
for (const lng of REAL_LOCALES) {
  if (lng === 'en') continue;
  const data = read(lng);
  for (const key of enKeys) {
    if (!(key in data)) {
      console.error(`[fail] ${lng}.json is missing top-level key "${key}" (present in en.json)`);
      failed = true;
    }
  }
}

if (failed) {
  console.error('i18n coverage check FAILED — add the missing namespaces to the real locales.');
  process.exit(1);
}
console.log(`i18n coverage OK: all ${enKeys.length} top-level namespaces present in ${REAL_LOCALES.join(', ')}.`);