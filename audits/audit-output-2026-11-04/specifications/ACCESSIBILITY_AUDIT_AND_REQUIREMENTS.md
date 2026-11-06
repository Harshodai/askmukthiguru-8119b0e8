# Accessibility audit and requirements (WCAG 2.2 AA, core seeker journey)

## 0. Header

| Field | Value |
|---|---|
| Purpose | Fill the gap that the audit package left open: it ran no accessibility audit (`FINAL_PRODUCTION_RELEASE_READINESS.md` row C7 says "Not audited yet"). This file audits the core seeker journey against WCAG 2.2 AA and states the requirements, tests and tasks that close the gaps. |
| Status | **Partial. Gate C item C7 is NOT met and is UNPROVEN end to end.** Runtime checks ran on the frontend only (no backend, no sign-in). The answer-with-clip view, the clip dialog, the crisis answer, the settings page and the deletion flow did not render at runtime. For those, findings are static (code reading) and are labelled so. No screen-reader session ran. |
| Date | 2026-11-06 |
| Code head | `fb5cab0f` on `feature/audit-strengthen-rag-qdrant` (working tree read in this session; `src/`, tests and config unchanged by this audit) |
| Evidence labels | Same as `CONVENTIONS.md` section 3. Added here: `[V-RUN]` = measured in a browser in this session (page, rule id and count named). `[V-STATIC]` = read at `fb5cab0f` (`path:line`). `[COMPUTED]` = contrast computed from the colour tokens in `src/index.css`. `[NOT-TESTED]` = no evidence either way. |
| Note on target | `CONVENTIONS.md` section 1 names `origin/main@46b808fb` as the audit target. The task for this file named head `fb5cab0f`. This file follows the task. The a11y code paths read here (`src/components/chat/*`, `src/pages/AuthPage.tsx`, `src/index.css`) may differ on `main`. Re-check the `path:line` cites before you implement. |
| Gate served | Gate C, item C7. Section 5 maps the rest. |
| Finding IDs | A11Y-01 to A11Y-17. Tasks: NEW-A11Y-1 to NEW-A11Y-10. Open questions: PROPOSED D-PA11Y1 to D-PA11Y6. |

Rules that bind this file:

1. The teachers' words are verbatim spans. No fix in this file may paraphrase, translate or shorten a quote. Captions and transcripts must show the stored verbatim text (root `CLAUDE.md`, invariants 1 and 15).
2. The label "Related, not a direct answer" must stay (invariant 21). A fix changes its colour, markup and wording consistency. It does not remove the label.
3. Crisis and helpline text comes from `src/lib/crisisHelplines.ts`, which mirrors `config/helplines.yaml`. No fix adds or edits a phone number.
4. Automated tools find only part of the WCAG failures. A tool pass is not a conformance claim. Section 4 marks every criterion that needs a human check.

---

## 1. Existing coverage and what it lacks

### 1.1 Requirements already in the audit package

| ID | Text (short) | Source | Status in the package | Gap found here |
|---|---|---|---|---|
| NFR-A11Y-01 | 0 axe serious or critical violations on chat, citation, profile, practices. WCAG 2.2 AA. | `04-non-functional-requirements-slos-and-benchmarks.md:95`; `specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md:158` | Partial | The test tags have no WCAG 2.2 tag (finding C-9). The test does not render the citation view, the clip dialog, the crisis answer or the deletion flow. |
| NFR-A11Y-02 | Clip playback shows the spoken words as text. | `04-...:96`; matrix `:159` | Partial. Test marked MISSING. | The text exists in code. No test covers it. There is no caption track for the video (A11Y-06). |
| NFR-A11Y-03 | At least 1 screen-reader session per study round. | `04-...:97`; matrix `:160` | Open | Nobody has run one. `[HUMAN]`. |
| C-9 | WCAG 2.2 AA required, but tests carry no 2.2 tag. | `FINAL_PRODUCTION_RELEASE_READINESS.md:49` | Open | Confirmed here (1.2). |
| BL-10 | NFR-A11Y-01 and NFR-N-1 backlog item. | matrix `:268` | Open | Same. |
| C7 | "WCAG 2.2 AA check of the core journey. No unresolved level-A or level-AA failure on the core journey." | `FINAL_PRODUCTION_RELEASE_READINESS.md:63` | Not audited | This file is that audit (partial). |

### 1.2 Existing tests and tools in the repository

| Item | What it does | Gap |
|---|---|---|
| `tests/e2e/a11y-smoke.spec.ts` | Runs axe on `/`, `/auth`, `/chat`, `/profile`, `/practices`, `/practices/serene-mind`, `/knowledge-graph`, plus the meditation player. Fails only on `serious` and `critical`. Excerpt: `.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])` at `:98`. | No `wcag22aa` tag. Rule `target-size` (WCAG 2.5.8) belongs to that tag. Without it the test cannot see A11Y-09. Protected routes use a fake Supabase token (`seedAuth`, `:114-123`) and may fall back to `/auth`; the test accepts that (`:151-158`). It never opens the clip dialog or sends a message. It disables `frame-title` and `color-contrast-enhanced` (`:30`). |
| `tests/e2e/landing-accessibility.spec.ts` | Axe on the landing hero with `wcag2a`, `wcag2aa` only (`:14`). Checks the demo dialog has a close and next button. | No 2.1 or 2.2 tags. |
| `src/test/ChatMessage-a11y.test.tsx` | 4 unit tests: action toolbar shows on keyboard focus and on small screens, Serene Mind offer card is a polite live region. | Does not cover the verbatim card, labels, clip play, lang, or colour. |
| `eslint.config.js` | Plugins: `react-hooks`, `react-refresh`, `typescript-eslint`. | **No `eslint-plugin-jsx-a11y`.** `package.json` lists neither `eslint-plugin-jsx-a11y` nor `jest-axe` nor `vitest-axe`. `[V-STATIC]` |
| `@axe-core/playwright ^4.12.1`, `axe-core ^4.12.1`, `playwright ^1.60.0` | Present in `package.json:110,124,130`. | Installed in `node_modules`; used in section 2. |
| Skip link | `src/App.tsx:243-246` points to `#main-content`. | Works on `/` (section 2, R5). |
| Dialog focus helper | `src/hooks/useDialogFocus.ts` (focus in, Tab trap, Escape, focus return) for hand-rolled dialogs. | Good. Radix dialogs do the same by default. |

---

## 2. Method

### 2.1 Static

Read the components on the journey: `src/components/common/SafetyDisclaimer.tsx`, `CrisisLines.tsx`, `src/components/chat/{ChatComposer,ChatMessage,CitationCard,MessageList,ChatErrorBanner,QuotaAuthPrompt,AbstainHelpCard,MemorySettingsModal}.tsx`, `src/components/profile/settings/AccountDataCard.tsx`, `src/components/profile/CancelFlow.tsx`, `src/pages/{AuthPage,MFAChallengePage,TeacherWords}.tsx`, `src/components/landing/SampleWisdomSection.tsx`, `src/App.tsx`, `src/components/layout/*`, `src/i18n.ts`, `src/index.css`, `tailwind.config.ts`. Searched with `grep` for `aria-live`, `role=`, `lang=`, `<track`, `prefers-reduced-motion`, `autoComplete`, `onPaste`, `jsx-a11y`. Contrast was computed with a Python script (`c.py` in the scratchpad) from the HSL tokens in `src/index.css:70-103,151-183` and the Tailwind default `amber-600` (`#d97706`).

### 2.2 Runtime

Commands that ran (all local; no backend; no credentials; no package installed):

