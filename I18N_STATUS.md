# i18n Status — Language Coverage

## Fully Translated (5 languages + English)

| Code | Language | File | Status |
|---|---|---|---|
| `en` | English | `src/locales/en.json` | ✅ Source of truth (967 keys) |
| `hi` | हिन्दी Hindi | `src/locales/hi.json` | ✅ Complete |
| `te` | తెలుగు Telugu | `src/locales/te.json` | ✅ Complete |
| `kn` | ಕನ್ನಡ Kannada | `src/locales/kn.json` | ✅ Complete |
| `ta` | தமிழ் Tamil | `src/locales/ta.json` | ✅ Complete |
| `mr` | मराठी Marathi | `src/locales/mr.json` | ✅ Complete |

## Selectable but Fall Back to English (8 languages)

These are registered in `src/i18n.ts` pointing at the English resource bundle. Users can select them (LanguageSelector shows them) but UI text will render in English until dedicated locale files are added.

| Code | Language | To translate |
|---|---|---|
| `bn` | বাংলা Bengali | Copy `en.json` → `bn.json`, translate values |
| `gu` | ગુજરાતી Gujarati | Copy `en.json` → `gu.json`, translate values |
| `ml` | മലയാളം Malayalam | Copy `en.json` → `ml.json`, translate values |
| `ur` | اُردُو Urdu | Copy `en.json` → `ur.json`, translate values |
| `or` | ଓଡ଼ିଆ Odia | Copy `en.json` → `or.json`, translate values |
| `pa` | ਪੰਜਾਬੀ Punjabi | Copy `en.json` → `pa.json`, translate values |
| `as` | অসমীয়া Assamese | Copy `en.json` → `as.json`, translate values |
| `sa` | संस्कृतम् Sanskrit | Copy `en.json` → `sa.json`, translate values |

## How to Complete a Locale

**Fastest path** — batch translate via Gemini/ChatGPT:

1. Copy `src/locales/en.json` to `src/locales/<code>.json`
2. Prompt: "Translate all JSON values in this file to <language>. Keep keys and structure identical. Do not translate proper nouns (Sri Preethaji, Beautiful State, Serene Mind). Output valid JSON only."
3. Paste `en.json` contents
4. Save output as `<code>.json`
5. In `src/i18n.ts`:
   ```ts
   import xx from './locales/xx.json';   // add import
   // in resources: change `xx: { translation: enFallback }` to `xx: { translation: xx }`
   ```

**Cost estimate**: ~$0.10 per locale via Gemini Flash. Ask agent to do batch of 8 → ~2 credits.

## Admin Console i18n

**Status**: English-only by design. `src/admin/**` uses hardcoded strings, no `useTranslation()` hooks. Admin console is internal — translating it adds surface area without user value.

**Override**: Say "translate admin console to Hindi" and the agent will add `useTranslation` throughout ~24 admin pages (~4 credits).

## Not Yet Selectable

15 more Indian scheduled languages exist in `LanguageSelector.tsx` `MASTER_LANGUAGES` (Maithili, Kashmiri, Konkani, Dogri, Sindhi, Nepali, Manipuri, Santali, Bodo) — filtered out because they have no i18n resource. Add via same recipe above.
