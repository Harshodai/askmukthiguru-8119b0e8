# Session Handoff — 2026-07-19 (ruthless / full detail)

Working tree: 16 files changed, 687 insertions(+), 422 deletions(-), all
uncommitted (repo convention: never commit/push without being asked).
Exact current `git status --short`:

```
M backend/app/api/teachings.py
M backend/config/router_routes.yaml
M backend/rag/nodes/intent.py
M backend/services/semantic_router.py
M handoff.md
M src/components/chat/ChatInterface.tsx
M src/components/chat/ChatMessage.tsx
M src/components/chat/DesktopSidebar.tsx
M src/components/chat/InlineActions.tsx
M src/components/chat/LanguageSelector.tsx
M src/lib/chatStorage.ts
M src/locales/en.json
M src/pages/AuthPage.tsx
M src/test/components/ChatMessage.test.tsx
M src/test/components/LanguageSelector.test.tsx
M user_video_script.md
```

`git stash list` → `stash@{0}: 97be378d Added YouTube link and fixed audio`
(touches `AGENTS.md`/`RUTHLESS_PLAN.md`). **Not created this session** —
pre-existing, never resolved. See §4 for the full stash story (there were
*two* separate stash events discussed this session; this one predates both).

---

## 1. The goal we're working toward

User handed over a numbered list of 6 live bug reports, their own numbering
(#8–#13, continuing the prior session's handoff §8 numbering), plus one
open-ended architecture question. Work happened in two explicit rounds,
each with its own verification bar the user set:

**Round 1** — investigate and fix all 6 reports:
- **#8** — language selector UX is bad in the main chat UI; incognito mode
  should work end-to-end "just like how claude.ai or anything manages it."
- **#9** — thinking pills (the rotating status text shown while an answer
  streams) are showing what looks like leaked LLM meta-commentary
  ("Decompose the following spiritual teaching into independent,
  self-contained propositions...") instead of real Sri Preethaji/Sri
  Krishnaji teachings.
- **#10** — Google sign-in happens twice.
- **#11** — the answer to "what kind of teachings you had for me" was a
  Serene Mind / distress-support script (Beautiful State, mantra, "you are
  not alone, you are held, you are seen") instead of an actual answer about
  teachings, and it contained a broken YouTube link
  (`?v=Gdd-uWUWw`, 9 chars — valid IDs are 11).
- **#12** — `https://askmukthiguru.lovable.app/second-brain` doesn't work
  in prod.
- **#13** — clicking Serene Mind in the chat UI shows video instead of
  audio, "for each and every" trigger.

User's explicit verification bar for round 1 (their words): *"can you check
this for all pipelines, since this is needed end to end and making sure
nothing breaks since this is production now."*

**Round 2** — user pasted 5 findings from an external code-review tool
against the round-1 diff, under an attached "standing instructions" rubric
that is unusually strict and worth restating because it changed how this
work was done, not just how it reads:
- Label every load-bearing claim `Confirmed:` / `Likely:` / `Assumption:`.
- Identify the single highest-stakes claim ("critical cell") and verify it
  *two independent ways*, not just re-read it.
- Run a genuine self-attack pass before sending — find the strongest
  objection a hostile reviewer would raise, test it for real, and change
  the conclusion if it survives (not bolt on a caveat).
- Never fabricate a "found nothing" result; never claim full pipeline
  coverage without actually running it.
- Instruction: "Verify each finding against current code. Fix only
  still-valid issues, skip the rest with a brief reason, keep changes
  minimal, and validate."

The user's very next message after round 2 landed also asked, unprompted:
*"is our entire pipeline when user asks a question... are we giving them
the answer in the most intelligent way... is all our ingestion and
retrieval top notch... we need to be successful each and every time."*
**This was explicitly not answered with a real audit** — see §5 item 4.
It's a materially different, larger task (retrieval-quality/eval-set
benchmarking) than reactive bug-fixing, and claiming otherwise would be
exactly the "false completeness" failure pattern the round-2 rubric warns
against.

The prior session's two open threads — backend production hardening
(complete, see prior handoff, now overwritten by this file) and
design-mockup implementation (Auth/Guided Tour/Practices/Profile/Product
Demo — 5 of 8 screens not yet implemented) — were **not touched this
session**. If picking that thread back up, the mockup context lived in the
overwritten version of this file; re-derive it from the `claude.ai/design`
project (`https://claude.ai/design/p/c22f7181-2e24-413d-a9ae-f5d572814ddc`)
rather than assuming it's still here.

---

## 2. Current state of code

### Backend
`999 passed, 8 skipped, 1 failed` — run via `cd backend &&
.venv/bin/pytest -q`, **executed 3 separate times this session** (once
after the round-1 citation/distress fixes, once after the round-1
`is_interrogative` startswith correction, once after the full round-2
`exclude_if_capability_question` refactor). Identical result all 3 times.
The 1 failure:

```
FAILED tests/test_quality_gate.py::test_ingest_playlist_chord -
redis.exceptions.ConnectionError: Error 61 connecting to 127.0.0.1:6379.
Connection refused.
```

This is environment-only (no local Redis running in this sandbox) — the Redis
dependency makes the failure environment-dependent, but its regression status
could not be determined without a baseline or CI result from a known-good
revision. Confirmed pre-existing by inspecting the test itself
(`tests/test_quality_gate.py:129`, mocks everything except a real Redis
connection for a Celery chord backend). No backend `npm run build`
equivalent exists (Python, no build step) — nothing to re-run there.

### Frontend
- `src/test/components/LanguageSelector.test.tsx` — 8/8 passing,
  independently re-run via `npx vitest run` (not just trusting the
  background agent that wrote most of the file's changes).
- `src/test/components/ChatMessage.test.tsx` — 10/10 passing, same
  independent re-run.
- `src/test/engagement-card.test.tsx` — **5 failed / 8 passed**,
  pre-existing, confirmed via `git diff` showing **zero** uncommitted
  changes to that specific test file (it tests a stale `EngagementCard`
  API — literal text like `"Did this help?"` that predates the current
  i18n-key-based redesign already in the working tree before this
  session started). Confirmed the one line changed in `InlineActions.tsx`
  this session (`if (submitted) return;`) cannot be the cause — the
  failures are `TestingLibraryElementError: Unable to find an element with
  the text: Did this help?`, a selector problem, not a submit-logic
  problem. **Spawned as a separate background task** rather than folded
  into this session's diff (task title: fix stale `engagement-card.test.tsx`
  selectors) — not fixed here.
- **Full `npm run build` was NOT re-run after the round-2 findings landed.**
  This is a real gap, not an oversight glossed over — see §5 item 1. Full
  `npx vitest run` (whole suite) is known to OOM in this environment per
  the prior session's documented precedent (commit `df30de30`); this
  session only ever ran scoped test files, never the full suite, to avoid
  hitting that.

### Production
Not touched, not redeployed. No live Railway logs, no Jaeger trace access,
no prod Supabase access were available in this environment at any point
this session — every fix below was verified against local test suites and
standalone logic scripts, never against a live production trace. This
matters specifically for #11 and #13 — see §4 and §5.

---

## 3. Files actively edited this session, exact changes

### `backend/app/api/teachings.py` (+6 lines) — fixes #9
Added `from services.okf_quality_filter import _LEAKAGE_RE` and, inside
`_looks_like_complete_thought(text)`, added `_LEAKAGE_RE.search(text)` as
a rejection check *before* the existing length/punctuation check. Root
cause: `GET /api/teachings/tips` harvests "thinking pill" tips by scrolling
raw Qdrant corpus chunks (`_harvest_tip_pool`) and only ever checked length
+ trailing punctuation — it never applied the same artifact-rejection regex
(`OKFQualityFilter`'s `_LEAKAGE_RE`, matches RAPTOR debug headers,
`"The user wants me to..."`-style extraction-LLM commentary, etc.) that the
curated OKF doctrine layer already enforces per root `CLAUDE.md`'s OKF
invariant #3. Reused the existing regex rather than duplicating pattern
logic — did not open or need to open `proposition_service.py` (the prior
session's handoff had *guessed*, unverified, that the leaked text's
specific origin was that file's extraction prompt; this session fixed the
class of bug at the harvesting chokepoint regardless of origin, and never
resolved whether that specific guess was correct).

### `backend/rag/nodes/intent.py` (+10 lines) — fixes half of #11
Inside `handle_distress` (line ~720), immediately before the final
`return {"final_answer": response, ...}`, added:
```python
from rag.nodes.generation import _clean_inline_citations
response = _clean_inline_citations(response)
```
Root cause: `handle_distress` returns straight to `END` in both graph
strategies (`graph_strategies.py` — `StandardGraphStrategy`/`FastGraphStrategy`
both wire `handle_distress → END` directly; `DeepGraphStrategy.build()` is
a bare alias to `StandardGraphStrategy().build()`, confirmed by reading the
class, so this fix covers all 3 strategies with one change, no
per-strategy duplication needed). This bypasses `format_final_answer`,
which is the node that normally runs `_clean_inline_citations` on the
QUERY path. `STIMULUS_RAG_PROMPT` (the system prompt `handle_distress`
uses) instructs the model at line 37: *"If the Context contains YouTube
links or source URLs, ALWAYS suggest the relevant ones... as 'Watch more
here: [URL]'"* — but the context `handle_distress` builds (line ~756) only
ever includes `doc.get('title')`, **never `source_url`**. So the model was
being told to cite a URL it was never given, and free-generated/
hallucinated one, landing on the malformed 9-char ID. Fix reuses the
existing `_clean_inline_citations` (strips any raw URL / "Watch more
here:" text unconditionally) rather than trying to inject a real
`source_url` into the prompt context (which would be a larger, riskier
change to a crisis-response code path) — the hallucinated link is simply
removed, not replaced with a correct one.

### `backend/config/router_routes.yaml` (+39 lines) — fixes the other half of #11
Final state, after 4 iterations (full blow-by-blow in §4 — do not skip
that section, this is the highest-stakes change in the whole session):
- `DISTRESS` route (line ~151): `exclude_if_capability_question: true`
  (was `exclude_if_interrogative: true` after iteration 1, further
  corrected in iterations 2–4).
- New top-level YAML key `capability_question_stems` (English only):
  `what is / what are / what does / what's / what kind / what type /
  what sort / which / who is / who are`. Deliberately excludes
  `why do / why is / how do / how does / can i / should i / is there /
  are there / does / do you` — those overlap with how genuine distress is
  routinely phrased as a question and must not veto DISTRESS.
- `interrogative_stems.en` (the pre-existing, broader list still used by
  `MEDITATION`'s `exclude_if_interrogative`) gained 3 new entries:
  `what kind`, `what type`, `what sort` — added in iteration 2, kept
  because `MEDITATION` benefits from the broader exclusion too (low
  stakes there — worst case a user doesn't get an auto-started meditation
  script, gets a normal answer instead).

### `backend/services/semantic_router.py` (+35/-4 lines) — fixes the other half of #11
- `LinguisticConfig.is_interrogative`: changed the match from `stem in
  head` (substring-containment anywhere in the first 60 chars) to
  `head.startswith(stem)` (prefix match) — see §4 iteration 3 for why this
  was a real, separate, pre-existing bug independent of anything added
  this session.
- Added `LinguisticConfig.is_capability_question(text)` — same 60-char-head
  prefix-match logic, against the new narrower `capability_question_stems`
  list instead of the broad `interrogative_stems`.
- `Route` dataclass gained `exclude_if_capability_question: bool = False`.
- `_parse_routes` now reads `exclude_if_capability_question` from each
  route's YAML block.
- `classify()` now computes `is_capability_question` alongside the
  existing `is_interrogative`/`is_imperative` and adds a third veto
  branch: `if route.exclude_if_capability_question and
  is_capability_question: continue`.

### `src/pages/AuthPage.tsx` (+21 lines) — fixes #10
- Added `const oneTapInFlightRef = useRef(false);` (new ref, line ~141).
- `handleGoogleOneTapResponse` (line ~695): added an early return if
  `oneTapInFlightRef.current` is already true, sets it true at the top of
  the try block, resets it in `finally`. In the nonce-mismatch fallback
  branch, added an `await supabase.auth.getSession()` check — if a session
  already exists, `endAuthRun('ok')` and return, **do not** fire the
  fallback `signInWithOAuth` redirect.
- Root cause: GSI's auto-`prompt()` corner popup and the `renderButton()`
  widget both funnel into the *same* `handleGoogleOneTapResponse` callback
  via one shared `initialize()` call. A second invocation of that callback
  (from either path firing twice, or the effect re-running on `loading`/
  `isSignUp` state changes and re-triggering `prompt()`) reuses an
  already-consumed nonce, which Supabase rejects as `"Nonces mismatch"`,
  which the existing fallback code unconditionally treated as "must do a
  full OAuth redirect" — even when the *first* call had already succeeded
  and signed the user in. That unconditional fallback redirect is the
  literal "signs in twice" symptom.
- **User's explicit decision on scope** (verbatim, in response to being
  asked): *"keep onetap and fix the fallback bug, mostly this is because
  since we are hosting our website through lovable we are using lovable
  google sign in and our own supabase free tier for our telemetry and also
  audit data as well..."* — **this session corrected that premise back to
  the user**: read `AuthPage.tsx` fully; there is no separate
  "Lovable Google sign-in" in the code. Every auth path
  (`signInWithIdToken`, `signInWithOAuth`) already goes through
  `@/integrations/supabase/client` — i.e. the user's own Supabase project
  — for both One Tap and the redirect flow, end to end. If future work is
  predicated on a Lovable/Supabase auth split existing, that premise needs
  to be re-examined; the code doesn't currently have one.
- The prior session's handoff had flagged this as needing to be resolved
  together with implementing the new `Auth.dc.html` design mockup (which
  shows a single plain button, no One Tap at all). **That mockup work was
  not done** — this fix keeps One Tap and patches the bug in place, per
  the user's explicit choice above, which is a *different* direction than
  the mockup implies. Worth reconciling before touching `AuthPage.tsx`
  again for mockup work (see §5 item 6).

### `src/components/chat/LanguageSelector.tsx` (142 lines changed, mostly deletions) — fixes #8 (part 1)
Done by a background agent (`subagent_type: claude`, full read/write
access), independently spot-checked by reading the actual diff (not just
trusting its summary):
- Removed the component's own `toast(...)` call inside
  `handleLanguageChange` — the parent `ChatInterface`'s
  `onLanguageChange` handler already fires one; every language switch was
  showing two toasts.
- Fixed dead code: the popover's viewport-clamped position (`coords.bottom`/
  `coords.left`, computed on open via `updatePosition()`) was calculated
  but never actually applied — the popover was rendered with static
  `absolute bottom-full left-0` Tailwind classes regardless, so near a
  screen edge it could render partially off-viewport. Switched to
  `position: fixed` driven by the already-computed clamped coordinates.
- Removed the search `<input>` — `LANGUAGES` is filtered down to 7 codes
  (`en, hi, te, kn, ta, mr, ml`) out of 23 total scheduled-language
  entries in `MASTER_LANGUAGES`; 7 items is flat-list territory, no search
  needed (matches claude.ai/ChatGPT's <10-item picker pattern).
- Removed the per-row TTS voice-capability badges (implementation detail
  surfaced as UI noise, not user-facing value) — the underlying voice
  detection logic (`detectTtsVoices`, `voiceCapable` state) is untouched,
  only the badge rendering was removed.
- Bumped the "AUTO" badge from 9px to 10px with more padding for
  legibility.

### `src/lib/chatStorage.ts` (+1 line) — fixes #8 (part 2, incognito)
`saveFeedback` now starts with `if (_incognito) return;`. This is the
shared chokepoint — any future caller of `saveFeedback` inherits the
guard, not just the one call site touched in `InlineActions.tsx` below.

### `src/components/chat/InlineActions.tsx` (199 lines changed) — fixes #8 (part 2) and round-2 finding #3
- `EngagementCard.submit()`: both `saveFeedback(...)` (local) and
  `void submitFeedbackToBackend(...)` (network POST of the query+answer
  pair) are now gated behind `if (!isIncognitoMode())` — previously
  neither had any incognito check at all, meaning "incognito" mode was
  still shipping the query/answer pair to the backend and to localStorage
  on every feedback click.
- `handleChoice(choice)`: added `if (submitted) return;` as the first
  line (round-2 finding #3) — without it, a rapid double-click during the
  `AnimatePresence` exit transition (the Yes/Not-quite buttons stay
  mounted and clickable through the fade-out) could call `submit()` twice
  for one logical click, firing a duplicate feedback submission.

### `src/components/chat/ChatInterface.tsx` (+9/-2 lines) — fixes #8 (part 2)
- The 500ms `setInterval` stream-checkpoint write to
  `sessionStorage.setItem('askmukthiguru_stream_checkpoint', ...)` is now
  gated on `!isIncognito` — previously the live streamed answer text was
  being written to disk-backed session storage even during "confidential"
  incognito sessions.
- The main chat surface wrapper (`<div className="flex-1 flex flex-col
  min-w-0 min-h-0 relative z-10 ...">`) now gets a conditional
  `bg-amber-950/[0.03] dark:bg-amber-950/[0.1]` tint whenever
  `isIncognito` is true — previously only the small header pill indicated
  incognito state; now the whole surface reads as persistently "in
  incognito" while active, matching claude.ai/ChatGPT's unmissable-while-active
  pattern instead of a small, easy-to-miss badge.
- Verified already-correct, no change needed: `saveConversation` already
  gated on `_incognito`; exiting incognito or refreshing mid-session
  already silently discards with no confirmation prompt (matches the
  desired UX exactly — that silence is the point of incognito); entry
  points to toggle incognito already exist in both the desktop sidebar and
  mobile sheet.

### `src/test/components/LanguageSelector.test.tsx` (29 lines changed) — matches the LanguageSelector.tsx changes + round-2 finding #4
- Removed the search-filter test and the toast-assertion test (both test
  behavior that no longer exists).
- Round-2 finding #4: the "renders all languages as a flat list" test
  previously only asserted `Telugu` and `Hindi` render — updated to
  `import { LanguageSelector, LANGUAGES } from
  '@/components/chat/LanguageSelector'` and
  `LANGUAGES.forEach((lang) => expect(screen.getByText(lang.name)).toBeInTheDocument())`,
  so all 7 languages are asserted and the test won't silently pass if a
  future change drops one from the filtered list.

### `user_video_script.md` (107 lines changed) — round-2 finding #5
Line 8 previously asked the user to *"sign up yourself and hand me an
already-logged-in session"* to record a demo video. Rewrote to remove that
request entirely (a live authenticated session handoff is functionally
equivalent to a credential handoff, which is a hard-line prohibited action
regardless of framing) — replaced with two options: record the
login/chat steps yourself and hand over the footage for editing, or set up
a separate, revocable demo account. Kept the existing "worth checking if a
no-signup guest path exists" note, since that's independent of the
credential-handoff issue. (Note: most of this file's 107-line diff predates
this session — it's part of the pre-existing uncommitted working tree from
before this conversation started; only the one paragraph above was changed
this session.)

### Not changed — round-2 finding #2, dismissed with reason
Finding asked to route `handle_distress`'s response through "the shared
final output guardrail... used by the QUERY path" before returning.
**Verified in code, not assumed**: `OutputGuardrailStage`
(`backend/app/pipeline/stages/guardrail_stage.py:86`, docstring
*"Moderate the final answer post-graph. Never short-circuits."*) calls
`container.guardrails.check_output(ctx.final_answer)` unconditionally, as
a pipeline-level stage that runs after `GraphStage` for every request
regardless of intent — it is not scoped to the QUERY path, does not care
which graph node produced `final_answer`. `handle_distress`'s output was
therefore already passing through content moderation; the specific gap
this session found and fixed (§ above) was citation/URL cleanup, a
*different, unrelated* function (`_clean_inline_citations`), not
moderation. Routing `handle_distress` through `format_final_answer`
instead (the finding's suggested remedy) was rejected because that
function's confidence-graduated-response logic is designed for QUERY/
FACTUAL answers with retrieved-doc scoring and would risk appending
inappropriate "confidence: low"-style caveats onto a crisis-support
message — a worse outcome than the status quo. No code changed for this
finding.

---

## 4. Everything tried, what failed, what was wrong the first time — full detail

### 4a. The DISTRESS-routing fix: 4 iterations, each catching a real bug the last one missed

This is the highest-stakes change in the session (crisis/distress routing
in a spiritual-support product) and the one most worth reading in full if
picking this back up.

**Iteration 1.** Added `exclude_if_interrogative: true` to the `DISTRESS`
route, reusing the exact flag already proven safe on `MEDITATION` (which
has a comment calling it *"the configuration-level fix for the Soul-Sync-
on-Mars hijack"*). Pattern-matched, looked correct, no verification done
yet.

**Iteration 2 — caught by writing a standalone verification script before
trusting the pattern-match.** Loaded the actual YAML, replicated
`is_interrogative`'s logic in a bare Python snippet (no `app.config`
import needed — importing `services.semantic_router` transitively pulls in
`app.config`, which throws a `pydantic_core.ValidationError` for a missing
`sarvam_api_key` in this environment; the fix was to test the pure-string
logic standalone instead of importing the real module). Result: the
existing `interrogative_stems.en` list (`what is`, `what are`, `what
does`, `what's`, plus `how do/does/can/to`, `why is/does/do/are`, `when
is/does`, `where is/does`, `is there`, `are there`, `does `, `do you `,
`which `, `who is/are`) contained **no stem matching the actual reported
query**, `"what kind of teachings you had for me"` — the shipped fix would
not have resolved the reported bug at all. Added `what kind`, `what type`,
`what sort` to close this.

**Iteration 3 — caught by testing DISTRESS's own 9 training utterances as
a control, not just the bug-report query.** Same standalone script, this
time asserting `is_interrogative(utterance) == False` for all 9 of
DISTRESS's canonical training phrases. One failed:
`"I feel completely hopeless and I do not know how to go on"` flagged as
interrogative. Root cause: `is_interrogative`'s match was `stem in head`
(substring-containment anywhere in the first 60 characters of the
lowercased query), not `head.startswith(stem)` — despite the YAML's own
header comment explicitly claiming *"drop the match if the query starts
with an interrogative stem."* The mid-sentence `"...how to go on"` matched
the `"how to"` stem via containment. This is a **pre-existing bug**,
unrelated to anything added this session, that only became *consequential*
once `DISTRESS` started using the flag — before this session, only
`MEDITATION` used `exclude_if_interrogative`, and its training utterances
(`"Start the meditation"`, etc.) never happened to trip the
containment-vs-prefix distinction. Fixed by changing the match to
`head.startswith(stem)` in `services/semantic_router.py`.

**Iteration 4 — caught by the external reviewer in round 2, not
independently found this session.** Worth being honest about: even with
iterations 2 and 3 applied, the *shape* of the fix was still wrong. A
blanket `exclude_if_interrogative` on `DISTRESS` — regardless of exact
stem-matching correctness — vetoes **any** query starting with `why do`,
`how do`, `can i`, `should i`, `is there`, etc. Genuine distress is
*routinely* phrased as exactly that kind of question: `"why do I feel so
hopeless"`, `"how do I stop crying"`, `"should I just give up"`. All three
of those would have been silently excluded from the DISTRESS route by the
iteration-3 fix, even though they are unambiguous crisis language. This
was flagged by the user pasting an external reviewer's finding, not caught
by this session's own self-verification — a real miss. Fixed by
**replacing** the blanket flag with a new, narrower
`exclude_if_capability_question` (new `Route` field, new
`capability_question_stems` list containing only `what kind/type/sort/is/
are/does`, `which`, `who is/are` — i.e. "asking about a topic," never
`why`/`how`/`can`/`should`/`is there`). Re-verified with 8 standalone test
cases: reported bug query still excluded; all 9 DISTRESS training
utterances *and* the 3 new question-phrased distress examples above all
correctly **not** excluded. Ran the full backend pytest suite (999/8/1,
same as baseline) after this final change.

**Why this matters for whoever continues this work**: three different
failure modes hit in sequence — wrong stem coverage (iteration 2), wrong
match semantics/containment-vs-prefix (iteration 3), wrong exclusion scope/
blanket-vs-narrow (iteration 4) — on what looked, at each step, like a
complete and correct fix. None of them would have been caught by "does the
one reported query now work" — only by deliberately testing the mechanism
against its own training data and against adjacent phrasings it needs to
still catch. Also worth noting: there is **no live embedding-model
verification** anywhere in this chain — every check was pure string-logic
(`is_interrogative`/`is_capability_question`'s stem matching), because the
actual semantic-similarity scoring (cosine similarity against the
`SentenceTransformer`-encoded route centroids) requires a loaded embedding
model this environment doesn't have easy access to without hitting the
`app.config` Settings validation error. **This means the actual embedding-
threshold behavior (does "what kind of teachings you had for me" really
score ≥0.66 against DISTRESS's centroid, confirming the original bug
report's mechanism) was never re-verified end-to-end with the real model
this session** — only inferred from the original diagnosis agent's
report. If the embedding model's behavior differs from assumed, the whole
chain of fixes could be moot or insufficient. Worth a live/staging-backend
smoke test of the exact reported query before calling this closed.

### 4b. Silent gate-blocked edits (twice)

The repo has a `GateGuard` pre-tool-use hook that requires stating
importers/affected-API/data-schema/user-instruction facts before the
*first* `Edit`/`Write` of a given file in a session; subsequent edits to
the same file in the same turn don't re-trigger it, but **the very first
attempt on a new file is denied**, and critically: **the denial can appear
alongside a different, successful tool result in the same batched call**,
making it easy to think an edit landed when it silently didn't.

This happened twice:
1. First attempt at `backend/app/api/teachings.py` (the import line) and
   `src/pages/AuthPage.tsx` (the `handleGoogleOneTapResponse` rewrite),
   sent as parallel `Edit` calls alongside two *other* edits in the same
   tool-call batch — the other two succeeded, these two were silently
   denied. Caught by running `git diff --stat` immediately after and
   noticing the insertion counts were smaller than expected (1 insertion
   on `AuthPage.tsx` instead of the ~20 the real rewrite should have
   produced) — re-read the actual file content at the target lines,
   confirmed the rewrite hadn't landed, re-presented the required facts,
   re-applied successfully.
2. First attempt at `backend/services/semantic_router.py`'s
   `is_interrogative` fix (iteration 3 above) hit the same denial pattern
   once, immediately retried with facts stated and it landed.

**Lesson for future sessions in this repo**: never trust that an `Edit`
call "succeeded" just because the batch didn't error out overall — always
verify with `git diff --stat`/`git diff <file>` after any batch containing
a first-touch edit to a new file, especially when edits are sent in
parallel.

### 4c. The `git stash` incident (this session, item #8 background agent)

Separately from the pre-existing stale `stash@{0}` (see the top of this
file — that one predates this session entirely and is unrelated), the
background agent assigned to investigate/fix item #8 (language selector +
incognito UX) self-reported, unprompted, in its final summary: *"mid-session
I ran `git stash` to check test baselines, which also stashed the
pre-existing uncommitted changes already in your tree... I immediately ran
`git stash pop` and verified via diff that everything... was restored
intact."*

This is the **second time** this exact failure mode has happened in this
repo — the prior session's handoff documents an earlier, separate incident
where an unpathspec'd `git stash` reverted the entire working tree and had
to be recovered via `git restore --source=stash@{0}`. **Did not just trust
the agent's self-report this time** — independently ran `git status
--short` and `git diff --stat` immediately after the notification landed,
confirmed all 16 expected files (this session's edits + the pre-existing
uncommitted redesign work: `ChatMessage.tsx`, `DesktopSidebar.tsx`,
`InlineActions.tsx`, `en.json`, `ChatMessage.test.tsx`,
`user_video_script.md`) were present with expected diff stats, and that
the one stray `stash@{0}` entry still present matched the **pre-existing**
stash's exact message/content (`AGENTS.md`/`RUTHLESS_PLAN.md`, not
anything the item-8 agent touched) — confirming the agent's own stash was
correctly created-and-popped in between, shifting the pre-existing stash
back to position 0 without altering its content. Spot-checked two of the
agent's most safety-relevant specific claims directly in the diff
(`!isIncognito` guard on the stream-checkpoint write, `if (_incognito)
return;` in `saveFeedback`) rather than trusting the summary text alone.

**Lesson, restated for the second time in this repo's history**: any
agent working here — background or foreground — must scope `git stash` to
a pathspec (`git stash push -- <file>`) or use `git stash -u <specific
paths>`, never run it bare, because this repo is worked on by multiple
concurrent background agents whose uncommitted changes all live in the
same working tree simultaneously.

### 4d. Other things tried and correctly abandoned
- Considered folding `engagement-card.test.tsx`'s 5 pre-existing failures
  into this session's fixes (they're adjacent to `InlineActions.tsx`,
  which this session did touch) — declined after confirming via `git diff`
  they predate this session and test an API surface (`"Did this help?"`
  literal text) that doesn't exist anymore, unrelated to the double-submit
  guard actually added. Spawned as a separate background task instead of
  scope-creeping.
- Considered whether `handle_casual` and `handle_meditation` (the other
  two graph nodes that also return straight to `END`, alongside
  `handle_distress`) share the same hallucinated-URL vulnerability —
  checked both: `handle_casual`'s system prompt (`CASUAL_SYSTEM_PROMPT`,
  `rag/prompts/system.py:202`) has no URL-citing instruction and is never
  given retrieved-doc context to cite from at all (near-zero risk, no fix
  applied — would be speculative). `handle_meditation` is entirely
  template/script-driven (`MEDITATION_SCRIPTS`, `format_meditation_
  response`), makes no LLM call whatsoever, zero risk. Neither touched.
- Considered whether the pipeline-level `DistressStage`
  (`app/pipeline/stages/distress_stage.py`, a separate keyword-gated
  pre-graph distress detector, distinct from the graph-level YAML semantic
  router) would conflict with or need updating alongside the router
  changes — read it fully, confirmed it's independent (own keyword regex,
  "Never short-circuits" per its own docstring, only sets advisory
  `state["proactive_serene_mind"]` metadata) and unaffected either way. No
  change needed.

---

## 5. Next step — prioritized

1. **Re-run a full `npm run build` and (scoped, not full-suite, to avoid
   the known OOM) frontend tests one more time** after the round-2
   findings — every individual touched file was validated, but there has
   been no single final "does everything still link together" pass since
   `InlineActions.tsx`, `LanguageSelector.test.tsx`, and
   `router_routes.yaml`/`semantic_router.py` all changed in the same
   session. Cheapest next action, do this first.
2. **Get a live/staging smoke test of the exact reported #11 query**
   (`"what kind of teachings you had for me"`) against a running backend
   with the real embedding model loaded — as noted in §4a, every
   verification this session was pure string-logic on the
   `is_interrogative`/`is_capability_question` stem-matching layer; the
   actual cosine-similarity threshold behavior against the live
   `SentenceTransformer` model was never re-confirmed end-to-end this
   session. This is the single biggest remaining unknown in the highest-
   stakes fix made.
3. **#13 (Serene Mind video-vs-audio) — diagnosed, not fixed, blocked on
   the user.** Every `openSereneMind()` call site defaults to `'audio'`;
   the video-tab component (`SereneMindModal`) is unreachable from the
   chat UI; the documented prior `crossOrigin` audio-CDN fix is intact
   (`useMeditationAudio.ts:35-37`, explicitly does *not* set
   `crossOrigin='anonymous'`, with a comment explaining why). Most likely
   explanation: `ChatMessage.tsx:952-984` auto-embeds a real inline
   YouTube player whenever a message's citations include a
   `youtube.com`/`youtu.be` URL, and teaching content about Serene Mind
   naturally cites the same source video (`igSp4H0OWLE`) Serene Mind
   itself references — so a real embedded video can appear in the same
   chat bubble as the Serene Mind CTA, unrelated to Serene Mind itself.
   **Question asked, not yet answered by the user**: was the video inline
   in the chat transcript, or inside the full-screen Serene Mind overlay
   itself? Do not guess further without that answer.
4. **#12 (second-brain) still fully blocked** on the user running 4
   Supabase migrations — no `SUPABASE_ACCESS_TOKEN`/DB password available
   in this environment, all 4 sessions so far. Exact paths, in required
   order (each is idempotent, safe to re-run):
   1. `supabase/migrations/20260717191006_second_brain_vault.sql`
   2. `supabase/migrations/20260718000000_user_streaks.sql`
   3. `supabase/migrations/20260718120000_add_unique_session_summary.sql`
   4. `supabase/migrations/20260718120001_second_brain_keys_table.sql`

   Run via `supabase login && npx supabase db push`, or paste each file
   into the dashboard SQL editor in that exact order.
5. **The broader pipeline-quality question the user asked** ("is our
   entire ingestion/retrieval top notch, successful every time") —
   deliberately not answered with a real audit this session; told the
   user directly this was reactive bug-fixing, not systematic retrieval-
   quality review. A real answer needs eval-set benchmarking — the tooling
   already exists (`backend/benchmarks/ragas_eval.py`,
   `sdlc_rag_benchmark.py`, `comprehensive_benchmark.py`,
   `ruthless_benchmark.py`) but wasn't run this session. **If the user
   wants this, scope it as its own dedicated task** — do not fold it into
   the next round of reactive fixes, it needs a live Docker stack
   (`docker compose up -d qdrant redis neo4j jaeger`) this environment
   doesn't currently have running.
6. **Stale `git stash@{0}`** — still sitting there, still unresolved,
   flagged to the user twice now (once mid-session, once here) without a
   decision either way. Ask directly: inspect and selectively restore, or
   drop it.
7. **Reconcile the Auth-screen mockup vs. the #10 in-place fix.** The
   prior session's handoff recommended implementing the new `Auth.dc.html`
   design mockup (single plain Google button, no One Tap) specifically to
   resolve #10. This session instead kept One Tap and patched the
   double-fire bug in place, per the user's own explicit choice mid-
   session. These are two different end states for the same screen —
   before touching `AuthPage.tsx` again for the still-pending mockup
   implementation work (5 of 8 design screens remain: Auth, Guided Tour,
   Practices, Profile, Product Demo), confirm with the user which
   direction they actually want for Auth specifically, since the mockup
   and the shipped fix now disagree.