```text
# 1. Vite dev server. The default config binds "::" and failed with EAFNOSUPPORT.
#    Placeholder Supabase values were set only so the app boots. No call reaches Supabase.
VITE_SUPABASE_URL=http://127.0.0.1:54321 VITE_SUPABASE_PUBLISHABLE_KEY=dummy-placeholder \
  npx vite --host 127.0.0.1 --port 8080
# 2. Playwright 1.60 library + @axe-core/playwright 4.12.1 from node_modules, Chromium from /opt/pw-browsers
#    (the default headless-shell path was missing, so executablePath was set).
#    Scripts: axe.js, rt2.js, rt3.js, rt4.js in the session scratchpad. None is in the repository.
```

Axe tags used: `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`. Viewport 1280x900 unless stated. `/api/*` calls returned 502 from the dev proxy (no backend) or were mocked by `page.route` (HTTP 429/500 on `/api/chat`).

What did **not** run or did not work:

| Item | Result |
|---|---|
| Backend, Supabase sign-in, real answer, clip dialog, crisis answer, `/profile` settings, account deletion | Not reachable. `/profile` redirects to `/auth` without a session. Static review only. |
| `/teachers-words` route | Flag `FIRST_PERSON_ENABLED` gates it (`src/App.tsx:374`). Not rendered. |
| `npx playwright test` suite | Not run. It needs a built preview and Supabase (`playwright.config.ts`). |
| First `rt2.js` pass | Its click helper hung on the disclaimer button; output was cut after the landing, auth and reduced-motion parts. The chat parts re-ran as `rt3.js` and `rt4.js`. |
| Screen reader (NVDA, VoiceOver, TalkBack) | Not run. `[HUMAN]`. |
| 200% zoom, 320 px reflow, text spacing, forced colours, speech input | Not run. Only one 390 px check ran (send-button overlap). |

The dev server was stopped at the end (`curl` to port 8080 returned `000`).

### 2.3 Runtime results (raw)

| Ref | Page and state | Check | Result |
|---|---|---|---|
| R1 | `/`, disclaimer open, light and dark scheme | axe, 5 tags | 1 violation: `target-size` (serious), 5 nodes (`button[aria-label="Go to slide N"]`). Same in dark. |
| R2 | `/`, disclaimer closed | axe | Same 1 violation. Incomplete: `color-contrast` 55 nodes (needs review). |
| R3 | `/auth`, disclaimer closed | axe | 1 violation: `target-size` (serious), 1 node (`button[aria-label="Show password"]`). Incomplete: `color-contrast` 16, `link-in-text-block` 3. `/profile` redirects to `/auth` and shows the same result. |
| R4 | `/chat`, disclaimer closed, cookie banner visible | axe | 0 violations. Incomplete: `color-contrast` 3 nodes. |
| R5 | `/chat`, after a failed send (HTTP 500 mock) | axe, tags `wcag2aa, wcag22aa` | 1 violation: `color-contrast` (serious), 3 nodes: "AI Generated" badge 1.52:1 (`#fbbd23` on `#f8f3e8`); "Something went wrong" 3.29:1 (`#ef4343` on `#f8ede9`); "Retry" button text 3.29:1. |
| R6 | `/practices`, disclaimer open | axe | 0 violations (the page behind an open modal is not a full test). Page has 2 `main` landmarks. |
| R7 | `/` | Skip link | Link count 1. Activating it set hash `#main-content` and moved focus to `MAIN#main-content`. Works. |
| R8 | `/` | 30 Tab stops | 0 stops without an outline or box-shadow. Every stop had a visible indicator (outline 2 to 3 px). |
| R9 | Safety disclaimer | Focus | Opens with focus on "I Understand — Begin My Journey". Tab cycles Close, 3 helpline links, Begin, Close (trap works). `aria-modal="true"`, labelled by `safety-disclaimer-title`. After it closes on first load, focus is on `BODY`. |
| R10 | `/` | Targets under 24 px (measured, not axe) | 23 elements. Dots 8x8 (4) and 24x8 (1); nav links 63 to 102 x 20; skip link 1x1 (hidden until focus). |
| R11 | `/chat` | Targets under 24 px | 5 elements: Rename 22x22, Delete 22x22, "Details" 40x16, "Privacy" 50x18, skip link. Axe did not flag them (spacing exception may apply). |
| R12 | `/chat` | Landmarks | 1 `main`, 1 `banner`, 0 `nav` with a label, 0 `role=log`, `h1` "Chat with your AI Spiritual Guide". Composer textarea has `aria-label="Your message"`. |
| R13 | `/chat` | Helpline text in the page after the disclaimer closes | Not present (`/helpline|tele-?manas|14416|crisis/i` found nothing in `body.innerText`). |
| R14 | `/chat`, send "How do I find peace?" (500 or 429 mock) | Focus and live regions | Focus is on `BODY` 4 s after Enter (1280 px and 390 px). A `role="alert"` `aria-live="assertive"` error card appears and a `role="status"` banner. The error card carries "Tele-MANAS 14416 (24/7, free)". |
| R15 | `/chat` at 390 px, cookie banner visible | Send button | `elementFromPoint` at the centre of the Send button (317,646, 44x44) returns the cookie dialog. The banner covers the Send button. At 1280 px it does not. |
| R16 | `/` | Animations | With `prefers-reduced-motion: reduce`: 14 running animations, 10 infinite. Without the preference: 27, all infinite. The sources were not identified. |
| R17 | `/auth` | Inputs | `email` (autocomplete `email`, label "Email"); `password` (autocomplete `current-password`, label "Password"). Empty submit: no custom alert, focus stays on Email (browser validation). |
| R18 | `/` | `lang` | `html lang="en"` only. No other `lang` attributes on the page. |

---

## 3. Findings

Severity follows `CONVENTIONS.md`. "Type" uses the package terms. SC = WCAG 2.2 success criterion.

### A11Y-01 — Gold text on the cream ground fails contrast (verbatim label, attribution, "AI Generated")

| Field | Value |
|---|---|
| SC | 1.4.3 Contrast (Minimum), AA |
| Severity | **P1** |
| Type | Confirmed defect (runtime for one node, static for the rest) |
| Evidence | `[V-RUN]` R5: axe `color-contrast`, `/chat`, "AI Generated" badge, `#fbbd23` on `#f8f3e8` = **1.52:1**, 8.3 pt. `[V-STATIC]` `src/components/chat/ChatMessage.tsx:508` ("Guru teaching · verbatim" label, 11 px, `text-ojas`); `:563` (speaker attribution, `text-ojas`); `:524` and `:341` (badge, `text-ojas` when verified); `:622,632,662` (practice labels). `text-ojas` maps to `--ojas-gold` (`tailwind.config.ts:58`, `src/index.css:44`). `src/index.css:46-52` already states that gold text measures 1.57:1 and defines `--ojas-gold-ink` (`text-ojas-ink`, 4.59:1) for text. 34 `text-ojas` uses exist in `ChatMessage.tsx` and `CitationCard.tsx` combined. `text-saffron-gold` (same colour) is used 9 times in those two files, for example the speaker label at `CitationCard.tsx:291` `[COMPUTED]` 1.63:1 on the card colour. |
| Actual behaviour | The labels that tell a seeker "this is the teacher's verbatim words" and who is speaking are near-invisible on the light theme. |
| Expected | 4.5:1 for text under 18.66 px bold or 24 px. |
| Impact | Low-vision seekers and anyone in bright light cannot read the trust labels and the speaker name. This is the attribution that the product promises. |
| Remediation | Replace `text-ojas` and `text-saffron-gold` with `text-ojas-ink` on every text use. Keep the gold for fills, borders and icons. Add a lint or test guard (NEW-A11Y-2). |
| Acceptance | Axe `color-contrast` returns 0 violations on the `/chat` answer view in light and dark. Computed ratio is at least 4.5:1 for each label. |
| Verification | `[V-RUN]` + `[V-STATIC]` |

