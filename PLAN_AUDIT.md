# Feature-Wave Plan Audit v2 — re-check after further work + fixes

Second pass, replacing the first pass's findings (the first pass found real gaps — 861MB DB dumps with
PII staged for commit, a crisis-answer feedback widget with no safety exclusion, a broken i18n language
switch, a guided tour that never re-triggered, count-based conversation retention that disagreed with the
backend's days-based schema, and several unwired features). Since then, both I and you closed almost all
of them; this document is the current, authoritative status. Verified by: full diff/grep re-check of
every item, `npm test` (233 passed, 0 failed), `npm run build` (succeeds), and targeted backend `pytest`
on the touched modules (21 passed). Not re-run: the live Docker stack (see Demo Readiness below for what
that means for you).

Legend: ✅ done & verified · 🟡 minor/polish, not blocking · ❌ still missing.

---

## 🔴 Safety & hygiene — RESOLVED
- **A1 DB dumps (861MB + PII)** — ✅ unstaged, `.gitignore` now excludes `*.dump *.snapshot *.rdb
  supabase_dump.sql`. Reconfirmed clean in this pass.
- **A2 Engagement card on crisis answers** — ✅ `isCrisisAnswer()` guard added in `ChatMessage.tsx`;
  suppresses both `InlineActions` and `EngagementCard` on any answer matching the 🆘/crisis/helpline
  signature. This is the one item I'd double-check by eye once against a real distress reply in the UI
  before a demo (see Demo Readiness) — regex-based, not plumbed from backend intent, so it's a pattern
  match on the crisis helpline text, not a structural guarantee.

## Feature-by-feature — current status
- **F1 Serene Mind Audio+Breath merge** — ✅ now wired. `MediaTab` accepts `externalIsPlaying`; the
  audio tab passes the breath's own `isPlaying` state in, and a `useEffect` slaves the hidden YouTube
  iframe to it (`play/pause` follow the breath controls). Two tabs (Audio, Video), session/streak intact.
- **F2 Colloquial practices copy** — 🟡 mostly done. `purpose`/`howItWorks` now reach English users too
  (the `lang==='en'` short-circuit is gone and `PracticesPage.tsx` now calls `getLocalizedPractice`).
  **Remaining:** `benefits` in `en.json` are still clinical ("Calms the amygdala — lowers cortisol...").
  Cosmetic, not launch-blocking — soften before a broader release, not before a demo.
- **F3 UI language en/hi/te(+kn/ta/mr)** — ✅ sync seam present (`profileStorage.saveProfile` writes the
  i18n detector key + calls `i18n.changeLanguage`). Coverage is now strong: en/hi/te/kn/ta all at
  **828/828 keys (100%)**, contamination essentially gone (te.json's 176 Hindi-in-Telugu values are down
  to 1 stray string). **mr (Marathi) is at 362/828 (44%)** — you extended scope to 3 more languages
  beyond the plan's en/hi/te; kn and ta hit full parity, mr didn't finish. Not a regression, just
  unfinished scope-add. `PracticesPage`/`LanguageSelector` literal sweep: partially done (both files now
  call `t()`, not exhaustively swept but no longer 0%).
- **F4 Mood check-in** — 🟡 unchanged from first pass: wired into first-visit flow, 5 chips (plan said
  ~6), mapping differs from the plan's exact wording but is reasonable, no streak-aware CTA, welcome
  message doesn't acknowledge mood. Functions correctly; cosmetic gaps only.
- **F5 Gemini via OpenRouter (translation only)** — ✅ works, tests pass (11/11 across both new test
  files). **Still default-on** (`gemini_translation_enabled=True`) rather than the plan's "default to
  Sarvam" — this was flagged before as matching your actual intent (you want Gemini for translation), so
  treating it as accepted rather than a bug unless you say otherwise.
- **F6 Engagement closer + crisis exclusion** — ✅ the crisis-exclusion gap (A2) is fixed. The backend
  deterministic-closer-in-generation from the original plan was never built (a frontend card exists
  instead, which is arguably the better implementation) — documented, not re-flagging as missing.
