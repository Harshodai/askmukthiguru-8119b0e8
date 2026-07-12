import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import en from './locales/en.json';
import hi from './locales/hi.json';
import te from './locales/te.json';
import kn from './locales/kn.json';
import ta from './locales/ta.json';
import mr from './locales/mr.json';

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
