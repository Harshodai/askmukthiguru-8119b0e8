# Engineering readiness audit — independent review of the 2026-11-13 uncommitted change set

**Document ID:** `ENGINEERING-READINESS-AUDIT-2026-11-13`
**Reviewer:** independent review pass (no authorship of the change set under review)
**Repository:** `askmukthiguru`, branch `main`, head `3a4d479f`
**Review window:** 2026-11-13
**Environment:** local Docker stack (18 containers up), local Supabase, `first_person_v10` / `first_person` alias (4,224 points)
**Deliverable:** engineering readiness of the change set + of the running product for a faculty demonstration and a Railway staging release

---

## 0. Release decision

| Scope | Decision | Reason |
|---|---|---|
| Merge the change set | **GO** | Every change is verified by a targeted test and none regresses an existing suite; two defects were found and fixed during this review. |
| Faculty demonstration on the current stack | **NO-GO** | The LLM provider account is out of spend: every first-person turn abstains at `relevance_indeterminate` (8 of 8 scorer calls refused). Retrieval and gates work; the question-scoring gate cannot run. |
| Railway staging release | **NO-GO (unchanged)** | Owner directive: Railway stays stopped until Harsha says go. Prerequisites from `docs/plans/RAILWAY_READINESS_PLAN_2026-11-12.md` are still open. |
| Production | **NO-GO (unchanged)** | Unchanged from the standing verdict: human gates (clinician, native speakers, rights sign-off, helplines, gold labels) are open. |

The change set itself is not the blocker. The blocker is an account quota plus the pre-existing Railway/human gates.

---

## 1. What was reviewed

Twelve modified files and eight untracked files, all uncommitted on `3a4d479f`.

A second, unrelated set of documentation edits by another live session (`AGENTS.md` +2, `CLAUDE.md` +1, `docs/DEVELOPER_GUIDE.md` +10, `.claude/tasks/sota_architecture_implementation_plan.md` +35 — all recording the telemetry-write guard) was present in the tree during this review. It was left untouched and is not part of the change set reviewed below. **Two sessions share one Docker container; that remains Railway blocker 1.**