- **F7 Microphone everywhere** — ✅ `NotesPanel.tsx` and `MemoryManager.tsx` (both textareas) now use
  the proven `useSpeechRecognition` hook — not the reinvented `useVoiceInput`. Chat composer unchanged
  (already had it). All three planned sites now have mic support.
- **F8 Guided tour re-trigger** — ✅ `askmukthiguru_tour_shown_count` gates re-show up to 3 times;
  skip/Escape route to `onDismiss` (does not mark completed), only "Got it" sets
  `askmukthiguru_tour_completed`. Verified in source.
- **F9 Conversations → Profile + deletion** — ✅ now solid. `getRetentionDays`/`setRetentionDays`/
  `purgeConversationsByAge` all exist and are **days-based** (matches the migration's
  `retention_days` column — UI and backend now agree). `App.tsx` purges on load. Delete All correctly
  **excludes the current conversation** (`c.id !== currentId`) before deleting. Per-conversation delete +
  typed-`DELETE` Delete All both present.
- **F10 Memory summarized reflections** — 🟡 summary half done and tested (`test_memory_summary.py`
  passes). Merge-or-append seam (`merge_with`) still not implemented — new writes still always insert.
  Not a regression; deferred as originally noted. Low risk (memories aren't demo-critical).
- **F11 Retention hooks** — 🟡 forgiving streak (≥30s partial counts, zero-duration mood check-ins
  excluded) is fixed and verified in `meditationStorage.ts`. Post-completion reminder prompt and the
  DailyTeaching streak chip were not attempted in this pass — still open, low-stakes for a demo.
- **F12 Backend backlog** — ✅ unchanged/confirmed good (doctrine_terms, ColBERT fallback, doctrine_faqs
  graceful-empty, compliance_logger writable dir — all pre-existing and intact).

## Verification run this pass
- `npm test` → **233 passed, 6 skipped, 0 failed** (48/49 files).
- `npm run build` → **succeeds** (warnings only: deprecated esbuild flag, stale browserslist data,
  one non-blocking dynamic-import chunking note — none are errors).
- `cd backend && .venv/bin/pytest tests/test_gemini_translation_provider.py
  tests/test_routing_translation_provider_gemini.py tests/test_memory_summary.py
  tests/test_doctrine_terms.py` → **21 passed**.
- New translation scripts (`scripts/apply_offline_translations*.py`, `translate_locales.py`, etc.)
  scanned for hardcoded secrets — clean.
- DB dumps reconfirmed unstaged and gitignored.

---

## Demo readiness — go / no-go

**Frontend: go.** Tests green, build green, all P0/P1 items from the first audit pass are now fixed and
re-verified in source. Safe to demo the chat UI, Serene Mind, mood check-in, mic, guided tour,
Profile → Conversations, and language switching (en/hi/te/kn/ta — skip Marathi in the demo, it's 44%
translated and will visibly fall back to English mid-flow).

**One thing I have not verified because it needs a live browser/backend session, not source reading:**
click through the actual Serene Mind Audio tab once and confirm the iframe genuinely starts/stops with
the breath animation (the wiring is correct in source — `externalIsPlaying` flows through — but YouTube
iframe autoplay policies can silently block a `postMessage`'d `playVideo()` in some browsers). A 30-second
manual check before the demo removes all doubt.

**Backend: conditional go — one step outstanding from the prior session, not from this feature wave.**
`handoff.md`'s Phase-0 live-verify (restart backend, flush caches, confirm the doctrine-terms rewrite
answers "Ekam" not "Akam" in a running query) was never re-run against a live Docker stack in this
session — I only ran the self-contained, mocked pytest files above, which don't touch a live LLM/DB.
If the backend has been restarted and queried since that handoff was written, you're clear; if not, run
that one check before relying on live chat answers in the demo — it's a 5-minute check
(`docker compose restart backend && make flush-cache`, then one `/api/chat` query) and it's the only
piece of this whole audit I could not verify from source alone.

**Bottom line:** you're in good shape for a demo. The two things worth 5 minutes before you present: (1)
click through Serene Mind Audio once in a real browser, (2) confirm the backend has been restarted since
the doctrine-terms fix if you haven't queried it live recently. Everything else checked out.
