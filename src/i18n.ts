import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import en from './locales/en.json';
import hi from './locales/hi.json';
import te from './locales/te.json';
import kn from './locales/kn.json';
import ta from './locales/ta.json';
import mr from './locales/mr.json';

// Additional Indian languages registered as English fallbacks until fully translated.
// Users can select them in the LanguageSelector; text falls back to English via fallbackLng.
// See USER_ACTIONS.md → "Translate remaining locales" for how to complete these.
const enFallback = en;

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      hi: { translation: hi },
      te: { translation: te },
      kn: { translation: kn },
      ta: { translation: ta },
      mr: { translation: mr },
      // Pending full translation — fall back to English resources for now.
      bn: { translation: enFallback },
      gu: { translation: enFallback },
      ml: { translation: enFallback },
      ur: { translation: enFallback },
      or: { translation: enFallback },
      pa: { translation: enFallback },
      as: { translation: enFallback },
      sa: { translation: enFallback },
    },
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
    },
    returnNull: false,
  });

export default i18n;
