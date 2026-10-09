/**
 * Shared i18n helpers. English (src/locales/en.json) is the single source of
 * truth; every other locale is derived from it by `scripts/i18n_sync.mjs`.
 * Pure functions only (no network, no fs writes) so they are unit-testable.
 */
import { createHash } from 'node:crypto';

export const LOCALES = ['en', 'hi', 'te', 'kn', 'ta', 'mr', 'bn', 'gu', 'ml', 'ur', 'pa', 'or', 'as', 'sa'];
export const TARGET_LOCALES = LOCALES.filter((l) => l !== 'en');

export const LOCALE_NAMES = {
  hi: 'Hindi (Devanagari)', te: 'Telugu', kn: 'Kannada', ta: 'Tamil', mr: 'Marathi (Devanagari)',
  bn: 'Bengali', gu: 'Gujarati', ml: 'Malayalam', ur: 'Urdu (Perso-Arabic script)',
  pa: 'Punjabi (Gurmukhi)', or: 'Odia', as: 'Assamese', sa: 'Sanskrit (Devanagari)',
};

// Values that legitimately stay identical to English (placeholders, contact
// details, machine tokens). Shared by the sync tool and the quality gate.
export const IDENTICAL_VALUE_ALLOWLIST = new Set([
  'auth.emailPlaceholder',
  'auth.passwordPlaceholder',
  'chat.inviteCodePlaceholder',
  'onboarding.tour.stepIndicator',
  'profile.support.emailPlaceholder',
  'nav.appName',
  'practices.detail.youtubeShort',
]);

// Teacher content shown in the UI (curated quotes). English is authoritative:
// the sync tool NEVER machine-translates or rewrites these. Existing values
// are left exactly as they are; a missing one is a loud failure, not a guess.
export const PROTECTED_KEY_RE = /(^|\.)quote$/;

// UI strings that touch crisis/safety. They are machine-translated like the
// rest but are listed in docs/i18n/SAFETY_MACHINE_TRANSLATED.md (no native review).
export const SAFETY_KEY_RE = /crisis|helpline|suicid|self.?harm|emergency|distress|safety/i;

export const flatten = (value, prefix = '', out = {}) => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [k, v] of Object.entries(value)) flatten(v, prefix ? `${prefix}.${k}` : k, out);
  } else {
    out[prefix] = String(value ?? '');
  }
  return out;
};

/** Rebuild a nested object whose key order follows `orderedKeys` (en order). */
export const unflatten = (flat, orderedKeys) => {
  const root = {};
  for (const key of orderedKeys) {
    if (!(key in flat)) continue;
    const parts = key.split('.');
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) node = node[parts[i]] ??= {};
    node[parts[parts.length - 1]] = flat[key];
  }
  return root;
};

export const hashValue = (s) => createHash('sha256').update(s).digest('hex').slice(0, 12);
export const placeholders = (s) => [...s.matchAll(/{{\s*([^}]+?)\s*}}/g)].map((m) => m[1].trim()).sort();
// Phone numbers / helpline digits: 3+ digit runs must survive translation verbatim.
// Native-script numerals (e.g. Bengali ৮,৭৫০) are fine; they are compared as ASCII digits.
const DIGIT_ZEROS = [0x660, 0x6f0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66, 0xbe6, 0xc66, 0xce6, 0xd66];
const asciiDigits = (s) =>
  s.replace(/[\u0660-\u0669\u06f0-\u06f9\u0966-\u096f\u09e6-\u09ef\u0a66-\u0a6f\u0ae6-\u0aef\u0b66-\u0b6f\u0be6-\u0bef\u0c66-\u0c6f\u0ce6-\u0cef\u0d66-\u0d6f]/g, (c) => {
    const cp = c.codePointAt(0);
    return String(cp - DIGIT_ZEROS.find((z) => cp >= z && cp < z + 10));
  });
export const digitRuns = (s) => (asciiDigits(s).match(/\d{3,}/g) ?? []).sort();

export const isProtected = (key) => PROTECTED_KEY_RE.test(key);
export const isLeftoverEnglish = (key, en, value) =>
  en.trim().length >= 4 && value === en && !IDENTICAL_VALUE_ALLOWLIST.has(key) && !isProtected(key);

/** Why a candidate translation is unacceptable, or null when it is fine. */
export function validateTranslation(key, en, value) {
  if (typeof value !== 'string' || !value.trim()) return 'empty';
  if (JSON.stringify(placeholders(en)) !== JSON.stringify(placeholders(value))) return 'placeholder mismatch';
  if (JSON.stringify(digitRuns(en)) !== JSON.stringify(digitRuns(value))) return 'digits/helpline number changed';
  if (isLeftoverEnglish(key, en, value)) return 'still English';
  return null;
}

