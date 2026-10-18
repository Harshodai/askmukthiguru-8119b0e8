# `t()` coverage audit — draft 2026-10-15 (agent; owner truth-check pending)

Faculty packet §3 item 4 / Deployment checklist item 1. Static scan only — no
locale file was modified. Counts from a script pass over `src/**` (tests and
`src/locales` excluded).

## 1. Key structure — closed

- 14 locale files, **1,796 keys each, exact path parity** with `en.json`.
- Enforced by `src/test/i18n-parity.test.ts` (parity) and
  `src/test/i18n-sync.test.ts` (English-as-source sync: missing/extra/stale
  keys, placeholder drift, helpline-digit drift, leftover-English detection).
- Real translations: en, hi, te, kn, ta, mr. The other 8 (bn, gu, ml, ur, or,
  pa, as, sa) exist as files but are English fallback content at runtime —
  `ml` visible in dropdown (already in packet known-limits).

## 2. `t()` call sites — one silent gap, no visible breakage

- 1,780 literal `t()/tt()` calls + 13 dynamic (`${}`) — not statically checkable.
- **0 calls render a raw dotted key.** The only two suspicious no-default
  calls (`chat.sourceCount`, `chat.slashResultsCount`) resolve through
  i18next plural keys `*_one`/`*_other` that do exist. i18n config:
  `fallbackLng: 'en'`, `returnNull: false`.
- **107 distinct keys are referenced with an inline English `defaultValue`
  but are NOT defined in `en.json`** (138 call sites, all seeker-facing,
  **0 in admin**). i18next renders the default in every locale, so nothing
  looks broken — but these strings are **English in all 13 non-English
  locales**. Largest clusters: `memory.*` (MemoryManager 25 calls),
  `cancelFlow.*`/`profile.*` (ProfilePage 24), `sadhana.*`
  (SadhanaHeatmap 15), `chat.responsePreferences.*`, `notFound.*`,
  `auth.ageConfirm.*`, `chat.whatsappBanner.*`, `chat.guidance.*`,
  `onboarding.tour.*`.
- Effect: "real translation" coverage is key-structure-complete but
  **~107 UI strings never translated even in hi/te/kn/ta/mr** because they
  never entered `en.json`.

## 3. Hardcoded English outside `t()` — heuristic

~504 matches (JSX text nodes + `placeholder/title/aria-label/label/alt`
attributes, inline expressions stripped) across 83 `.tsx` files:

| Area | Count | Reading |
|---|---|---|
| `src/admin/**` | ~305 | Admin console is English-by-design for operators — **owner ruling needed** (document as intentional, or add to i18n scope) |
| Seeker-facing | ~199 | Real coverage debt. Top: `DeepenAndTuneBar.tsx` (18), `TTSVerificationPage.tsx` (16 — internal verification page), `ProvenanceDrawer.tsx` (15), `LinkSearchModal.tsx` (11), `StudyNotebookPage.tsx` (9), `AuthLatencyDashboard.tsx` (9, internal), `DemoModal.tsx` (8) |

Heuristic includes false positives (alt text on decorative icons, etc.) —
numbers are an order-of-magnitude draft, not a defect list.

## 4. Proposed fix plan (owner decides; not started)

1. **Promote the 107 inline-default keys into `en.json`** using the existing
   sync tooling (`scripts/i18n/`), then translate to the 6 real locales via
   the same sync workflow. The sync test's leftover-English check will flag
   which of the 13 files actually carry content vs fallback.
2. **Admin console ruling**: document English-only as intentional (1 line in
   README/admin docs), or put it in i18n scope. Recommend documenting —
   operators are not the multilingual audience.
3. **Regression guard (needs CI/workflow approval)**: a lint check that fails
   when `t('key')`'s inline default has no matching `en.json` key — turns the
   silent gap into a build error. Script could live in `scripts/i18n/` and be
   added to the existing parity test instead of a new workflow (test-only, no
   workflow edit needed).
4. **Seeker-facing hardcoded sweep**: translate top seeker files first
   (chat surfaces before internal dashboards).

## 5. Relation to faculty packet

- Packet §4.3 language table stands (6 real / 8 fallback) — this audit adds
  the sharper fact: even hi/te/kn/ta/mr show English for the 107-key set and
  all hardcoded strings.
- Recommend adding the 107-key set size + admin-English ruling to the
  packet's known-limits page before send (owner call).
