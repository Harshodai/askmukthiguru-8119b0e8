import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import en from './locales/en.json';

// Only English ships in the entry chunk. The other bundles are 55–110 kB of
// JSON each; statically importing all eleven put ~900 kB (of a 1.0 MB entry
// chunk) on the critical path for every visitor, in ten languages they will
// never read. `import.meta.glob` without `eager` makes Vite emit one lazy
// chunk per locale, fetched only when that language is actually selected.
const localeLoaders = import.meta.glob<{ default: Record<string, unknown> }>(
  ['./locales/*.json', '!./locales/en.json'],
);

const SUPPORTED = ['en', 'hi', 'te', 'kn', 'ta', 'mr', 'bn', 'gu', 'ml', 'ur', 'pa', 'or', 'as', 'sa'] as const;

const baseLanguage = (lng?: string) => (lng ?? 'en').split('-')[0];

const RTL_LANGUAGES = new Set(['ur']);

const syncDocumentLanguage = (lng: string) => {
  if (typeof document === 'undefined') return;
  const base = baseLanguage(lng);
  document.documentElement.lang = base;
  document.documentElement.dir = RTL_LANGUAGES.has(base) ? 'rtl' : 'ltr';
};

/** Fetch + register a locale bundle once. No-op for en / unknown / already-loaded. */
const localeLoads = new Map<string, Promise<void>>();

const loadLocale = async (lng: string): Promise<void> => {
  const base = baseLanguage(lng);
  if (base === 'en' || i18n.hasResourceBundle(base, 'translation')) return;
  const existing = localeLoads.get(base);
  if (existing) return existing;

  const load = localeLoaders['./locales/' + base + '.json'];
  if (!load) return;

  const promise = load().then((mod) => {
    if (!i18n.hasResourceBundle(base, 'translation')) {
      i18n.addResourceBundle(base, 'translation', mod.default, true, true);
    }
  }).finally(() => {
    localeLoads.delete(base);
  });

  localeLoads.set(base, promise);
  return promise;
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
    },
    supportedLngs: SUPPORTED as unknown as string[],
    // Every other language starts as an empty bundle that `loadLocale` fills in,
    // so i18next must not treat "no resources yet" as "language unavailable".
    partialBundledLanguages: true,
    fallbackLng: 'en',
    ns: ['translation'],
    defaultNS: 'translation',
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'askmukthiguru_profile.preferredLanguage',
      caches: ['localStorage'],
    },
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: false,
      // Re-render on `addResourceBundle`, not just on `languageChanged` —
      // otherwise a lazily-fetched locale lands in the store and nothing repaints.
      bindI18nStore: 'added',
    },
    returnNull: false,
  });

export const changeUiLanguage = async (lng: string): Promise<void> => {
  const base = baseLanguage(lng);
  await loadLocale(base);
  await i18n.changeLanguage(base);
};

i18n.on('languageChanged', (lng) => {
  syncDocumentLanguage(lng);
});

export const setLocale = async (lng: string): Promise<void> => {
  const base = baseLanguage(lng);
  if (!SUPPORTED.includes(base as (typeof SUPPORTED)[number])) return;
  await loadLocale(base);
  await i18n.changeLanguage(base);
};

// The detector may resolve to a non-English language before any change event.
syncDocumentLanguage(i18n.language);
void loadLocale(baseLanguage(i18n.language));

export default i18n;