| File | Change | Independent verdict |
|---|---|---|
| `backend/app/config.py` | removed a duplicate `first_person_corpus_version` declaration; `intent_router_ambiguous_domain_enabled` default `True → False` | **Correct.** Duplicate declaration was real (single field, second won). Default flip matches measured behaviour: the router answered in 470–690 ms against a 0.45 s budget, so it could never fire; routing is identical without the wait. Pinned by `test_settings_declares_every_field_once` and `test_ambiguous_domain_router_is_off_by_default`. |
| `backend/app/runtime_budget.py` | new `serving_gate_warnings()`, emitted at startup | **Correct and useful.** Verified live: the running container logs the warning once at boot (`Serving gate posture: FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false …`). It reports, it does not change policy — the right call for an owner-set flag. |
| `backend/app/api/search_routes.py` | `GET /api/search/inspect-source`: 30/min limit, blocked-video 404, rights 403, per-chunk quarantine filter | **Correct in intent, and the gate works live** (licensed video → 200; unlicensed → 403 with no transcript text). **One defect found in the reviewed code's blast radius** (see F-1): the endpoint's Qdrant path is dead in the live container, so the content a user sees comes from the local-transcript fallback. Fixed in this review. |
| `backend/app/pipeline/stages/first_person_bridge.py` | history-resolved follow-up bypasses the exact cache; comment correction | **Correct.** The exact-cache key hashes the bare question, so two different conversations asking "why does that happen?" could share an entry. Bypass covers read and write, and does not widen the key (which would have stopped non-English questions from caching). |
| `backend/services/first_person_pipeline.py` | `neutralise()` on the answerability prompt; `corpus_version` derived from citations; `error` on a terminal retrieval outage; `_passes_integrity_gate` moved off the event loop | **Mixed.** Neutralisation, `corpus_version` and the executor move are correct. `error` is set but has **no consumer** (see F-2). |
| `backend/rag/nodes/on_device_intent.py` | log user text replaced by `len` + truncated sha256 | **Correct and necessary.** Three INFO lines were logging raw seeker text. Test asserts the text never reaches the record. |
| `backend/scripts/ops/validate_production_env.py` + `scripts/ops/validate_production_env.py` | preflight mirrors `Settings.validate_production_restrictions` (BRAIN_KEK, FACULTY_ACCESS_CODE/`FACULTY_GATE_DISABLED`, OpenRouter budget guard) | **Correct.** The three rules match `app/config.py:2519-2550` line for line. Both tree copies are byte-identical (`diff -q` clean), as X1 requires. One nuance: the mirror treats an empty value as "unset" while pydantic would raise on `""` for a bool — harmless in practice, worth knowing. |
| `backend/tests/test_production_env_preflight.py` | fixture gains `BRAIN_KEK`, `FACULTY_ACCESS_CODE` | **Correct** — without them the "valid environment" fixture could not boot the app it claims to validate. |
| `docs/REINGESTION_RUNBOOK_2026-11-12.md` | re-measured corpus shape | Provenance only; not re-derived here. |
| `lessons.md` | five lessons + a report pointer | Content is accurate **except** that it points at a report and an open-work row (`T-E1`) that did not exist. Both are created by this review. |
| `src/lib/chatStorage.ts` | citation-ledger flags never upgraded from absent; 32-bit string hash → sha256; `{ error }` read from the insert | **Correct.** Both original defaults were provenance violations (`rightsCleared ? … : 'licensed'`, `speakerVerified ?? true`). The `try/catch` around a supabase-js call caught nothing. |
| `supabase/migrations/20261113000000_message_citations_owner_scoped_read.sql` | replaces `USING (true)` read policy with owner-scoped read + insert | **Correct, and independently proven** (see §3.6). |
| `evals/first_person/conversation_cases_draft.jsonl` + schema test | 24 AI-authored draft conversation cases | Correctly labelled `draft_needs_owner_review`. **No runner consumes them** (F-4). |
| `backend/tests/test_{lead,security,fp}_audit_fixes_2026_11_13.py`, `test_validate_production_env_parity_2026_11_13.py` | 44 new tests | All pass. One test double diverges from the live container shape (F-1). |
| `src/test/citationLedgerFlags.test.ts` | 3 tests | Pass. |

---

## 2. Findings

Severity: P0 = security/data-integrity/failure; P1 = core product or release blocker; P2 = significant quality/reliability; P3 = maintainability.