### A11Y-02 — Red text in the error card fails contrast (the card that carries the helpline)

| Field | Value |
|---|---|
| SC | 1.4.3, AA |
| Severity | **P1** (safety-relevant text) |
| Type | Confirmed defect |
| Evidence | `[V-RUN]` R5: "Something went wrong" `#ef4343` on `#f8ede9` = **3.29:1** (10.5 pt semibold); "Retry" button text 3.29:1 (9 pt). `[V-STATIC]` `ChatMessage.tsx:1298` (`text-sm font-semibold text-destructive`); `--destructive: 0 84% 60%` at `src/index.css:97`. `[COMPUTED]` 3.65:1 on the plain card colour. The same card holds the helpline line (`ChatMessage.tsx:1300-1303`, `data-testid="error-care-line"`, and the screenshot of R14). |
| Impact | The title and the Retry button are hard to read. The helpline sentence itself uses `text-foreground` and passes. |
| Remediation | Add a darker `--destructive-ink` token (about 45% lightness) for text on tinted backgrounds. Use it for text only. |
| Acceptance | Axe `color-contrast` 0 violations on the error state. |
| Verification | `[V-RUN]` |

### A11Y-03 — "Related, not a direct answer" label fails contrast and has three wordings

| Field | Value |
|---|---|
| SC | 1.4.3, AA; also 3.2.4 Consistent Identification, AA (advisory) |
| Severity | **P1** |
| Type | Confirmed defect (static + computed; the answer view did not render at runtime) |
| Evidence | `[V-STATIC]` `ChatMessage.tsx:1038-1043` (`text-xs font-medium text-amber-600/90`, 12 px); `:525` and `:344` (badge `text-amber-600` on `bg-amber-500/10`, 11 px); `src/pages/TeacherWords.tsx:257` (`text-amber-600`). `[COMPUTED]` amber-600 `#d97706` on the card colour = **3.07:1**; on card plus the 10% amber tint = **2.85:1**. The dark theme passes (`text-amber-400`, 8.51:1). Wording differs by file: "Related teaching — not a direct answer" (`ChatMessage.tsx:305`), "Related — not a direct answer" (`:497`), "Related, not a direct answer" (`:1038`, `TeacherWords.tsx:258`, backend text). The `src/types/provenance.ts:261` variant is a fourth: "Related Teaching (not a direct answer)". |
| Impact | This label is the honesty signal for every answer today, because no calibration profile exists (invariant 3). Many seekers cannot read it on the light theme. |
| Remediation | Use an amber text token with at least 4.5:1 on the tinted background (about `amber-800`, `#92400e`). Use one string key for the label in all views. Keep the label text per invariant 21; do not shorten it. |
| Acceptance | Computed and axe contrast at least 4.5:1 in both themes. One i18n key, one visible wording. |
| Verification | `[V-STATIC]` + `[COMPUTED]` |

### A11Y-04 — Meaning carried only by the `title` attribute

| Field | Value |
|---|---|
| SC | 1.3.1 Info and Relationships (A); 1.4.13 Content on Hover or Focus (AA); 4.1.2 (A) |
| Severity | **P2** |
| Type | Probable defect |
| Evidence | `[V-STATIC]` `ChatMessage.tsx:514-521`: the explanation of "Related", "Unverified" and "Verified" is in `title=` on a `<span>`. A `<span>` is not focusable, so keyboard and touch users cannot reach it. Also `:599` (`title={domain}`). The English strings in `title` are not passed through `t()` (for example "Related teaching: addresses surrounding spiritual concepts, not a direct direct answer to your specific query." has a doubled word). |
| Impact | A seeker who needs to know why a clip is "unverified" or "related" cannot read the reason without a mouse. The sentence is also not translated. |
| Remediation | Show the reason as visible text under the badge, or use a button that opens a popover (focusable, dismissible, hoverable). Pass it through `t()`. Fix the doubled word. |
| Acceptance | The reason is reachable by Tab and by touch; Esc closes it; the text is in the i18n files. |
| Verification | `[V-STATIC]` |

### A11Y-05 — The clip dialog has no accessible name

| Field | Value |
|---|---|
| SC | 4.1.2 Name, Role, Value (A); 1.3.1 (A) |
| Severity | **P1** |
| Type | Probable defect (not rendered at runtime) |
| Evidence | `[V-STATIC]` `src/components/chat/CitationCard.tsx:244` renders `<DialogContent>` with no `DialogTitle` and no `DialogDescription`. The heading is a plain `<h3>` at `:290`. Radix links `aria-labelledby` only to a `Dialog.Title`. `rg "DialogTitle" CitationCard.tsx` finds nothing. The other dialogs in the journey do use `DialogTitle` (`MemorySettingsModal.tsx:127`, `AccountDataCard.tsx:217`). The close control is labelled "Close" (`src/components/ui/dialog.tsx:51-52`). |
| Impact | A screen-reader user hears "dialog" with no name when the clip opens. Radix prints a console warning in development. |
| Remediation | Replace the `<h3>` with `DialogTitle` (visible). Add a `DialogDescription` ("Clip from <source>, starts at <time>") or `aria-describedby` to the quote. |
| Acceptance | `getByRole('dialog', {name: <clip title>})` resolves in the e2e test. Axe `aria-dialog-name` 0 violations with the dialog open. |
| Verification | `[V-STATIC]`; confirm with the e2e test in section 6 |

### A11Y-06 — No synchronised captions for clip video

| Field | Value |
|---|---|
| SC | 1.2.2 Captions (Prerecorded), A; 1.2.3 Audio Description or Media Alternative, A |
| Severity | **P1** (Level A) for the direct-video path; **Unknown** for the YouTube path |
| Type | Probable defect / Unverified assumption |
| Evidence | `[V-STATIC]` `CitationCard.tsx:247-254`: `<video controls autoPlay playsInline src=...>` with no `<track kind="captions">`. The YouTube path (`:261-272`) builds the embed URL without `cc_load_policy=1`; whether captions show depends on YouTube and on the viewer's setting. `grep "<track"` finds nothing under `src/components`. Mitigation that exists: the verbatim text of the clip shows next to the player (`CitationCard.tsx:311-318`, 12 px italic) and in the answer card (`ChatMessage.tsx:531-545`, 15 px serif, `<blockquote>`). `[COMPUTED]` the 12 px quote has 5.76:1 contrast and passes. |
| Impact | A deaf or hard-of-hearing seeker sees the whole clip text, but not timed captions. For a long clip the text and the speech cannot be matched. The transcript counts as a media alternative for audio-only content. For video with sound, WCAG 1.2.2 asks for captions. |
| Remediation | (a) Generate a WebVTT file for each served clip from the stored verbatim span and add `<track kind="captions" srclang=... default>`. (b) Add `cc_load_policy=1` to the YouTube embed. (c) Raise the quote text to at least 14 px. Whether auto-transcript text may be shown as captions is a decision (D-PA11Y2): captions from the auto-transcript carry its errors. |
| Acceptance | Direct-video test finds a `<track>` whose cue text equals the displayed verbatim text. NFR-A11Y-02 test exists. |
| Verification | `[V-STATIC]` |

### A11Y-07 — Quoted teacher text has no `lang` attribute