/**
 * Compare one locale against English + the source-hash manifest.
 * @returns {{missing:string[],extra:string[],stale:string[],leftover:string[],invalid:string[]}}
 */
export function diagnoseLocale(enFlat, localeFlat, manifestHashes) {
  const res = { missing: [], extra: [], stale: [], leftover: [], invalid: [] };
  for (const key of Object.keys(localeFlat)) if (!(key in enFlat)) res.extra.push(key);
  for (const [key, en] of Object.entries(enFlat)) {
    if (!(key in localeFlat)) { res.missing.push(key); continue; }
    const value = localeFlat[key];
    if (isProtected(key)) continue;
    if (manifestHashes[key] !== hashValue(en)) { res.stale.push(key); continue; }
    if (isLeftoverEnglish(key, en, value)) { res.leftover.push(key); continue; }
    const why = validateTranslation(key, en, value);
    if (why) res.invalid.push(`${key} (${why})`);
  }
  return res;
}

/** Keys of one locale that a sync must (re)translate. Protected keys never. */
export const keysToTranslate = (d) =>
  [...new Set([...d.missing, ...d.stale, ...d.leftover, ...d.invalid.map((s) => s.split(' ')[0])])]
    .filter((k) => !isProtected(k));

const TERMINATORS = /[.!?\u0964\u06d4\u061f\u2026]+/g;
/**
 * Structural fidelity (sync-time only): a translation must not add, drop or
 * reword clauses. Sentence count and the "ends with a full stop / does not"
 * shape must match English, and the length must stay within a sane band.
 * Heuristic by design: it catches a dropped or invented clause, not word choice.
 */
export function fidelityProblem(en, value) {
  const n = (s) => (s.replace(/{{[^}]+}}/g, '').match(TERMINATORS) ?? []).length;
  if (n(en) !== n(value)) return 'sentence count differs from English (added or dropped a clause)';
  const ends = (s) => /[.!?\u0964\u06d4\u061f\u2026:]\s*$/.test(s.trim());
  if (ends(en) !== ends(value)) return 'ending punctuation differs from English (reworded ending)';
  if (en.length >= 40 && (value.length < en.length * 0.3 || value.length > en.length * 3.5)) return 'length implausible vs English';
  return null;
}

export function buildPrompt(localeCode, items) {
  const lang = LOCALE_NAMES[localeCode] ?? localeCode;
  return [
    {
      role: 'system',
      content:
        `You translate UI strings for AskMukthiGuru, a respectful spiritual-companion app, from English into ${lang}. ` +
        'Return ONLY a JSON object mapping each given key to its translation. Rules: ' +
        '(1) keep {{placeholders}} exactly as written; ' +
        '(2) keep digits, phone numbers, URLs, email addresses and the names AskMukthiGuru, Ekam, Oneness, GDPR, DPDP Act, YouTube unchanged; ' +
        '(3) write Sri Preethaji & Sri Krishnaji as a respectful transliteration in the target script; ' +
        '(4) translate faithfully and literally: do not add, drop, merge, split, reword or soften any clause, claim, warning or disclaimer; keep the same sentence count and the same ending (if the English ends mid-sentence, e.g. before a link, end mid-sentence too, with no colon or full stop added); ' +
        '(5) simple, natural, respectful modern language; keep punctuation such as em-dashes and emoji.',
    },
    { role: 'user', content: JSON.stringify(items, null, 1) },
  ];
}

/**
 * Apply `updates` (flat) and delete `removals` (flat keys) on a nested locale
 * object IN PLACE, keeping each file's existing key order so diffs stay tiny.
 * New keys are appended where they first appear in `enOrder`.
 */
export function patchNested(nested, updates, removals = []) {
  for (const key of removals) {
    const parts = key.split('.');
    const trail = [nested];
    for (const p of parts.slice(0, -1)) { if (!trail.at(-1)?.[p]) break; trail.push(trail.at(-1)[p]); }
    if (trail.length === parts.length) {
      delete trail.at(-1)[parts.at(-1)];
      for (let i = trail.length - 1; i > 0; i--) if (!Object.keys(trail[i]).length) delete trail[i - 1][parts[i - 1]];
    }
  }
  for (const [key, value] of Object.entries(updates)) {
    const parts = key.split('.');
    let node = nested;
    for (const p of parts.slice(0, -1)) node = (node[p] && typeof node[p] === 'object') ? node[p] : (node[p] = {});
    node[parts.at(-1)] = value;
  }
  return nested;
}