| ID | Sev | Finding | Evidence | State |
|---|---|---|---|---|
| F-1 | P2 | `GET /api/search/inspect-source` never reached Qdrant in the live container: `container.qdrant.get_client()` and `container.qdrant.collection_name` do not exist on `QdrantService`. Every request raised `AttributeError` inside the try-block, logged a WARNING, and silently served the local-transcript fallback. The endpoint's own new test could not see it because its stand-in container has `get_client`. | live backend log: `Failed to scroll Qdrant for source … 'QdrantService' object has no attribute 'get_client'`; `services/qdrant_service.py` facade has `_client`/`_collection` only | **FIXED and LIVE** (`get_client()` + `collection_name` accessors, `tests/test_inspect_source_qdrant_facade.py`; rebuilt and verified 2026-11-14 — see §8.1). |
| F-2 | P2 | A context-store retrieval outage in terminal mode is recorded in `result.error` but the seeker is still told "I don't have a verified verbatim teaching…". `abstain_cause()` reads only `status`/`reason`, and `abstain_reason` is `no_verified_clips`. The stated intent of the change (an outage is not an empty corpus) is not delivered end to end. | `services/first_person_pipeline.py:5314`, `app/answer_contract.py:24-45`, `app/pipeline/stages/first_person_bridge.py:1644-1652` | **OPEN** — documented as `T-E5`. Not changed here: the same change set pins `status == "abstained"` in its own test, so flipping the status is the author's/owner's call, not a reviewer's. |
| F-3 | **P1** | The LLM provider account is out of budget: `OpenRouter daily or monthly spend limit reached`. The relevance scorer therefore returns indeterminate on every candidate and every first-person turn abstains with `first_person_check_unavailable` / `abstain_cause=system_unavailable`. | live chat probe (`/api/chat?wait=true`, anger question → 200, `grounding_state=abstained`, 0 citations); backend log ×8 in one turn; `docker exec … settings.llm_provider=openrouter` | **CORRECTED 2026-11-14 — see §8.1.** It was the app's own monthly cap (100) against a 123.13 counter, not the provider balance. |
| F-4 | P3 | `conversation_cases_draft.jsonl` is validated for shape only; nothing runs it, so it changes no measurement. | only reference is its schema test | **OPEN** — `T-E7`. |
| F-5 | P3 | The new inspect-source 403 is invisible to the user: `LinkSearchModal` only reads `res.ok`, so a rights refusal renders as "Discourse Transcript (0 chunks)" with no explanation. | `src/components/chat/LinkSearchModal.tsx:90-100,149,243` | **CLOSED before this review ended** — the error map already exists at `LinkSearchModal.tsx:50-54`; see §8.1. |
| F-6 | P3 | Local Supabase has neither `message_citations` nor `video_serving_decisions`: migrations `20261107000000`/`20261107000001` are unapplied, so the citation ledger is dead locally and the new policy migration has nothing to attach to. | `select to_regclass(...)` → `message_citations` NULL; `supabase_migrations.schema_migrations` newest `20261030140000` | **CLOSED 2026-11-14** — migrations applied, RLS re-proven, snapshot regenerated; see §8.2. |
| F-7 | P3 | Redis rate limiter fails open on `Connection closed by server` (2 events in a 10-minute window). Bounded, but it is the same class as Railway blocker 4 (unexplained Redis timeouts). | backend log | **OPEN** — measure under load, `T-E8`. |

No P0 was found. No security regression was introduced by the change set.

---

## 3. Verification evidence

All commands were run on this tree, in this session. Nothing below is inferred from a document.

### 3.1 Backend tests

| Suite | Result |
|---|---|
| The 44 new tests (`test_{lead,security,fp}_audit_fixes_2026_11_13.py`, `test_validate_production_env_parity_2026_11_13.py`, `test_conversation_cases_draft_schema.py`, `test_production_env_preflight.py`) | **44 passed** in 0.88 s |
| Related regression slices (`test_first_person_bridge`, `test_first_person_pipeline`, `test_config_validation`, `test_runtime_budget`, `test_intent_router`, `test_on_device_intent_encoder_missing`) | **269 passed** in 9.95 s |
| Telemetry/ingestion slice (`test_gate_rejection_ledger`, `test_telemetry_*`, `test_ingestion_pipeline`, `test_ingestion_security`) | **64 passed** in 8.10 s |
| Repository layout pin (`test_repo_layout.py`) | **5 passed** |
| New facade pin (`test_inspect_source_qdrant_facade.py`) + security audit tests | **6 passed** |
| Full backend suite (`pytest -q`, default `-m 'not slow'`) | **`14141 passed, 22 skipped, 2 deselected, 2 xfailed` in 353.86 s, exit 0** (baseline, before the F-1 fix) |
| Full backend suite, re-run **after** the `qdrant_service.py` edit | **`14143 passed, 22 skipped, 2 deselected, 2 xfailed` in 353.43 s, exit 0** (+2 = the new facade pin tests) |

### 3.2 Frontend

| Gate | Result |
|---|---|
| `tsc -b` | exit 0 |
| `vitest run` (full) | **1,151 passed, 6 skipped**, 182 files (+1 skipped file), 15.8 s |
| `vitest run src/test/citationLedgerFlags.test.ts` | 3 passed |
| `npm run build` | **exit 0**, 29 routes prerendered |
| `eslint` on the two touched TypeScript files | 0 errors |

### 3.3 Lint and repository guards

`ruff check` on all touched Python files: **All checks passed**. `git diff --check`: clean. Guards: `migration_lint` (schema snapshot valid), `guru_literal_guard`, `config_lint` (0 undeclared settings reads), `stale_flags` (0 blocking), `lesson_guards publication|claims|fp-writes` — all exit 0. `scripts/ops/validate_production_env.py` and `backend/scripts/ops/validate_production_env.py` are byte-identical.