| Field | Value |
|---|---|
| SC | 3.1.2 Language of Parts (AA) |
| Severity | **P2** |
| Type | Probable defect (depends on corpus language, see Unknowns) |
| Evidence | `[V-STATIC]` `src/i18n.ts:22-27` sets `<html lang>` to the UI language. Quotes are never translated (root `CLAUDE.md`, invariant 16), so a seeker who picks Hindi or Telugu sees the UI in that language and the quote in the recording's language. The quote elements carry no `lang`: `ChatMessage.tsx:531` (`<blockquote>`), `:391`, `:1070`; `CitationPanel.tsx:111`; `CitationCard.tsx:311`. Only `LanguageSelector.tsx:329` and `LanguageOnboardingStep.tsx:81` set `lang` (on language names). `[V-RUN]` R18: the landing page has `html lang="en"` and no other `lang`. |
| Impact | A screen reader reads an English quote with a Hindi voice, or a Hindi quote with an English voice. The result is unintelligible. |
| Remediation | Add a `language` field per clip (from the transcript language, or from the script with a safe fallback to none) and set `lang` on the quote. Do not guess when the language is unknown: omit the attribute. |
| Acceptance | Unit test: a Hindi quote under an English UI renders `lang="hi"`; an English quote under a Hindi UI renders `lang="en"`. |
| Verification | `[V-STATIC]` |

### A11Y-08 — Focus drops to the page body after a send

| Field | Value |
|---|---|
| SC | 2.4.3 Focus Order (A); 3.2.2 On Input (A, advisory) |
| Severity | **P2** |
| Type | Confirmed behaviour on the error path; success path not tested |
| Evidence | `[V-RUN]` R14: after Enter in the composer, `document.activeElement` is `BODY` 4 s later at 1280 px and at 390 px (HTTP 500 mock). `[V-STATIC]` `ChatInterface.tsx` calls `inputRef.current.focus()` in several places (`:445,536,1151,1767,2079,2099,2123,2347`) but the runtime result shows none of them restores focus on this path. R9: after the safety disclaimer closes on first load, focus is also on `BODY`. |
| Impact | A keyboard user must Tab from the top of the page after each question. A screen-reader user loses their place. |
| Remediation | Keep focus on the composer after send (do not disable the textarea; use `aria-disabled` or `readOnly`). When the dialog closes on first load, move focus to the composer. |
| Acceptance | e2e test: after send, `document.activeElement` is the composer; after the disclaimer closes, it is the composer or the `main` landmark. |
| Verification | `[V-RUN]` (error path) |

### A11Y-09 — Target size under 24 px (landing dots, password toggle)

| Field | Value |
|---|---|
| SC | 2.5.8 Target Size (Minimum), AA (new in WCAG 2.2) |
| Severity | **P2** |
| Type | Confirmed defect |
| Evidence | `[V-RUN]` R1, R2: `/` axe `target-size` serious, 5 nodes: `button[aria-label="Go to slide N"]`, 8x8 px (active dot 24x8). `[V-STATIC]` `SampleWisdomSection.tsx:157-167` (`w-2 h-2`). `[V-RUN]` R3: `/auth` (and `/profile` redirected to it) axe `target-size` serious, 1 node: `button[aria-label="Show password"]`, 16x16 px; `[V-STATIC]` `AuthPage.tsx:1193-1198`. Not flagged by axe but measured small: Rename and Delete conversation 22x22, "Details" 40x16 (R11). |
| Impact | Seekers with tremor, large fingers, or a pointer that is hard to steer miss these controls. The password toggle matters on sign-in. |
| Remediation | Give each control a 24x24 px minimum hit area (padding or `min-h-6 min-w-6`), keep the visible dot small if wanted. Prefer 44 px for touch (the arrows already use 40 px). |
| Acceptance | Axe with `wcag22aa` returns 0 `target-size` violations on `/` and `/auth`. |
| Verification | `[V-RUN]` |

### A11Y-10 — No persistent help link to the helpline on chat pages

| Field | Value |
|---|---|
| SC | 3.2.6 Consistent Help (A, new in WCAG 2.2); product safety requirement |
| Severity | **P2** |
| Type | Product gap (the SC applies only if help is offered on several pages; here help is offered in some places and not in others) |
| Evidence | `[V-RUN]` R13: after the first-run notice closes, `/chat` has no helpline text. `[V-STATIC]` `CrisisLines` is used in `SafetyDisclaimer.tsx:110`, `SafetyPillarsSection.tsx`, `TermsPage.tsx`, and the crisis and error answers (`ChatMessage.tsx:5,165-172`). `grep -in "crisis\|helpline" src/components/landing/Footer.tsx src/components/landing/Navbar.tsx src/components/layout/AppShell.tsx src/components/chat/ChatHeader.tsx` returns nothing. The first-run notice shows once; the seeker cannot find it again from the chat. |
| Impact | A seeker in distress who dismissed the notice has no fixed place to find a number. This also matters for B16 (distress handling). |
| Remediation | Add one "Get help now" link to the app header and the public footer, in the same position on every page. It opens a small list from `CrisisLines` (numbers from `src/lib/crisisHelplines.ts`). Do not change the numbers. |
| Acceptance | e2e: on `/`, `/auth`, `/chat`, `/profile`, `/practices` the link exists, is in the same landmark, and is within 3 Tab stops of the top of its landmark. |
| Verification | `[V-RUN]` + `[V-STATIC]` |

### A11Y-11 — Cookie banner covers the Send button on phones

| Field | Value |
|---|---|
| SC | 2.4.11 Focus Not Obscured (Minimum), AA (new in WCAG 2.2); 2.5.8 |
| Severity | **P1** (blocks the core action until the seeker answers the banner) |
| Type | Confirmed at one viewport |
| Evidence | `[V-RUN]` R15: at 390x800, `elementFromPoint` at the Send button centre returns the cookie dialog. The banner is 131 px high, `top: 753` at 900 px height (`rt3` output). At 1280 px the Send button (1040,591) is not covered. A Tab-order probe on the landing page at 1280 px found 0 of 40 stops overlapped by the banner; that probe may have run after the banner was absent, so it is not conclusive. |
| Impact | A phone seeker types a question and cannot press Send until the banner is accepted or rejected. A keyboard user can still reach Send, but the focus ring is hidden under the banner. |
| Remediation | Make the banner a non-overlapping bar (reserve space with `padding-bottom` on `main`), or place it above the composer, or use `scroll-padding-bottom` equal to the banner height. |
| Acceptance | e2e at 390 px: with the banner visible, `elementFromPoint` at the Send centre returns the Send button; Tab to Send keeps its focus ring fully visible. |
| Verification | `[V-RUN]` |

### A11Y-12 — Looping animations continue under "reduce motion"; no pause control

| Field | Value |
|---|---|
| SC | 2.2.2 Pause, Stop, Hide (A); 2.3.3 Animation from Interactions (AAA, advisory) |
| Severity | **P2** |
| Type | Probable defect (the moving elements were not identified) |
| Evidence | `[V-RUN]` R16: `/` with `prefers-reduced-motion: reduce` still has 14 running animations, 10 infinite (27 without the preference). `[V-STATIC]` `HeroSection.tsx:76` uses `MotionConfig reducedMotion="user"`; CSS media queries exist at `src/index.css:245,711`, `styles/design-tokens.css:103`, `styles/mobile-chat-ux.css:131`, `styles/product-ux.css:187`. Candidates for the rest: `FloatingParticles.tsx`, `BackgroundParticles.tsx`, `EkamGoldenOrb.tsx` (not confirmed). The landing page offers no pause control for decorative motion. |
| Impact | Vestibular disorders, attention disorders and migraine. This app serves people who seek calm. |
| Remediation | Honour `prefers-reduced-motion` for every infinite animation. Add a visible "Pause animations" toggle, stored per viewer. |
| Acceptance | With the preference set, `document.getAnimations()` returns 0 infinite animations on `/`, `/chat`, `/auth`. |
| Verification | `[V-RUN]` (count) + `[NOT-TESTED]` (source) |

### A11Y-13 — Answer arrival is not announced (no live region on the message list)

