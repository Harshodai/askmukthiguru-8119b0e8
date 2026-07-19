# Session Handoff — Jul 18, 2026 (Redesign, Term Renaming & Localization)

## 1. The Goal We Are Working Toward
- Complete the redesign requirements in `~/Downloads/askmukthiguru-redesign/` (Digital Ashram layout, mood check-ins, stat row, safety pillars, mandala corners, ambient breath motion).
- Align technical terminology to user-friendly spiritual language:
  - Rename "Second Brain" to **"My Reflections"** (in English) / `"मेरे विचार"` (Hindi) / `"నా ఆత్మావలోకనం"` (Telugu) / `"என் பிரதிபலிப்புகள்"` (Tamil) / `"माझे विचार"` (Marathi) / `"ನನ್ನ ಆಲೋಚನೆಗಳು"` (Kannada).
  - Rename "Knowledge Graph" to **"Wisdom Map"** (in English) / `"ज्ञान मानचित्र"` (Hindi) / `"జ్ఞాన చిత్రం"` (Telugu) / `"ஞான வரைபடம்"` (Tamil) / `"ज्ञान नकाशा"` (Marathi) / `"ಜ್ಞಾನ ನಕ್ಷೆ"` (Kannada).
- Clean up language selection list: Restrict selector options strictly to the 6 fully supported/translated languages.
- Apply database migrations to both the local stack and the remote project-level Supabase free tier (`ozmjeuqbholoxypfxixb`).
- Update behavioral rules to remove the auto-commit and push requirement.

---

## 2. Current State of Code
- **Compilation**: The frontend project builds cleanly with `npm run build:dev` (no TypeScript or bundler errors).
- **Unit Tests**: Ran localized component unit tests individually (`LanguageSelector.test.tsx` and `components/LanguageSelector.test.tsx`), and they are passing (14/14 tests green).
- **Git Status**: All changes are safely preserved in the local working directory (staged and unstaged) and not committed/pushed, complying with your request.
- **Rules Updated**: `AGENTS.md` has been modified to remove the mandatory automatic git commit/push rule.
- **Database Migrations Fixed**:
  - Solved migration conflict caused by duplicate version key `20260713000000`.
  - Solved migration crash caused by `REVOKE EXECUTE ON FUNCTION` for non-existent functions.

---

## 3. Files Actively Edited / Modified
- [LanguageSelector.tsx](src/components/chat/LanguageSelector.tsx) (filtered to six supported languages)
- [SecondBrainPage.tsx](src/pages/SecondBrainPage.tsx) (localized and renamed terms to "My Reflections" / "Reflections")
- [KnowledgeGraphPage.tsx](src/pages/KnowledgeGraphPage.tsx) (renamed to "Wisdom Map")
- [DesktopSidebar.tsx](src/components/chat/DesktopSidebar.tsx) (renamed navigation links to "Wisdom Map" and "My Reflections")
- Locale JSON translation files:
  - [en.json](src/locales/en.json)
  - [hi.json](src/locales/hi.json)
  - [te.json](src/locales/te.json)
  - [kn.json](src/locales/kn.json)
  - [mr.json](src/locales/mr.json)
  - [ta.json](src/locales/ta.json)
- [20260715000000_harden_linter_warnings.sql](supabase/migrations/20260715000000_harden_linter_warnings.sql) (commented out non-existent functions)
- [AGENTS.md](AGENTS.md) (removed auto-commit/push instruction)

---

## 4. Everything Tried and Failed
- **Duplicate migration version `20260713000000`**: Two migrations (`20260713000000_create_push_devices.sql` and `20260713000000_user_retention_cards.sql`) had the exact same timestamp, halting local Supabase start with a primary key duplicate violation.
  * **Fix**: Renamed `20260713000000_user_retention_cards.sql` to `20260713000001_user_retention_cards.sql`.
- **Non-existent function errors in `20260715000000_harden_linter_warnings.sql`**: The migration crashed because of `REVOKE EXECUTE ON FUNCTION` statements for `public.rls_auto_enable()`, `public.meditation_streak(uuid)`, and `public.match_user_memories_by_user(uuid, ...)` which do not exist or were dropped.
  * **Fix**: Commented out these lines in `20260715000000_harden_linter_warnings.sql`.
- **Supabase CLI db push dry-run**: Tried pushing migrations using `npx supabase db push --dry-run` to project `ozmjeuqbholoxypfxixb`. This failed because the environment doesn't contain a `SUPABASE_ACCESS_TOKEN` or database password.
  * **Fix**: Requires either database credentials/access tokens or manually running it with credentials.

---

## 5. Next Steps
1. **Push Migrations to Remote Project**: Run `npx supabase db push` once a database password or `SUPABASE_ACCESS_TOKEN` is supplied, or manually paste the fixed migrations into the SQL Editor of the Supabase dashboard for project `ozmjeuqbholoxypfxixb`.
2. **Local Startup Check**: Run `npx supabase start` to boot the local database container and verify the full local stack starts successfully.
3. **Interactive Verification**: Start the local development server (`npm run dev`), switch the UI language to Hindi or Telugu, and verify that "My Reflections" and "Wisdom Map" translate dynamically.