### 3.4 Telemetry-write invariant (AGENTS.md ingestion invariant 5)

`public.corpus_gate_rejections` row count read from the live project: **3,135 before** the suite slices, **3,135 after**, and **3,135** again after two consecutive full-suite runs (~12 minutes of pytest). The `PYTEST_CURRENT_TEST` guard in `app/telemetry_db.py::_telemetry_db_allowed` holds; the guard was not weakened.

### 3.5 Live checks (local Docker stack)

| Check | Result |
|---|---|
| `docker ps` | 18 containers up; backend/frontend/worker/redis/qdrant/memgraph healthy; `RestartCount=0` on backend, frontend, worker, qdrant, redis |
| `GET /api/health` | 200 (3.09 s — deep health is slow; see limits) |
| `GET /api/healthz` | 200 |
| `GET /` (frontend) | 200 |
| `POST /api/auth/anon-session` | 200, token issued |
| Crisis probe "I am planning to end my life tonight" | 200 in **16 ms**, `crisis=True`, `status=crisis_redirect`, `grounding_state=safety_redirect`, **2 helplines**, no LLM call |
| Out-of-domain probe "what is the capital of france" | 200 in **0.52 s**, `off_topic_domain_boundary`, 0 citations, honest refusal |
| Bounded comparison "compare meditation and contemplation" | 200 in **0.52 s**, `limited_comparison_fallback`, 0 citations, explicitly labelled general distinction |
| First-person probe "how do i deal with anger towards my brother" | 200 in 2.04 s, **abstained** (`first_person_check_unavailable`), 0 citations — provider quota (F-3). Harness logs show retrieval ran and returned serve decisions before the scorer failed. |
| `GET /api/search/inspect-source` licensed video `-0O6WmxU3pw` | 200, 1 chunk — **served from the file fallback** (F-1), not Qdrant |
| `GET /api/search/inspect-source` unlicensed video `-dzlXEIkqkI` | **403**, body carries no transcript text |
| Backend log levels (current container) | 380 INFO, 9 WARNING, 0 ERROR |

### 3.6 Migration proof (independent)

Applied `20261107000000` and `20261113000000` **inside a transaction that was rolled back** against the local Postgres, with two real `auth.users`/`conversations`/`chat_messages` owners:

| Assertion | Result |
|---|---|
| Owner sees own citation rows | 1 |
| Owner sees the other owner's row | 0 |
| Owner inserts a citation for own message | allowed (1 row) |
| Owner inserts a citation for another owner's message | **denied** — `new row violates row-level security policy` |
| `message_citations` / `corpus_takedowns` persist after the proof | none (`to_regclass` unchanged) |

The pre-existing `USING (true)` read policy did let any signed-in user read everyone's `verbatim_text` and `video_id`; that is a genuine P1-class exposure and this migration closes it.

---

## 4. Verified product capability (current running stack)

| Capability | Status | Evidence |
|---|---|---|
| Crisis detection and helplines | **WORKING** | 16 ms, static, no provider dependency |
| Out-of-scope boundary refusal | **WORKING** | deterministic, 0.52 s, 0 citations |
| Bounded comparison fallback | **WORKING** | deterministic, labelled, 0 citations |
| Retrieval into the first-person harness | **PARTIALLY WORKING** | harness decisions logged (`serve_parent_context`, `serve_single_span`, gates evaluated); gate scoring cannot complete |
| First-person answer serving | **BROKEN (environmental)** | provider spend limit → `relevance_indeterminate` on 100% of turns |
| Source inspection | **PARTIALLY WORKING** | rights gate works; Qdrant path dead in the image (fixed in tree, needs rebuild) |
| Citation ledger persistence | **BROKEN (local)** | table absent locally; migration written, applied nowhere |
| Structured citation flags | **WORKING (client-side)** | tests; still self-attested by the browser |
| Health / readiness endpoints | **WORKING** | 200 |
| Frontend build + unit suite | **WORKING** | 1,151 tests, build exit 0 |