| Field | Value |
|---|---|
| SC | 4.1.3 Status Messages (AA) |
| Severity | **P2** |
| Type | Probable defect (answer path did not render) |
| Evidence | `[V-STATIC]` `src/components/ai-elements/conversation.tsx:19` defines `role="log"`, but no file imports it (`rg "ai-elements/conversation"` finds only the definition). `MessageList.tsx` and `ChatInterface.tsx` have no `aria-live` or `role="log"`. `[V-RUN]` R12: 0 `role=log` on `/chat`. What exists: error card `role="alert" aria-live="assertive"` (`ChatMessage.tsx:1290-1292`), banner `role="status"` (`ChatErrorBanner.tsx:47-48`), Serene Mind offer `role="status"` (`ChatMessage.tsx:655-656`). The status pill `StreamingStatusPill.tsx` has no live role. The first-person answer is one clip, not a token stream, so a single polite announcement fits. |
| Impact | A screen-reader user sends a question and hears nothing until they navigate. They do not know whether the answer, an abstain or an error arrived. |
| Remediation | Add one visually hidden polite live region. Announce short text only: "Answer ready: a teaching clip from <teacher>", "No teaching matched your question", or the error. Do not announce the full quote. Keep `role="alert"` for errors and the crisis answer. |
| Acceptance | e2e: after a mocked answer, the live region text changes once and contains the teacher name; no token-by-token announcements. |
| Verification | `[V-STATIC]` |

### A11Y-14 — Delete-account flow: steps change with no focus move or announcement; some errors only as toasts

| Field | Value |
|---|---|
| SC | 2.4.3 (A); 4.1.3 (AA); 3.3.1 Error Identification (A) |
| Severity | **P2** |
| Type | Probable defect (static) |
| Evidence | `[V-STATIC]` `CancelFlow.tsx`: stages `intent`, `survey`, `offer`, `confirm` swap in place with `setStage(...)` (`:233-320`, `:317,419`). `rg "focus\(" CancelFlow.tsx` finds nothing. The step guard reports errors only through a toast (`:124-127`). Radix toast is a live region, so the message is announced, but the field is not marked invalid. The flow starts with "A short retention flow runs first — immediate deletion is one of its options" (`AccountDataCard.tsx:146`). The other dialogs (`AlertDialog` for clear data and erase memories, `AccountDataCard.tsx:214-229,244-`) use Radix and are accessible by construction. |
| Impact | A keyboard or screen-reader user who steps through the flow loses focus on each step. The path to deletion is longer than needed (this is also an open ethics item: B12, D-19). |
| Remediation | On each stage change, move focus to the stage heading (`tabIndex={-1}`). Add `aria-invalid` and an inline error next to the field. Keep a direct "Delete my account now" path on the first screen (D-19 decides the funnel). |
| Acceptance | e2e (mocked Supabase): after each "Continue", focus is on the new stage heading. The direct delete path takes at most 2 activations. |
| Verification | `[V-STATIC]` |

### A11Y-15 — Weak focus indicator on the composer

| Field | Value |
|---|---|
| SC | 1.4.11 Non-text Contrast (AA); 2.4.7 Focus Visible (AA) |
| Severity | **P2** |
| Type | Probable defect (static) |
| Evidence | `[V-STATIC]` `ChatComposer.tsx:386` sets `outline-none ... focus:ring-1 focus:ring-ojas/30` on the textarea. The wrapper changes its border to `border-ojas/50` when focused (`:291`). `[COMPUTED]` gold at 30% or 50% on the cream card is well under 3:1 (gold on cream is 1.57:1 at full strength). The other controls on the landing page had a 2 to 3 px outline (R8); the composer was not Tab-tested. |
| Impact | A keyboard user cannot see that the text box has focus. |
| Remediation | Use the same `focus-visible` ring as `ui/button.tsx` (solid 2 px, `--ring`) on the composer wrapper. Use a ring colour with 3:1 against the card. |
| Acceptance | Manual and Playwright: the focused composer shows an outline or ring of at least 2 px at 3:1 contrast. |
| Verification | `[V-STATIC]` + `[COMPUTED]` |

### A11Y-16 — Accessibility tests do not cover the journey or WCAG 2.2

| Field | Value |
|---|---|
| SC | Process (supports every SC) |
| Severity | **P1** (it is why A11Y-09 and A11Y-11 were not caught) |
| Type | Confirmed gap |
| Evidence | `[V-STATIC]` `tests/e2e/a11y-smoke.spec.ts:98` and `landing-accessibility.spec.ts:14` (no `wcag22aa`); no test opens the clip dialog, sends a message, renders the crisis answer or the abstain card, or opens settings or deletion; `eslint.config.js` has no `jsx-a11y` plugin. R4: the same `/chat` that has 0 violations when empty has 3 contrast violations after one failed send (R5). |
| Remediation | Section 6 and tasks NEW-A11Y-1 to 4. |
| Verification | `[V-STATIC]` + `[V-RUN]` |

### A11Y-17 — Smaller items (P3)

| ID | Item | Evidence | SC |
|---|---|---|---|
| A11Y-17a | Nested `<main>`: `DebugLayout` wraps public routes in `<main id="main-content">` (`App.tsx:170-174,339`) and `PublicShell` adds another (`PublicShell.tsx:18`). `/practices` has 2 `main` landmarks (R6). | `[V-RUN]` R6, `[V-STATIC]` | 1.3.1 (advisory) |
| A11Y-17b | Password toggle has `aria-pressed` and a label that changes ("Show password"/"Hide password"), which states the state twice (`AuthPage.tsx:1194-1195`). | `[V-STATIC]` | 4.1.2 (advisory) |
| A11Y-17c | First-run notice close icon is drawn at `opacity-50` (`SafetyDisclaimer.tsx:77`); the icon is pale in the screenshot. Escape triggers the same handler as "Begin" (`:43-46`), so Escape records acceptance. | `[V-STATIC]`, screenshot | 1.4.11 (AA, borderline); see D-PA11Y5 |
| A11Y-17d | The welcome message uses `•` characters inside one paragraph, so the three points run together (`ChatHelpers.tsx:65`; the screenshot of R14). No list structure. | `[V-STATIC]`, `[V-RUN]` | 1.3.1 |
| A11Y-17e | Copy uses terms a first-time seeker may not know: "verbatim", "abstains honestly", "stillness practice", "crisis care lines" (`ChatHelpers.tsx:65`). The badge text "Related, not a direct answer" does not say what to do next. | `[V-STATIC]` | 3.1.5 (AAA, advisory); see section 4 and NEW-A11Y-9 |
| A11Y-17f | `useDialogFocus` and Radix handle focus return on close. When the first-run notice closes on first load, there is no previous element, so focus is on `BODY` (see A11Y-08). | `[V-RUN]` R9 | 2.4.3 |

---

## 4. Per-criterion status (WCAG 2.2 A and AA criteria that apply to this app)

Status values: **Pass** (evidence names the check), **Fail** (finding named), **Partial**, **Not tested**. "Pass" covers only what was tested; it is not a conformance claim for the whole app.

