#!/usr/bin/env node
/**
 * check_i18n_quality.mjs
 *
 * Runtime-data quality guard for the supported locale bundles.
 * This complements deep key parity by checking:
 *   1. every locale preserves the same interpolation placeholders
 *   2. no translated value is empty
 *   3. known historically-corrupted translations stay corrected
 *
 * It intentionally does not flag brand/proper-noun English values globally;
 * doing so would create false positives for product names, URLs, email
 * addresses, code-like labels, and technical terms.
 */

import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const LOCALES_DIR = join(ROOT, 'src', 'locales');
const LOCALES = ['en', 'hi', 'te', 'kn', 'ta', 'mr', 'bn', 'gu', 'ml', 'ur', 'pa', 'or', 'as', 'sa'];

const read = (lng) => JSON.parse(readFileSync(join(LOCALES_DIR, `${lng}.json`), 'utf8'));

const flattenLeaves = (value, prefix = '', out = {}) => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      flattenLeaves(child, prefix ? `${prefix}.${key}` : key, out);
    }
  } else {
    out[prefix] = String(value ?? '');
  }
  return out;
};

const placeholders = (value) =>
  [...value.matchAll(/{{\s*([^}]+?)\s*}}/g)].map((m) => m[1].trim()).sort();

const en = flattenLeaves(read('en'));
let failed = false;

// These values intentionally remain identical across locales because they are
// placeholders, route-independent code-like values, contact details, or a
// machine-readable progress token rather than user prose.
const IDENTICAL_VALUE_ALLOWLIST = new Set([
  'auth.emailPlaceholder',
  'auth.passwordPlaceholder',
  'chat.inviteCodePlaceholder',
  'onboarding.tour.stepIndicator',
  'profile.support.emailPlaceholder',
  'common.crisisNumbers',
  'nav.appName',
  'practices.detail.youtubeShort',
]);


for (const lng of LOCALES.slice(1)) {
  const locale = flattenLeaves(read(lng));

  for (const [key, sourceValue] of Object.entries(en)) {
    const targetValue = locale[key];

    if (targetValue === undefined) {
      console.error(`[fail] ${lng}: missing key ${key}`);
      failed = true;
      continue;
    }

    if (!targetValue.trim()) {
      console.error(`[fail] ${lng}: empty translation for ${key}`);
      failed = true;
    }

    if (
      sourceValue.trim().length >= 4 &&
      targetValue === sourceValue &&
      !IDENTICAL_VALUE_ALLOWLIST.has(key)
    ) {
      console.error(
        `[fail] ${lng}: value is identical to English for user-facing key ${key}: ${JSON.stringify(targetValue)}`,
      );
      failed = true;
    }

    const expected = JSON.stringify(placeholders(sourceValue));
    const actual = JSON.stringify(placeholders(targetValue));
    if (expected !== actual) {
      console.error(`[fail] ${lng}: placeholder mismatch for ${key}: expected ${expected}, got ${actual}`);
      failed = true;
    }
  }
}

const knownBadValues = {
  hi: {
    'common.day': 'बिन्दु',
    'common.days': 'बिन्दु',
    'common.hour': '॥',
    'common.decline': 'पतन',
  },
  te: {
    'common.beginJourney': 'పాఠ్యం:',
    'common.daysAgo': '{{count}} సంవత్సరాల క్రితం',
    'common.disable': 'నిలిపివేయబడిన',
  },
};

// Hindi corruption guard: these repeated "नारार..." artifacts were shipped in
// chat copy and are especially dangerous because they look like valid Unicode.
for (const [key, value] of Object.entries(flattenLeaves(read('hi')))) {
  if (value.includes('नारार')) {
    console.error(`[fail] hi: known corruption marker remains at ${key}`);
    failed = true;
  }
}

for (const [lng, entries] of Object.entries(knownBadValues)) {
  const locale = flattenLeaves(read(lng));
  for (const [key, badValue] of Object.entries(entries)) {
    if (locale[key] === badValue) {
      console.error(`[fail] ${lng}: known corrupted translation remains at ${key}`);
      failed = true;
    }
  }
}

if (failed) {
  console.error('i18n quality check FAILED.');
  process.exit(1);
}

console.log(`i18n quality OK across ${LOCALES.length} locales.`);