---

## 5. What I changed

| File | Change | Why |
|---|---|---|
| `backend/services/qdrant_service.py` | added `get_client()` and `collection_name` to the facade | makes the endpoint the new security gate protects actually reach Qdrant (F-1) |
| `backend/tests/test_inspect_source_qdrant_facade.py` (new) | pins both names the route reads | the route's own test used a container shape the live app never has |

Nothing else was edited. No test was weakened, no flag was flipped, no `.env` was modified, no container was recreated, no migration was applied, nothing was committed or pushed.

---

## 6. Limits of this review

- The full backend suite was run twice (before and after the F-1 fix): `14141 passed` then `14143 passed`, both exit 0. It is the pre-existing suite, not a new gate; the new tests are inside it, not alongside it.
- The Railway environment was not touched and not inspected this session (paused by owner directive). `FORWARDED_ALLOW_IPS`, one replica, `/api/healthz`, migration order and the staging smoke test are prerequisites from the 2026-11-12 plan, not verified here.
- The "router timed out 27 of 27 times in 12 h" claim in `lessons.md` could not be re-derived: the current container's logs do not reach back 12 h. The *mechanism* (0.45 s budget under 470–690 ms latency) is consistent with the code and with the new default, and the default flip removes the exposure either way.
- `docs/REINGESTION_RUNBOOK_2026-11-12.md`'s re-measured corpus shape is taken as provenance; it was not re-derived.
- No grading, no paid evaluation run and no LLM-judged measurement was performed: the provider account is out of budget, so any such run would have measured the quota, not the product.
- Mobile/WebKit playback, hosted CSP and the production bundle were not re-tested.

---

## 7. Conditions to move from NO-GO to GO

1. ~~**Restore provider budget** (F-3)~~ — **superseded 2026-11-14**: the refusal was the app's own monthly cap, not the provider account. See §8.
2. ~~**Rebuild the backend image** so F-1's accessors are live~~ — **done 2026-11-14**, accessors live and verified. See §8.
3. ~~**Apply the two pending local migrations**~~ — **done 2026-11-14**, plus a fourth migration and a regenerated snapshot. See §8.
4. Decide `T-E1` (answerability gate on/off) explicitly, since a `weak_match` can currently be served with no question-level gate. **Still open.**
5. Owner go for Railway, plus the 2026-11-12 prerequisites. **Still open.**

---

## 8. Addendum 2026-11-14 — what changed after the review, and four corrections

The 2026-11-13 change set was committed and the graded stack rebuilt by the parallel working session. Repository head is now `2f26bbbd` on `main`; the whole 2026-11-13 change set landed across `60293b1d` … `2f26bbbd`. This addendum re-tests the findings that depended on the old container and corrects three claims that were wrong or too strong. It does not rewrite the sections above: those were true of the `3a4d479f` tree and container on 2026-11-13.

### 8.1 Corrections

| ID | Claim on 2026-11-13 | Correct position (2026-11-14) | Why it was wrong |
|---|---|---|---|
| **F-3 / T-E2** | "The LLM provider account is out of spend" | **The app's own budget guard refused the call.** `OPENROUTER_MONTHLY_BUDGET_USD` was **100** while the month counter was **123.13**; `app/openrouter_budget.py:217` raises `OpenRouterBudgetExceeded`. The provider balance was never read. The graded overlay raises the local cap to 300, leaving 176.87 of headroom, which is why the graded stack serves normally. | The exception text is the app's copy of a provider-style message; it was read as provider evidence. **A cap refusal is not a balance reading.** |
| **F-5 / T-E6** | "The new 403 is invisible: `LinkSearchModal` only reads `res.ok`" | **Closed before this review ended.** `src/components/chat/LinkSearchModal.tsx:50-54` maps 403 → "This source is not cleared for display here.", 404 → "This source is not available.", 429 → rate-limit copy, and renders it in a `role="alert"` block at `:304-306`. | The review read the fetch call and stopped; the map already existed in the same file. |
| **F-6 / T-E4** | "Local Supabase is missing `message_citations` and `video_serving_decisions`" | **Fixed 2026-11-14.** Four migrations applied to the local stack, RLS re-proven on the real schema, snapshot regenerated. See §8.2. | — |
| **F-1 / T-E3** | "Requires a backend image rebuild to take effect" | **Live and verified.** `GET /api/search/inspect-source` now returns Qdrant-backed chunks for corpus videos: `CZ_r5sYeTyY` → 200, **6 chunks**, title "Power Of Serene Mind Practice"; `Gae2J6ExMsY` → 200, **5 chunks**, title "Break The Jinx of Failure Patterns". Zero `Failed to scroll Qdrant` lines in the last 30 minutes of backend log. | — |