| SC | Level | Status | Evidence / finding |
|---|---|---|---|
| 1.1.1 Non-text Content | A | Partial | Axe `image-alt`, `button-name`, `svg-img-alt`: 0 violations on `/`, `/auth`, `/chat` (R2-R4). Icons next to text are `aria-hidden` (`ChatMessage.tsx:507`). Clip thumbnails and the wisdom card image: Not tested. |
| 1.2.1 Audio-only and Video-only (Prerecorded) | A | Partial | Verbatim text shown with the clip (`CitationCard.tsx:311`, `ChatMessage.tsx:531`). Serene Mind audio transcript: Not tested. |
| 1.2.2 Captions (Prerecorded) | A | **Fail** (direct video) / Not tested (YouTube) | A11Y-06 |
| 1.2.3 Audio Description or Media Alternative | A | Partial | Same transcript text; A11Y-06 |
| 1.3.1 Info and Relationships | A | Partial | Landmarks and headings present (R12). A11Y-04, A11Y-17a, A11Y-17d. |
| 1.3.2 Meaningful Sequence | A | Not tested | |
| 1.3.4 Orientation | AA | Not tested | |
| 1.3.5 Identify Input Purpose | AA | Pass (auth) | `autocomplete` `email`, `current-password`, `new-password`, `name` (`AuthPage.tsx:1148,1167,1186`); R17. |
| 1.4.1 Use of Color | A | Not tested | The "Verified" and "Unverified" badges differ by colour and by text; text is present. |
| 1.4.2 Audio Control | A | Partial | Clip video has native controls (pause); it autoplays after a user click (`CitationCard.tsx:249`). Serene Mind audio: Not tested. |
| 1.4.3 Contrast (Minimum) | AA | **Fail** | A11Y-01, A11Y-02, A11Y-03. Incomplete axe rows: 55 nodes on `/`, 16 on `/auth` need a human review. |
| 1.4.4 Resize Text | AA | Not tested | |
| 1.4.5 Images of Text | AA | Not tested | The wisdom card generator output is an image; its alt text was not checked. |
| 1.4.10 Reflow | AA | Not tested | One 390 px load only (A11Y-11). |
| 1.4.11 Non-text Contrast | AA | Partial / **Fail** (static) | A11Y-15, A11Y-17c |
| 1.4.12 Text Spacing | AA | Not tested | |
| 1.4.13 Content on Hover or Focus | AA | **Fail** (static) | A11Y-04 |
| 2.1.1 Keyboard | A | Partial | Landing: 30 Tab stops, all reachable (R8). Safety dialog trap works (R9). Composer send by Enter works (R14). Clip dialog, citation panel, settings: Not tested. |
| 2.1.2 No Keyboard Trap | A | Pass (safety dialog) | R9: Escape closes; Tab cycles inside by design. Others Not tested. |
| 2.1.4 Character Key Shortcuts | A | Not tested | `SlashCommandMenu` and `CommandPalette` exist; their single-key bindings were not checked. |
| 2.2.1 Timing Adjustable | A | Pass (static) | The quota reset text "Resets in N hours" is information, not a session timer (`QuotaAuthPrompt.tsx:20-22`). Session-expiry handling (`SessionExpiredHandler.tsx`): Not tested. |
| 2.2.2 Pause, Stop, Hide | A | **Fail** (probable) | A11Y-12 |
| 2.3.1 Three Flashes | A | Not tested | |
| 2.4.1 Bypass Blocks | A | Pass | R7: skip link works on `/`. |
| 2.4.2 Page Titled | A | Not tested | |
| 2.4.3 Focus Order | A | **Fail** (error path) | A11Y-08, A11Y-14 |
| 2.4.4 Link Purpose | A | Partial | Play and Open-source links have names (`ChatMessage.tsx:576,587,596`). External links do not say they open a new tab: Not tested. |
| 2.4.5 Multiple Ways | AA | Not tested | |
| 2.4.6 Headings and Labels | AA | Partial | `h1` on `/chat` (R12). |
| 2.4.7 Focus Visible | AA | Partial | Pass on landing (R8). A11Y-15 for the composer. |
| 2.4.11 Focus Not Obscured (Min) | AA | **Fail** (phone, send button) | A11Y-11. Landing probe inconclusive. |
| 2.5.1 Pointer Gestures | A | Not tested | `KGConceptMap` and chat scroll gestures were not checked. |
| 2.5.2 Pointer Cancellation | A | Not tested | |
| 2.5.3 Label in Name | A | Pass (static) | "Play clip" is inside the name "Play clip: <source> at <time>" (`ChatMessage.tsx:472,576`). |
| 2.5.4 Motion Actuation | A | Not tested | |
| 2.5.7 Dragging Movements | AA | Not tested | No drag-only control was found in the journey files read. The knowledge-graph page (`KGConceptMap.tsx`) uses pointer drag; it is outside the core journey. |
| 2.5.8 Target Size (Minimum) | AA | **Fail** | A11Y-09 |
| 3.1.1 Language of Page | A | Pass | `html lang` follows the UI language (`i18n.ts:22-27`; R18). |
| 3.1.2 Language of Parts | AA | **Fail** (probable) | A11Y-07 |
| 3.2.1 On Focus / 3.2.2 On Input | A | Not tested | |
| 3.2.3 Consistent Navigation | AA | Not tested | |
| 3.2.4 Consistent Identification | AA | Partial | Label wording differs (A11Y-03). |
| 3.2.6 Consistent Help | A | Partial | A11Y-10 |
| 3.3.1 Error Identification | A | Partial | Auth: browser validation on empty submit (R17). Cancel flow uses toasts (A11Y-14). Error card is `role="alert"` (R14). |
| 3.3.2 Labels or Instructions | A | Pass (auth, composer) | Email, Password, Verification code have `<Label>` (`MFAChallengePage.tsx:151`); composer has `aria-label` (R12). |
| 3.3.3 Error Suggestion | AA | Not tested | |
| 3.3.4 Error Prevention (Legal, Financial, Data) | AA | Partial | Account deletion uses a confirm step (`CancelFlow.tsx:406`, `confirm-box`) and `AlertDialog`s. |
| 3.3.7 Redundant Entry | A | Not tested | Sign-up, age confirmation (`/auth/confirm-age`) and feedback forms were not walked. |
| 3.3.8 Accessible Authentication (Minimum) | AA | Pass (static) | Email and password with `autocomplete`; paste not blocked (`rg onPaste` finds nothing in the auth pages); one-time code has `autoComplete="one-time-code"` (`MFAChallengePage.tsx:155`); no CAPTCHA found (`rg -i captcha\|turnstile` finds nothing). Google and Apple buttons are alternatives. |
| 4.1.2 Name, Role, Value | A | **Fail** (probable) | A11Y-05. Axe `aria-*` and `button-name`: 0 violations on `/`, `/auth`, `/chat`. |
| 4.1.3 Status Messages | AA | Partial / **Fail** (answer arrival) | A11Y-13. Error card and banner announce (R14). |

Criteria not in the table (for example 1.4.6, 2.4.9, 3.1.5) are AAA and out of scope, except where a finding names them as advisory.

---

## 5. Gate mapping

IDs are those of `FINAL_PRODUCTION_RELEASE_READINESS.md`.

| Gate item | Link to this file | Effect |
|---|---|---|
| **C7** Accessibility of the chat flow. Pass: "No unresolved level-A or level-AA failure on the core journey." | Findings with a failing SC on the core journey: A11Y-01, 02, 03 (1.4.3); A11Y-05 (4.1.2); A11Y-06 (1.2.2, Level A); A11Y-07 (3.1.2); A11Y-08 (2.4.3); A11Y-09 (2.5.8); A11Y-11 (2.4.11); A11Y-12 (2.2.2); A11Y-13 (4.1.3); A11Y-04 (1.4.13); A11Y-14 (3.3.1, 2.4.3); A11Y-15 (1.4.11). | **C7 is not met. Each of these blocks C7 until fixed or until the owner decides a documented exception (D-PA11Y1).** None of these is a security, privacy, data-integrity, cross-user or attribution class, so a P1 item may stay open only under the written risk acceptance in section 2 of that file (named finding, reason, mitigation, end date). |
| C7 (process) | A11Y-16, section 6 | The a11y test must cover the journey and carry `wcag22aa` before C7 can be called passed. A manual screen-reader session (NFR-A11Y-03) is `[HUMAN]`. |
| B16 Distress known gap handled | A11Y-02 (error card text), A11Y-10 (persistent helpline) | Proposed: close A11Y-02 and A11Y-10 with B16, because a seeker who cannot read or find the helpline is a distress-handling gap. Not currently written in B16. Decision D-PA11Y3. |
| B12 User deletion honoured | A11Y-14 | Proposed: the deletion flow must work by keyboard and screen reader on staging when B12 is tested. Decision D-PA11Y3. |
| B18 Invited users only | none | No change. |
| Gate B in general | none of B1 to B18 names accessibility | If invited users include people who use assistive technology, the owner may move C7 items A11Y-09, 11 and 13 up to Gate B (D-PA11Y3). |
| Gate A | none | No change. |
| P3 items (A11Y-17a to f) | none | Do not block any gate. |