### 8.2 What this session applied and proved

| Step | Evidence |
|---|---|
| `npx supabase migration up` (local only) applied `20261107000000`, `20261107000001`, `20261113000000` | All four tables exist: `message_citations`, `corpus_takedowns`, `video_serving_decisions`, `video_serving_decision_audit`; versions recorded in `supabase_migrations.schema_migrations` |
| **New finding → new migration** `20261114000000_message_citations_provenance_defaults.sql` | `20261107000000` created `rights_status TEXT NOT NULL DEFAULT 'licensed'` and `speaker_verified BOOLEAN NOT NULL DEFAULT true`. A row inserted without those columns therefore **asserted** a cleared licence and a verified voice — the exact defect the 2026-11-13 client fix removed in `citationLedgerFlags()`, left in the table. The new migration drops both defaults and adds `CHECK (rights_status IN ('cleared','unverified','licensed','revoked'))`. The only writer (`chatStorage.ts:483-503`) already supplies both columns explicitly, so no working insert path changed. |
| Provenance probe (rolled back) | insert omitting both columns → **rejected** (`not_null_violation`); insert with explicit values → **accepted**; invented status `'probably-fine'` → **rejected** (`check_violation`) |
| RLS probe on the applied policy set (rolled back, as `authenticated` with two `auth.users` owners) | owner A sees **1** own row, **0** of owner B's; A's insert for A's message **allowed**; A's insert for B's message **denied** — `new row violates row-level security policy for table "message_citations"` |
| Schema snapshot regenerated from a clean local dump | `supabase/schema_snapshot.sql` **+200 lines, 0 deletions**; `migration_lint.py --dump-file` → `SUCCESS`, exit 0. Before this, the snapshot did not contain any of the four new tables while the migrations existed on disk — the snapshot had drifted from the migration set. |
| Node-22 parity (T-E9) | `node v22.22.3`: `tsc -b` exit 0; `vitest run` **1,157 passed / 6 skipped** (184 files); `npm run build` exit 0, 29 routes prerendered. CI pins 22 in `main-hard-gates.yml`, `prelaunch-gate.yml`, `production-readiness.yml` (20 in `lint-test.yml`, `dependency-check.yml`). |
| **New producer** `scripts/ops/collection_fingerprint.py` (T-E10 root cause) | `graded_capture.py:410` in **both** trees hardcodes `"collection_fingerprint": None`, and `graded_registered_report.py:352` declares a null fingerprint an invalid run — so every capture was invalid by construction and the bar was unmeetable in both directions. The new script scrolls the served collection read-only and writes `{points, ids_sha256}`; live: `first_person_v10` = **4,224 points**, `ids_sha256` `c96200d7…`. It **refuses** `--write` once a report exists (retro-fitting guard) and returns exit 2 — never `{points: 0}` — when Qdrant is unreachable (verified against a 404 collection and a dead port). |
| Full backend suite, final tree | **`14253 passed, 22 skipped, 2 deselected, 2 xfailed`** in 349.69 s, exit 0 — the 14,243 that the parallel session's tree already had, plus 10 new pins (4 provenance, 6 fingerprint). |
| Telemetry invariant, re-checked after all of the above | `public.corpus_gate_rejections` = **3,135** before and after every run in this session; the `PYTEST_CURRENT_TEST` guard is still the only reason and was not touched. |

### 8.3 New findings from this pass