Claim limits: until C7 passes, the product may not claim "accessible", "WCAG 2.2 AA" or "WCAG compliant". It may say "automated checks pass on N pages" and name the pages.

---

## 6. Acceptance criteria and tests

Prefer extending the existing smoke test. Each row names a pass condition that a command can check.

| ID | Requirement | Test | Pass condition | Covers |
|---|---|---|---|---|
| AC-A11Y-1 | Axe runs with the WCAG 2.2 tag on every route and state in the journey. | In `tests/e2e/a11y-smoke.spec.ts` change `withTags` to `['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']` (line 98). In `landing-accessibility.spec.ts` change line 14 the same way. | 0 `serious` or `critical` violations on `/`, `/auth`, `/chat`, `/practices`. Today: `target-size` fails on `/` (5 nodes) and `/auth` (1 node). The test fails until A11Y-09 is fixed. | NFR-A11Y-01, A11Y-09, A11Y-16 |
| AC-A11Y-2 | Axe also runs on the states, not only the empty page. | New tests in the same file with mocked `/api/chat` (Playwright `page.route`): (a) answer with one clip, (b) abstain, (c) crisis redirect, (d) error 500, (e) clip dialog open, (f) report-clip form open. | 0 `serious` or `critical` in each state. Today (d) fails on `color-contrast` (3 nodes). | A11Y-01, 02, 03, 05 |
| AC-A11Y-3 | Settings and deletion states. | Seed a fake session (`seedAuth`) and mock Supabase calls; open `/profile?tab=settings`, memory settings, delete-account flow stages 1 to 4. | 0 `serious` or `critical` per stage. | A11Y-14 |
| AC-A11Y-4 | Clip dialog has a name and transcript text. | e2e: click Play clip; `getByRole('dialog', {name: /./})` resolves; the dialog contains the verbatim quote text equal to the stored `verbatim_text`. | Pass. | A11Y-05, NFR-A11Y-02 |
| AC-A11Y-5 | Captions on direct video. | e2e with a direct-video citation: `video > track[kind="captions"]` exists and its cue text matches the quote. | Pass. YouTube path: embed URL contains `cc_load_policy=1`. | A11Y-06 |
| AC-A11Y-6 | Language of parts. | Vitest: render `GuruTeachingCard` with a Hindi quote under UI `en`, and an English quote under UI `hi`. | `blockquote[lang="hi"]` and `blockquote[lang="en"]`. Unknown language: no `lang` attribute. | A11Y-07 |
| AC-A11Y-7 | Contrast of the label set. | Vitest or Node script using the tokens in `src/index.css`: for each of `text-ojas-ink`, the amber text token and the destructive text token, compute the ratio on card, background and tinted backgrounds, light and dark. | Each at least 4.5:1. A guard fails the build if `text-ojas` or `text-saffron-gold` is used on a text node (NEW-A11Y-2). | A11Y-01, 02, 03 |
| AC-A11Y-8 | Focus after send and after dialog close. | e2e: send a question; check `document.activeElement` is the composer after the response. Close the first-run notice; check focus is in `main` or the composer. | Pass. | A11Y-08 |
| AC-A11Y-9 | Live region. | e2e: after a mocked answer, the hidden polite region text changes once. After a mocked error, a `role=alert` exists. | Pass. No more than 1 polite update per answer. | A11Y-13 |
| AC-A11Y-10 | Cookie banner does not cover the composer. | e2e at 390x800 with the banner visible: `elementFromPoint` at the Send centre is the Send button. | Pass. | A11Y-11 |
| AC-A11Y-11 | Persistent help link. | e2e on 5 routes: link "Get help now" present, same landmark, opens the list from `src/lib/crisisHelplines.ts`. | Pass. Existing `crisisHelplines.test.ts` still passes. | A11Y-10 |
| AC-A11Y-12 | Reduced motion. | e2e with `reducedMotion: 'reduce'`: count infinite animations. | 0 on `/`, `/chat`, `/auth`. | A11Y-12 |
| AC-A11Y-13 | Lint. | Add `eslint-plugin-jsx-a11y` (recommended rules) to `eslint.config.js`. | `npm run lint` passes. New violations fail CI. Adding the package needs owner approval of the dependency (open-source licence: MIT). | A11Y-16 |
| AC-A11Y-14 | Manual pass. | One screen-reader session (NVDA with Firefox or Chrome on Windows, VoiceOver on iOS) over the journey in section 7, task NEW-A11Y-10. | Task list completed; a signed record exists (D-10 rule). Not run. `[HUMAN]` | NFR-A11Y-03, C7 |
| AC-A11Y-15 | Zoom, reflow, spacing. | Manual: 200% zoom, 320 px width, WCAG text-spacing bookmarklet on the journey. | No loss of content or function. Not run. `[HUMAN]` | 1.4.4, 1.4.10, 1.4.12 |

---

## 7. Tasks

Each task names files, non-goals and rollback. Tasks change `src/` or tests; this audit did not.