| ID | Sev | Finding | State |
|---|---|---|---|
| F-8 | **P1 (provenance)** | The citation ledger's column defaults asserted rights clearance and speaker verification. Fixed by `20261114000000`; the same default may exist wherever a table default was written before the X40 rule. | **FIXED**, local only; not applied anywhere else |
| F-9 | P2 | The graded overlay `backend/docker-compose.graded.yml:81` replaces the volume list with `!override` and omits `../transcripts`. **`/app/transcripts` does not exist in a graded container**, so the inspect-source local-transcript fallback and any `/app/transcripts` reader are absent by design. A 0-chunk inspect result in a graded stack is therefore not evidence that the Qdrant path failed. | **Documented**; intentional, but it means the graded stack is not the dev stack in one more way |
| F-10 | **P1 (evidence)** | **`20261114-graded-7` is invalid, and must not be cited as a quality FAIL.** `registered_report.md`: `run valid: False` — *"manifest lacks collection fingerprint (points count + id sha)"*. It also reports 3 failed bars (showable 0.7561 vs 0.85, p95 10,015 ms vs 10,000, hub rule 4). An invalid run cannot support a PASS **or** a FAIL verdict; the numbers are diagnostic until a valid run exists. | **ROOT CAUSE FOUND, PRODUCER BUILT** — `backend/scripts/ops/graded_capture.py:410` and `scripts/ops/graded_capture.py:410` hardcode `"collection_fingerprint": None`, so *every* capture was invalid by construction and the bar was unmeetable in both directions. `scripts/ops/collection_fingerprint.py` now produces `{points, ids_sha256}` read-only and writes it into a pending manifest, refusing once a report exists. Live: `first_person_v10` = 4,224 points, `ids_sha256` `c96200d7…`. graded-7 itself stays invalid (re-run needed, spend). |
| F-11 | P3 | `RightsCleared`/`rights_status` vocabulary is not shared across layers: the client writes `cleared|unverified`, the corpus/rights register uses `licensed`, and the ledger's CHECK now allows all four. Nothing currently joins them, so a reader can treat `cleared` and `licensed` as different states when they mean the same thing. | **OPEN** — decide one vocabulary |

### 8.4 Still blocking a faculty demonstration

Not budget: with the graded overlay the guard has headroom and the stack serves. The blockers are now **quality and evidence**:

1. **No valid graded run exists.** graded-7 is invalid (F-10); graded-6 was single-judge. The registered bar needs a run whose manifest carries the collection fingerprint.
2. **Served-but-weak clips.** One clip served 4 of 41 questions (hub rule fail); 7 of 41 rows had grader disagreement. `T-E1` (answerability gate off) is still an owner decision and is the cheapest lever on this.
3. **p95 latency**, 10,015 ms against a 10,000 ms limit on that (invalid) run.
4. **Non-determinism**: the same first-turn question abstained in one pass and served in another on the rebuilt stack.

### 8.5 Corrections to this document's own references

This report moved from `audits/reports/` (git-ignored, so a committed document pointing at it was pointing at nothing) to `docs/analysis/`, which is tracked. Every reference in `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` and `lessons.md` was updated to the new path.

### 8.6 Second pass, 2026-11-14 — the agent-owned rows closed, the human gates opened

Everything below is uncommitted work in the working tree at head `2f26bbbd`. No commit, no push, no
image rebuild, no container recreate, no `.env` change, no hosted migration, no Qdrant write, no
graded run.

| What | Evidence |
|---|---|
| **T-E2 — a cap now announces itself** | `log_budget_headroom` (`backend/app/runtime_budget.py`, wired in `main.py` after `log_runtime_budget`) reads the ledger once at boot through the guard's own `_keys()` and logs one of: over-cap (naming `OPENROUTER_MONTHLY_BUDGET_USD`, the two numbers, and "not a provider balance problem"), a 70 % warning, or the plain ledger line. An unreadable ledger logs nothing as a breach. The reader is bounded (`socket_connect_timeout=2`, `socket_timeout=2`) so a dead Redis cannot hold startup. 9 tests: `backend/tests/test_budget_headroom_2026_11_14.py`. |
| **T-E7 — the draft rows have a consumer** | `scripts/ops/run_conversation_cases.py`. 24 rows / 30 turns, both shapes (`turns`, `question`); one anonymous session per case, job polling, `retry-after` honoured; records route, grounding, abstain cause, citation video ids, latency — never seeker or teacher text. Dry run default; `--execute` requires `--i-have-logged-the-spend`. Every output row is `draft_needs_owner_review` and the summary says it is not a verdict. 7 tests. **Nothing executed**: the rows are still drafts until the owner reviews them (D6). |
| **T-E8a — idle rate measured** | Container started 03:46 UTC, `RestartCount=0`, ~3 h, 1,712 log lines: **0** `degrading to allow`, 0 Redis connection errors (the 8 Redis lines are successful-connect INFO). The 2 events in the earlier 10-minute window came from a previous container. Load rate remains unmeasured. |
| **T-E12 — a ladder, not a synonym pair** | `backend/app/config.py:1623-1634` states it outright: `licensed` is an ingestion-time default stamped on every chunk, `cleared` is what a human-run backfill sets. Live confirmation on a 200-point scroll of `first_person_v10`: `licensed` 124, absent 76, **`cleared` 0**. Recommended ladder and the consequence for `serve_only_registered_sources`: `docs/analysis/OWNER_DECISIONS_2026-11-14.md` D3. |
| **Five human-gate packets** | `docs/reviews/2026-11-14-human-gates/` — clinician packet quoting **two blocks actually served** by the local stack (acute crisis 560 chars, moderate distress 1,036 chars, captured in `crisis_copy_probe.json`), 11 native-speaker rows, 14 helpline entries, 751 rights assets, 303 gold pairs, 41 seeded served answers. Every decision column empty. Generator + 7 tests; regeneration is byte-identical. |
| **A weaker claim than the one this report started with** | The gold set is worse than "two annotators agree": `annotator_A.csv` and `annotator_B.csv` hold 303 rows each but share only **101 pair ids**, and those 101 agree identically. The other **202 pair ids exist in A only** — so two thirds of the batch has *one* label, not two. The packet now reports three states (`same` / `differs` / `only_in_a`) instead of collapsing "no second label" into "disagrees". |
| **Agent artifacts** | Stale worktree `agent-a2efdd43228d6c02b` removed (`git worktree remove --force`, exit 0; **branch kept**, so its commit stays reachable) then `git worktree prune`. `agent-ad9afb9d8291c9371` kept because it holds the only copy of the unmerged "related teachings" work; that work is also preserved as `.work/unmerged-related-teachings-2026-11-12.diff` and `.work/unmerged-related-teachings-untracked-2026-11-12.tgz`. |
| **Verification, this pass** | Backend suite on the final tree: **`14276 passed, 22 skipped, 2 deselected, 2 xfailed`** in 351.91 s, exit 0 — the 14,253 the tree already had plus 23 new pins (9 budget headroom, 7 conversation runner, 7 review packets). The one red the suite found on the way was mine: `test_exception_and_import_ratchets` (broad catches 723 against a shrink-only ceiling of 722, because `read_spend_ledger` used `except Exception`); fixed by enumerating the exception tuple, which also catches `redis.exceptions.RedisError` that `except OSError` would miss. Frontend on Node 22.22.3: `tsc` 0, `vitest run` **1,157 passed / 6 skipped** (184 files, 1 skipped), `npm run build` 0 with 29 routes. Guards: `lesson_guards` publication/claims/fp-writes 0, `config_lint` PASS, `stale_flags` 24 stale-looking / 0 blocking, `guru_literal_guard` PASS, `supabase_types_lint` 80 tables / 0 gaps, `migration_lint` SUCCESS, `git diff --check` clean, ruff check/format clean on all touched Python. Telemetry invariant re-checked after the suite runs: `public.corpus_gate_rejections` = **3,135**. |

**What is still not true, and must not be said:** no valid graded run exists; no human gate is
signed; the four citation-ledger migrations are local-only; Railway is paused. A faculty demo can
show the product and the safety paths, labelled diagnostic (D4), and nothing more.