| ID | Task | Files | Non-goals | Rollback | Closes |
|---|---|---|---|---|---|
| NEW-A11Y-1 | Add `wcag22aa` to both axe tests; extend the smoke test to the states in AC-A11Y-2 and AC-A11Y-3. | `tests/e2e/a11y-smoke.spec.ts`, `tests/e2e/landing-accessibility.spec.ts` | Do not disable new rules to make the test pass. Do not weaken the severity filter. | Revert the test files. | A11Y-16, AC-1 to 3 |
| NEW-A11Y-2 | Contrast: use `text-ojas-ink` for gold text; add a `--destructive-ink` token; add an amber text token with 4.5:1; one i18n key for the "Related, not a direct answer" label; guard script that fails on `text-ojas` or `text-saffron-gold` in text positions. | `src/index.css`, `tailwind.config.ts`, `src/components/chat/ChatMessage.tsx`, `CitationCard.tsx`, `src/pages/TeacherWords.tsx`, `src/types/provenance.ts`, `scripts/guards/lesson_guards.py` or a Vitest check | Do not remove or reword the label's meaning (invariant 21). Do not change fills, borders or icons. | Revert the token and class changes. | A11Y-01, 02, 03 |
| NEW-A11Y-3 | Clip dialog: `DialogTitle`, `DialogDescription`; keep the visible heading. Replace `title=` explanations with visible text or a focusable popover; pass through `t()`. | `src/components/chat/CitationCard.tsx`, `ChatMessage.tsx:514-521` | Do not change the clip URL, the playback window or the quote text. | Revert. | A11Y-04, 05 |
| NEW-A11Y-4 | Captions: WebVTT per clip from the stored verbatim span; `<track>`; `cc_load_policy=1` on the YouTube embed; raise quote text to 14 px or more. | `CitationCard.tsx`; a backend endpoint or a client-side Blob URL built from `verbatim_text` | Do not generate new text. Do not use an LLM. Cue text equals the stored text. Do not translate. | Remove the `<track>`. | A11Y-06 |
| NEW-A11Y-5 | `lang` on quotes from a clip language field; omit when unknown. | `ChatMessage.tsx`, `CitationPanel.tsx`, `CitationCard.tsx`; `src/lib/firstPersonService.ts` schema (add an optional field) | Do not detect language by guessing. Do not change backend payloads without a decision (D-PA11Y4). | Revert; field optional. | A11Y-07 |
| NEW-A11Y-6 | Focus and live region: keep focus on the composer after send; one hidden polite region for answer, abstain and error; focus the composer or `main` after the first-run notice closes. | `ChatInterface.tsx`, `ChatComposer.tsx`, `MessageList.tsx`, `SafetyDisclaimer.tsx` | Do not announce the full quote. Do not add token-by-token announcements. | Revert. | A11Y-08, 13 |
| NEW-A11Y-7 | Target size and banner: 24 px minimum hit area on dots, password toggle, rename, delete, "Details"; cookie banner reserves space or sits above the composer on narrow screens. | `SampleWisdomSection.tsx`, `AuthPage.tsx`, `DesktopSidebar.tsx` (rename and delete), `CookieConsentBanner.tsx`, `ChatInterface.tsx` | Do not change the banner's consent logic or wording. | Revert. | A11Y-09, 11 |
| NEW-A11Y-8 | Persistent "Get help now" link in `AppShell` and `PublicShell` footer or header; reuse `CrisisLines`. Composer focus ring. Reduced motion: stop every infinite animation under the preference; add a pause toggle. | `src/components/layout/AppShell.tsx`, `PublicShell.tsx`, `src/components/common/CrisisLines.tsx`, `ChatComposer.tsx`, `FloatingParticles.tsx`, `BackgroundParticles.tsx`, `EkamGoldenOrb.tsx` | Do not add or edit phone numbers. Do not change `config/helplines.yaml`. | Revert. | A11Y-10, 12, 15 |
| NEW-A11Y-9 | Delete-account flow: focus on stage heading; inline errors with `aria-invalid`; plain-language copy review of the welcome text, the label help text, and the quota and error messages (short sentences, no terms such as "verbatim", "abstains"); list markup for the welcome bullets. | `CancelFlow.tsx`, `AccountDataCard.tsx`, `ChatHelpers.tsx:65`, i18n files | Do not decide the retention funnel (D-19). Do not change the helpline text. | Revert. | A11Y-14, A11Y-17d, A11Y-17e |
| NEW-A11Y-10 | Manual pass: one screen-reader session, one keyboard-only session, 200% zoom, 320 px, text spacing; record results as a signed note. Add `eslint-plugin-jsx-a11y` if D-PA11Y6 approves. | `docs/` (notes), `eslint.config.js`, `package.json` | Do not claim conformance from this pass alone. | Remove the plugin. | NFR-A11Y-03, C7 |

Order: NEW-A11Y-1 first (it shows the failing state), then 2, 7, 3, 6, 8, 5, 4, 9, 10.

---

## 8. Open questions (PROPOSED)

| ID | Question | Why it matters | Default if no answer |
|---|---|---|---|
| PROPOSED D-PA11Y1 | Which WCAG 2.2 level binds the first invited release: AA on the core journey (C7 as written), or a smaller written subset? | Sets whether A11Y-06, 07 and 12 block Gate C. | AA on the core journey, per C7. |
| PROPOSED D-PA11Y2 | May captions be built from the auto-transcript, when the transcript is flagged "auto" (`isAutoTranscript`)? | Captions will repeat transcript errors. | Yes, with the visible "auto-transcript" note, as the text already shows today. |
| PROPOSED D-PA11Y3 | Move A11Y-02, 10 (helpline) and A11Y-14 (deletion) into Gate B (B16, B12)? Move A11Y-09, 11, 13 if invited users include assistive-technology users? | Today Gate B names no accessibility item. | Add A11Y-02, 10 to B16 and A11Y-14 to B12. |
| PROPOSED D-PA11Y4 | Does the backend or the corpus record a language per clip? If not, who supplies it (corpus owner or a one-time offline tag)? | Needed for `lang` on quotes (A11Y-07). Unknown. | Add an optional `language` field; omit `lang` when absent. |
| PROPOSED D-PA11Y5 | Should Escape on the first-run safety notice count as acceptance? | Today Escape and "Begin" both record it (`SafetyDisclaimer.tsx:43-46`). | Keep; confirm with the owner and the clinician (C1). |
| PROPOSED D-PA11Y6 | Approve `eslint-plugin-jsx-a11y` (MIT) and, if wanted, `vitest-axe` as dev dependencies? | Package rule: dependencies must be open source; installs need approval. | Approve `eslint-plugin-jsx-a11y`. |
| PROPOSED D-PA11Y7 | Who runs the screen-reader session and in which languages? | NFR-A11Y-03 needs a person. | Owner names a tester; first session in English, second in Hindi or Telugu. |

---

## 9. Verified, assumptions, unknowns

### Verified

- `[V-STATIC]` The smoke and landing a11y tests carry no `wcag22aa` tag (`a11y-smoke.spec.ts:98`, `landing-accessibility.spec.ts:14`). No `jsx-a11y` plugin is configured.
- `[V-RUN]` Axe with `wcag22aa`: `/` has 1 violation (`target-size`, 5 nodes); `/auth` has 1 (`target-size`, 1 node); `/chat` has 0 when empty and 1 (`color-contrast`, 3 nodes) after a failed send. Desktop 1280x900; `/` also in dark scheme with the same result.
- `[V-RUN]` Skip link works on `/`. The safety notice traps Tab, is labelled and moves focus to its action. Landing Tab stops all show a focus indicator.
- `[V-RUN]` After a send on the error path, focus is on `BODY`. At 390 px the cookie banner covers the Send button.
- `[V-RUN]` The error card is an assertive alert and includes the Tele-MANAS number. The helpline is not on `/chat` after the first-run notice closes.
- `[COMPUTED]` Gold text on cream 1.52 to 1.63:1; amber-600 label 2.85 to 3.07:1; destructive text 3.29 to 3.65:1; `text-ojas-ink` 4.59:1 (from the code comment at `src/index.css:46-52`, not re-computed here).
- `[V-STATIC]` The clip dialog has no `DialogTitle`; the video has no `<track>`; quotes have no `lang`; `role="log"` component is unused; the `title` attribute carries the label explanations.

### Assumptions

- The Tailwind default `amber-600` (`#d97706`) and `amber-500` apply, because `tailwind.config.ts` has no `amber` override (checked by `grep`; no match).
- The error state seen with the 500 mock has the same markup as a real backend error. The 429 mock produced the "cannot reach teaching service" banner, not the quota prompt, so the quota prompt did not render.
- The first-person answer arrives as one block, not a token stream. If the non-first-person path streams tokens, A11Y-13 needs a second rule (announce once at the end).
- The 390 px overlap (R15) holds on real phones with browser chrome. Browser toolbars may change the viewport height.

### Unknowns

- The answer card, "Play clip", the clip dialog, the abstain card, the crisis answer, memory settings and account deletion did not render at runtime. Their rows in section 4 rest on code reading.
- Whether YouTube shows captions in the embedded player for these videos.
- Which animations still run under reduced motion (10 infinite).
- Language of each clip, and whether the backend sends it.
- Focus after send on the success path.
- Behaviour with a real screen reader, voice control, 200% zoom, 320 px reflow, text spacing, forced colours.
- Whether axe "incomplete" contrast nodes (55 on `/`, 16 on `/auth`, 3 on `/chat`) pass. They need a human check.
- Whether the same code exists on `origin/main@46b808fb` (this audit read `fb5cab0f`).
- Session-expiry and time-limit behaviour (2.2.1) and sign-up redundant entry (3.3.7).
