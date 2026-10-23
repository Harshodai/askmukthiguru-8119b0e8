# AGENTS.md split proposal, 2026-10-22

Status: PROPOSAL ONLY. Nothing was moved, edited, committed or staged. The owner (Harsha) approves block by block before anything changes.
Source reviewed: `AGENTS.md` as it sits in the working tree (sha256 `85a890e759146dac…`, 492 lines, 79,985 bytes). It carries uncommitted owner edits (+81/-1 vs HEAD, the Oct 21 and Oct 22 first-person entries), so the archive must be cut from the working-tree file, not from `git show HEAD:AGENTS.md`.

## 1. Summary

- Lines 5-163 are 47,205 bytes (59% of the file) in 17 `###` blocks. (The brief said 32 entries; the file has 17 blocks in that range. Bullets inside them number more.)
- Of the 17: 13 mix provenance with at least one standing rule, 2 are binding invariants (`Ingestion Safety Invariants`, `Fresh audit invariants`), 2 are fully archivable (`Docker idle-cost handoff`, `First-person v5/v10 completion audit`). A mechanical move would have dropped rules in the 13, as the brief feared.
- Proposal: archive the whole range verbatim, then put back 39 verbatim extracts (about 12,678 bytes) plus two whole blocks (`Ingestion Safety Invariants`, and `Fresh audit invariants` minus two provenance lines).
- Estimated result: AGENTS.md goes from 79,985 bytes (~19K tokens) to about 50,939 bytes (~12K tokens). That is a saving of roughly 29 KB, about 7K tokens per read, not the whole 20K. Getting further needs the optional trims in section 8, which are outside the brief.
- Section 6 lists five problems that need an owner decision but are not part of the move: a CLAUDE.md vs AGENTS.md conflict on where `FIRST_PERSON_COLLECTION` is set, a dangling pointer to a CLAUDE.md section that no longer exists, and stale text in the harness and Railway entries.

## 2. Verdict per block

KEEP = stays as is. ARCHIVE = moves whole. MIXED = whole block moves to the archive, binding sentences listed in section 3 stay in AGENTS.md verbatim. Sizes are bytes of the block (heading to the line before the next heading).

| Lines | Heading (exact) | Verdict | Why |
| --- | --- | --- | --- |
| 5-12 | `### Repository dead-code sweep + script-tree drift closure — Oct 22, 2026` | MIXED (archive + extract) | Bullets 6, 7, 9, 10 binding (extract). 8 and 11 provenance (archive). |
| 13-22 | `### First-person v10 public-release remediation — Phase 0/1 done, Phase 2+ not started — Oct 21, 2026` | MIXED (archive + extract) | Only the NO-GO / "do not enable until B1-B7" line (14) binds. Rest is Phase 0/1 measurements and tool notes. Phase-2 precondition (soundfile) is superseded by the Oct 22 Phase 2 entry. |
| 23-33 | `### First-person v10 — the three evidence defects fixed + owner-only preview live in Docker — Oct 22, 2026` | MIXED (archive + extract) | Bullets 24, 25, 26, 27, 29 (rebuild cmd), 30 binding or standing. 28 (tier arithmetic), 31 (packets NOT approved), 32 and the defect narrative are dated. |
| 34-44 | `### First-person v10 — Phase 4/5 done: independent rights register, corpus tiers, B4 isolation, owner-only test mode — Oct 22, 2026` | MIXED (archive + extract) | Bullets 36, 37, 38, 39, 40, 42 binding. 35 repeats NO-GO; 41 smoke matrix and 43 lessons dated. Bullet 39 tier counts are SUPERSEDED in-text. |
| 45-55 | `### First-person v10 — Phase 2 (per-span ECAPA evidence) done; B1 measured — Oct 22, 2026` | MIXED (archive + extract) | Bullets 50, 51, 52 binding. 46 repeats NO-GO; 47-49, 53, 54 are measurements/provenance. |
| 56-63 | `### First-person v10 — Phase 3 (ASR coordinates + audio windows) candidate only — Oct 21, 2026` | MIXED (archive + extract) | Bullets 59, 60 binding. 57 NO-GO already covered; 58, 61, 62 root-cause history and tool notes. |
| 64-71 | `### First-person v5/v10 completion audit — harness OFF again, three provenance gates open — Oct 21, 2026` | ARCHIVE | Binding sentence (65, harness stays off) is covered by line 14/24 extracts. 66 ("schema mismatch, not a regression") describes the Oct 21 local state that Oct 22 entries have since changed: stale, archive. 67-70 measurements. |
| 72-79 | `### First-person context harness — phases A/B/D landed, serving unwired — Oct 20, 2026` | MIXED (archive + extract) | Bullet 77 (prohibitions) binding. 73 says the harness is "not wired into serving" but the Oct 21 audit says the bridge consumed harness answers: stale, archive. 74-76, 78 dated. |
| 80-84 | `### `first_person_mode` default corrected to `retrieval_only` — Oct 20, 2026` | MIXED (archive + extract) | Bullet 81 binding. 82-83 describe the change and the local .env quirk (dated). |
| 85-91 | `### Local first-person serving pointer + answer-quality measurement — Oct 19, 2026` | MIXED (archive + extract) | Sentence in 86 (how the collection switch works), tail of 88 (clinician-review rule), sentences in 89 and 90 stand. Collection name v9, promotion evidence, 42-question banks are dated. |
| 92-101 | `### First-Person Pipeline Quality Breakthrough — Oct 11, 2026` | MIXED (archive + extract) | Mostly corrections of withdrawn claims (provenance). Standing: sentence in 94 and 96 (speaker-label rule). Heading is cited by a test comment, see section 5. |
| 102-112 | `### Ingestion Safety Invariants — Aug 28, 2026` | KEEP | Labelled "binding repository invariants"; P0-bug rules. Cited by code comments as "invariant #1/#2" and "Invariant 1", so numbering must not change. |
| 113-130 | `### Corpus ingestion handoff — Aug 27, 2026` | MIXED (archive + extract) | PIDs, /tmp paths, source counts, commits, "REFETCH not started" are dated. Bullets 117 and 118 are standing rules (extract). Host command (119-126) still resolves from backend/ but its inputs are /tmp files: archive. |
| 131-141 | `### Fresh audit invariants — Aug 21, 2026` | KEEP (minus lines 134-135) | Heading says invariants. Bullets 132, 133, 136, 137, 138, 139, 140 bind (138 is cited by a test as the SSE public-projection rule). Only 134 and 135 (deployment ids, one proof run) are provenance: move those two lines. |
| 142-151 | `### Fresh Railway handoff — Aug 23, 2026 post-audit correction` | MIXED (archive + extract) | Bullets 143, 144, 148, 149 deployment ids / test runs / samples (dated). 145, 146, 147 (last sentence), 150 are standing rules. 150 also says compiled.json is "absent", which is stale (see section 6). |
| 152-157 | `### Docker idle-cost handoff — Aug 23, 2026` | ARCHIVE | Memory measurements and a manual worker stop. Compose profile change is visible in docker-compose.yml, which is the source of truth. |
| 158-163 | `### Localhost safety-order handoff — Aug 23, 2026` | MIXED (archive + extract) | Bullets 159, 160 are safety-ordering rules (extract). 161-162 are probe results. |
| 164-169 | `## Deployment Readiness Checklist (Jul 19 to Aug 10, 2026) — archived` | KEEP | Already an archive pointer plus one binding rule (Aug 21 rotation invariants, BRAIN_KEK). Untouched. |
| 170-187 | `### Security Invariants (as of Aug 1, 2026)` | KEEP | Binding; cited by code (`lettuce_detect_service.py`) and docs by heading. |
| 188-188 | `## Plan & Review` | KEEP | Agent workflow rules (read lessons.md first, plan file, approval). |
| 189-196 | `### Before starting work` | KEEP | Part of Plan & Review. |
| 197-200 | `### While implementing` | KEEP | Part of Plan & Review. |
| 201-216 | `## Docker Execution on Host` | KEEP | Docker PATH / keychain workaround. Cited by name in `.github/workflows/nightly-load.yml` (4x). |
| 217-227 | `## Supabase` | KEEP | `X-Test-Key` three-condition rule is a security control. |
| 228-237 | `## Local Benchmarking` | KEEP | Procedural. Last line ("current working provider ... nim") is dated, see optional section 8. |
| 238-248 | `## Cache Management & Ingestion Isolation` | KEEP | Redis flush / namespace rules. |
| 249-271 | `## Non-Interactive Shell Commands` | KEEP | Standing agent rule. |
| 272-273 | `## Troubleshooting Guidelines for Agents` | KEEP | Standing. One dangling pointer, see section 6. |
| 274-277 | `### React Component Crashing` | KEEP | Part of troubleshooting. |
| 278-281 | `### Code-Review-Graph MCP "Context Canceled"` | KEEP | Part of troubleshooting. |
| 282-285 | `### "Connection issue" chat responses that are actually retrieval failures` | KEEP | Part of troubleshooting; points at a CLAUDE.md section that no longer exists (section 6). |
| 286-294 | `## Post-Change Documentation Checklist` | KEEP | Binding checklist; root CLAUDE.md line 98 says to update AGENTS.md. |
| 295-303 | `## Session Completion` | KEEP | Consistent with the no-commit-unless-asked rule. |
| 304-308 | `## Agent Technical Skills` | KEEP | Small; points at `.agents/skills`. |
| 309-316 | `## MCP Tools: code-review-graph` | KEEP | Tool routing. Out of scope; auto-generated block (optional section 8). |
| 317-326 | `### When to use graph tools FIRST` | KEEP | Sub-section of MCP Tools. |
| 327-339 | `### Key Tools` | KEEP | Sub-section of MCP Tools. |
| 340-346 | `### Workflow` | KEEP | Sub-section of MCP Tools. |
| 347-357 | `## Local Codebase Intelligence & Memory MCP Layer` | KEEP | Contains binding constraints (Node 22 only, worktree cleanup). |
| 358-362 | `### Strict Environment Constraints` | KEEP | Binding: Node 22 only (Node 25 OOMs WASM), Bun path, git worktree cleanup before ending a session. |
| 363-366 | `### Utilizing Local MCP Tools` | KEEP | Tool routing guidance. |
| 367-368 | `## Ponytail & Headroom Guidelines` | KEEP | Duplicates hook-injected text for Claude Code, but AGENTS.md is the only copy other agents (Codex, Cursor) read. Optional section 8. |
| 369-383 | `### The Ladder (hard rule — runs BEFORE writing any code)` | KEEP | Sub-section of Ponytail & Headroom. |
| 384-390 | `### Ponytail Principle` | KEEP | Sub-section of Ponytail & Headroom. |
| 391-412 | `### Headroom Principle` | KEEP | Sub-section of Ponytail & Headroom. |
| 413-430 | `## Mobile App` | KEEP | Stable reference facts. |
| 431-439 | `## Multimodal Chat Upload Invariants (Aug 19, 2026)` | KEEP | Binding invariants. |
| 440-445 | `## Railway Deployment (Production) — archived` | KEEP | Already an archive pointer. |
| 446-450 | `## ONNX Reranker + ColBERT MaxSim (Jul 27, 2026) — archived` | KEEP | Already an archive pointer. |
| 451-475 | `### Dependency Lock Authority and Clean Release Installs (Aug 13, 2026)` | KEEP | Binding release rule. |
| 476-486 | `## Active latency and quality invariants — 2026-08-22` | KEEP | Binding rules in paragraphs 1-2. Paragraph 3 (2026-08-22 measurements) is dated: optional section 8. |
| 487-493 | `## Cost-effectiveness invariants — Aug 22, 2026` | KEEP | Binding principles in bullets 3-4. Bullets 1-2 are 2026-08-22 dollar figures: optional section 8. Cited by heading in two docs, so keep the heading. |

Classification rule: a block is BINDING if an agent that ignored it could break a safety, ingestion, security, rights or deploy rule. It is DATED if it only records what happened (counts, hashes, PIDs, dated measurements, "now fixed" narratives). When a sentence could be either, it is treated as binding.

## 3. Verbatim extracts that stay in AGENTS.md

Each quote below was machine-checked as an exact substring of the current `AGENTS.md` line named. They would be placed together, in this order, under one new heading right after the line-3 status note (replacing lines 5-163 except the two kept blocks). Source line numbers are for the working-tree file today.

Proposed AGENTS.md insert (heading + intro):

> ### Standing rules extracted from dated handoffs (2026-10-22)
> Verbatim from the entries archived in `docs/agent/claude-md-archive/AGENTS-handoffs-2026-10-22.md`. Source heading and line are noted per item; counts and states inside them were true on their stated date, not necessarily now. For a conflict, code and scoped CLAUDE.md files prevail.

**X1** (line 6; script-tree parity rule; test-pinned)

> - **Binding:** the `scripts/` ↔ `backend/scripts/` duplicate trees are now **fully reconciled and pinned**. Three duplicated paths outside `scripts/ops/` had drifted in both directions, and because `backend/docker-compose.yml` bind-mounts repo-root `scripts/` at `/app/scripts` (shadowing the image's baked `backend/scripts`), the **container ran the stale copies** while CI and the host ran the backend ones. Worst case: `scripts/verify_rls_policies.py` was missing the `canonical_memories` RLS probe — a **security control** silently skipping the most sensitive table. All shared paths are byte-identical now, and `backend/tests/test_repo_layout.py::test_cross_tree_shared_scripts_are_identical` pins every one of them. **Any new script duplicated across the two trees must be added byte-identical in both, or not duplicated at all.**

**X2** (line 7; declares the one allowed exception)

> - **Binding:** `backend/scripts/` holds the canonical content for every shared path. The single intentional exception is `eval/run_ragas_eval.py` (root = standalone RAGAS runner, tested by `tests/test_ragas_claim_ledger.py`; backend = older golden-set harness) — it is declared in `_DIFFERENT_TOOLS` and asserted to **stay** distinct.

**X3** (line 9; standing owner decisions: do not delete these)

> - **What was deliberately NOT removed (owner decisions):** `memory/okf/staging/` (820 entries — read by the admin review queue; the `_excluded_parts` filter in `services/memory/okf_store.py` is the release-critical gate), `memory/okf/compiled.json` (10.4 MB tracked artifact — read at runtime), `docs/production-readiness/` raw captures (governance register classifies it append-only historical), `.agent/` vs `.agents/` skill trees (each serves a different harness), and `backend/scripts/eval/run_ragas_eval.py` (a planning note still targets it).

**X4** (line 10; rule for proving a file dead before deleting)

> - **How to verify a file is dead:** resolved-import check only — `ast.parse` for Python, import-specifier resolution for TypeScript. A name grep is not evidence: `form` matches `chat.py`, `security` matches every skill doc, and a doc mention is a reference to *update*, not a reason to keep the file. **Rule:** prove no import resolves to it before deleting it.

**X5** (line 14; public-release NO-GO + harness flag; the B1-B7 gate)

> - **Binding:** the public-release verdict is **NO-GO** and unchanged. `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` **and** inside the container (re-verified at Phase 0). Do not enable it until B1–B7 in `docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md` are closed and recorded.

**X6** (line 24; current alias/flag state and "no writes" posture (supersedes older copies))

> - **Binding:** the public-release verdict is **NO-GO and unchanged**. `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` **and** in the container; the public `first_person` alias still points at `first_person_v10` (4,197 points); **no Qdrant write, no alias change, no Redis mutation, no deployment, no Railway action.** The local-review flag (`FIRST_PERSON_LOCAL_REVIEW_ENABLED`) is the only first-person flag that is on, and only in the local container.

**X7** (line 25; schema rule: field never repurposed)

> Schema is now `first-person-speaker-conflict-v2`: `audio_duration_ms` is **removed** (never repurposed) and replaced by `audio_file_duration_ms` + `audio_slice_duration_ms` + `audio_start_ms` + `audio_end_ms`.

**X8** (line 26; identity rule)

> `(video_id, guru_id)` is **not** an identity.

**X9** (line 27; standing: do not re-key without owner approval)

> **No namespace fix was applied** — it would re-key the corpus and invalidate the 1,600 Phase-2 verdicts, the rights join and the pinned contract. The collision is **unresolved** and both members are quarantined in the new tier `deterministic_id_collision_quarantine`.

**X10** (line 29; only operational how-to for the owner-only preview)

> Rebuild with `cd backend && FIRST_PERSON_LOCAL_REVIEW_ENABLED=true bash ../scripts/docker-safe.sh docker compose up -d --build --no-deps backend`.

**X11** (line 30; canonical label; a contract pinning another label makes the mode refuse to start)

> - **The label is now two canonical lines** — `REVIEW CANDIDATE — NOT PUBLIC RELEASE` and `AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION` — in the service, the route, the CLI, the contract, every citation and the owner guide. A contract pinning a different label is stale and the mode **refuses to start**.

**X12** (line 36; owner-only preview gating)

> It runs only when `FIRST_PERSON_LOCAL_REVIEW_ENABLED=true` **and** `IS_PRODUCTION=false`, refuses to start when any pinned artifact is missing or whose sha256 changed, and every response carries `"review candidate / not public release"`.

**X13** (line 37; B4 serving-contract gate; explicit "do not fix back into a startup raise")

> - **B4 is implemented and tested** (`backend/services/first_person_serving_contract.py` + `backend/config/first_person_serving_contract.json`): a legacy store may not point at an fp-context collection, a context store may not point at a legacy-only collection, the two may not share a collection, and the exact-cache fingerprint must carry `legacy_collection`, `legacy_schema`, `legacy_corpus_version` and `evidence_policy`. **Production raises at startup; outside production the legacy path fails closed by itself** (`abstain_reason=serving_contract_violation`) instead of taking the whole app down — do not "fix" that back into a startup raise. Adding the four fingerprint components invalidated the 24 h exact cache once, by design.

**X14** (line 38; rights register provenance rule)

> **B5 register exists but is NOT signed off.** `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` (751 assets) is built from `docs/rights/CONTENT-RIGHTS.md`, never from a Qdrant payload field.

**X15** (line 39; caution against over-claiming the tier)

> **The first tier is NOT "public verified":** its evidence policy is `automated_evidence_candidate`, and the 1,127 variants need a separate owner decision.

**X16** (line 40; quarantine, never relabel)

> - **The 45 speaker-label conflicts are quarantined**, never relabelled: `audits/evidence/public_release_phase4_speaker_conflict_review_2026-10-22.md` is the human review packet (window, WAV sha256, YouTube link, scores, empty decision/reviewer/timestamp).

**X17** (line 42; B4 gate scope (arming it on test doubles broke 102 tests))

> - **B4 gate scope:** the gate is armed for the **real** serving path (a real `FirstPersonStore`, or a store pointed at `first_person*` / `fp_context*`). A stand-in store in a unit test is not gated — the first, wider version turned 102 existing tests into `abstained / serving_contract_violation`.

**X18** (line 50; binding method for any Phase-2 consumption)

> - **Binding for any future Phase-2 consumption:** the reference is built from the **two human-confirmed anchor moments** in `backend/scripts/ops/speaker_attribution.py::ANCHORS` (recomputed here with a **pinned** ECAPA revision — the repo's `speaker_attribution.py` loads the model *unpinned*, which breaks the HF-pin invariant), widened over train-split slices. Method constants (`ENROLL_MIN=0.75`, `ANCHOR_LABEL_MIN=0.55`, `ANCHOR_MARGIN=0.15`, `CLUSTER_DISTANCE=0.6`, 2 s window / 1 s hop) are **inherited unchanged** from that file and **not re-tuned** on this corpus. The expected guru of a span is the corpus assignment carried by the Phase-3 candidate — it is the **claim under test, never the evidence**; a span whose voice contradicts it is `refused_guru_mismatch` and is never verified.

**X19** (line 51; limit on what the FAR/FRR numbers prove)

> - **Honest limit (do not overstate):** the trial labels come from the same two anchors the references are widened from, so the measured FAR/FRR is a *relative* consistency measurement on held-out videos, **not** a human-certified false-accept rate. The repo has no filled human speaker-label sheet (`docs/attribution/*.csv` speaker columns are blank), so certification is a **B7** dependency. The margin gate also collapses to an ordering requirement (every held-out impostor margin is negative).

**X20** (line 52; dependency posture: speechbrain lazy, lock regen needs approval)

> `torch` and `scikit-learn` are already in `backend/requirements.lock`; `speechbrain` is **not** in the lock and is imported **lazily** inside the embedding function, so the app import graph and the test suite never depend on it. `backend/requirements.txt` / `requirements.lock` are **unchanged**; no lock regeneration, no runtime-image change, no service recreate. In-image execution needs its own approval plus `uv pip compile backend/requirements.txt --output-file backend/requirements.lock`.

**X21** (line 59; WAV source rule (stubs have no PCM))

> - **Binding for Phase 2:** slice ECAPA audio from `audio_archive/wavs/`, **never** from `<asr_root>/audio/` — 515 of 516 files in `mass_ingest_2026-10/audio/` are 86-byte WAV stubs with a correct declared duration and **no PCM data**. Use the candidate's rebuilt `[audio_start_ms, audio_end_ms]`, not the live payload's.

**X22** (line 60; corpus_version / alias rule)

> - **Binding for any future candidate write:** the rebuilt corpus declares `corpus_version=fp-context-transcript-v2` because **502 of 1,600 candidate spans would collide with a live span id** under the live corpus version. Never repoint the `first_person` alias at a v2 collection while the speaker evidence is still open.

**X23** (line 77; prohibitions for the context harness)

> - **Prohibitions:** never default a missing `speaker_verified` to `true` (attribution without verification); never give the harness an LLM-authored sentence (its `answer_text` is exactly the stored span text, in order); `_serving_policy_fingerprint` already carries `context_harness`, `context_max_spans`, `context_selector` and `context_schema` (landed before wiring on 2026-10-20), so wiring must not remove them; without those entries a pre-harness answer replays for the 24 h exact-cache TTL.

**X24** (line 81; FIRST_PERSON_MODE default and production restriction)

> - **Binding:** the code default is `retrieval_only` (was `hybrid` since 2026-10-11 while its own comment and `services/first_person_release.py` both said `retrieval_only`). `hybrid` is now an explicit owner opt-in: set `FIRST_PERSON_MODE=hybrid` and expect LLM-authored opening/connective/question prose. Production still accepts **only** `retrieval_only`.

**X25** (line 86; how the serving collection is switched (CONFLICT with CLAUDE.md invariant 23, see section 6))

> The switch is the `FIRST_PERSON_COLLECTION` env value in the **project** `.env` — `backend/.env` for this stack, not the repo-root `.env` — applied with `docker compose up -d --no-deps --force-recreate backend` (`restart` never rereads `env_file`).

**X26** (line 88; distress decline boundary)

> `first_person_bridge` declines a clip at `_DISTRESS_DECLINE_LEVEL = 2` (MODERATE; deliberate 2026-10-05 fix), the graph then routes `intent=DISTRESS`, and the seeker gets scripted compassion boilerplate instead of the teacher's clip.

**X27** (line 88; safety: do not tune without clinician review)

> Router margin data: DISTRESS embedding route threshold 0.66 → 32/150 on-topic hijacks; 0.72 → 10; but at **0.74+** `"I am suicidal"` stops matching the router (still caught by the guardrail `self_harm` rail and `assess_distress`). Do not tune this boundary without a clinician-review pass.

**X28** (line 89; bind-mount topology rule)

> Per `L-OPS-MOUNT-1`, `backend/scripts/` is NOT bind-mounted into the container, so anything needing `docker exec` must live in repo-root `scripts/ops/`.

**X29** (line 90; operational gotcha for sweeps)

> `/api/chat` is rate-limited to **20/min** (batch sweeps must throttle and retry on 429)

**X30** (line 94; binding lesson)

> Per binding `L-FP-HYBRID-SCAFFOLD-1`, a gateless run cannot speak to answerability.

**X31** (line 96; speaker label rule (L-NO-INVENTED-CREDIT-1))

> `"shared in <channel>"` is the intended label for unverified speakers; the fix belongs at ingest via speaker verification, never via ID-to-name mapping. Head `86cc77f6` implements that lane (`backend/ingest/verbatim/speaker_verify.py`, `speaker_verified` plumbing, 15 tests). Displayed speaker stays as-verified until then.

**X32** (line 117; transcript staleness invariant)

> - **Staleness invariant**: `PRE_EXTRACTED_MAX_AGE_SKIP=30 days`. Always `touch` projected transcripts before running ingestion or they will be skipped and fall back to live YouTube API.

**X33** (line 118; ingestion LLM provider rule)

> - **LLM provider for ingestion**: Use `OpenRouterService` (cloud-only mode, `OLLAMA_CLOUD_ONLY=true`). `bulk_ingest_video.py` was fixed from `OllamaService` → `OpenRouterService`. `LLM_PROVIDER=openrouter` env required.

**X34** (line 145; grounded-partial contract)

> - Grounded partials are deterministic source excerpts only: maximum two excerpts of 360 characters, absolute URLs, `verification.method=grounded_partial_evidence`, `partial=true`, `verification.passed=false`, and `faithfulness_score=0.0`. They are not verified generated teachings.

**X35** (line 146; partial-evidence cache rule; no global flush)

> - Partial evidence may be written only to exact/hot scoped caches. Semantic/vector writes are forbidden until those tiers gain fresh evidence, source-version, and support gates. Never use a global Redis flush to address this policy.

**X36** (line 147; do not generalize queued replay)

> Direct fetch-stream reconnect/resume remains unimplemented or unproven; do not generalize queued replay to direct streaming.

**X37** (line 150; no placeholders / no evidence-gated activations)

> - Curated `/app/memory/okf/compiled.json` and `/app/data/doctrine_lexicon.json` remain absent. Do not manufacture placeholders, activate ONNX/RRF/DBSF, mutate Neo4j schema, widen graph concurrency, or modify `scripts/ingestion/corpus/` without approved audited artifacts and held-out evidence.

**X38** (line 159; stage order: InputGuardrail before CircuitBreaker)

> - The default pipeline now runs `InputGuardrailStage` before `CircuitBreakerStage`. This is required so deterministic acute self-harm and other input safety decisions are not bypassed when an LLM provider circuit is open. The change is limited to `backend/app/pipeline/stages/pipeline_builder.py` and is covered by an explicit stage-order regression.

**X39** (line 160; ERROR/TIMEOUT maps to system_error)

> - Provider distress-classifier failures remain indeterminate and do not invoke degraded intent classification. An unblocked `ERROR` or `TIMEOUT` maps to public `grounding_state=system_error`, not `abstained` or `safety_redirect`.

Then, unchanged and in place: `### Ingestion Safety Invariants — Aug 28, 2026` (lines 102-111) and `### Fresh audit invariants — Aug 21, 2026` (lines 131-133 and 136-140; lines 134 and 135 go to the archive).

Note: `### Ingestion Safety Invariants` is cited as "invariant #1", "invariant #2" and "Invariant 1" from code comments. Its numbering must not change.

## 4. Not extracted on purpose

So the owner can overrule any of these. Each stays recoverable in the archive.

- Line 8 (what the sweep removed: 78 files by category) and line 11 (lessons pointers). Provenance.
- Lines 15-21, 28, 31, 32: Phase 0/1 tool notes, reconciliation counts, tier arithmetic, "packets NOT approved", regression totals.
- Lines 35, 46, 57, 65: each repeats the NO-GO / harness-off line already kept as X5 and X6.
- Line 66 (and 64-71 generally): says the local stack serves no first-person teaching because the legacy store points at the v10 collection. Oct 22 entries changed that picture, so the paragraph is stale as a state description.
- Line 73: "not wired into serving". Contradicted by the Oct 21 audit (line 69: the bridge discarded every harness answer, which only happens if the harness is wired). Archive and let the owner confirm current wiring.
- Line 76: the `L-FP-CONTEXT-GURU-SET-1` fix. Behaviour is covered by `test_first_person_context_red_team.py`.
- Lines 87, 92-93, 95, 97-99: promotion evidence for v9, Oct 11 corrections of withdrawn claims.
- Lines 113-116, 119-129: ingestion handoff state, host command (inputs are /tmp files), Supabase role passwords set by hand. Line 116 is the only place that explains `transcripts/<video_id>.md`; see section 5 for the code comment that cites it.
- Lines 134-135, 143-144, 148-149, 152-157, 161-162: deployment ids, test runs, probe samples, Docker memory measurements.

## 5. What depends on AGENTS.md (grep of tracked files)

Nothing parses AGENTS.md. No script, test, hook or CI step reads its content or headings; all references are prose or comments. Checked: `git grep` over py/sh/yml/json/js/ts/toml/Makefile, `.github/`, `.claude/settings.json`, `scripts/guards/`, `backend/tests/` (including `test_repo_layout.py`).

Would be affected by the split, ranked:

1. `.github/workflows/nightly-load.yml` lines 70, 90, 186, 210: comment "Repo Docker convention (AGENTS.md): never assume docker on PATH." The `Docker Execution on Host` block stays, so nothing breaks. No change needed.
2. Root `CLAUDE.md` line 3: "Confirm behaviour against code and scoped `AGENTS.md`/`CLAUDE.md` (`backend/`, `src/`) before acting." This is the sentence that sends agents to the whole file. Also wrong in fact: `backend/AGENTS.md` and `src/AGENTS.md` do not exist; the scoped files are `backend/CLAUDE.md` and `src/CLAUDE.md`. Fix proposed in section 7.
3. Root `CLAUDE.md` line 98: "Update this file and `AGENTS.md` when directory layout, services, env config or core pipeline patterns change." Still valid after the split. Optional rewording in section 7.
4. Code comments citing sections that STAY: `backend/services/lettuce_detect_service.py:77` ("Security Invariants"), `backend/guardrails/llama_guard_handler.py:87`, `backend/ingest/ontology_writer.py:260`, `backend/services/intelligent_metadata_extractor.py:16`, `backend/tests/test_answerability_check.py:165`, `backend/tests/test_okf_integrity_gaps.py:82` (all Ingestion Safety / Security Invariants), `backend/tests/test_citation_contract.py:195` ("public-projection rule" = Fresh audit invariants line 138). All stay valid.
5. Code comments citing sections that MOVE (comment-only, no behaviour): `backend/tests/test_first_person_pipeline.py:783` ("AGENTS.md First-Person Pipeline Quality Breakthrough") and `evals/grounding/verify_quote.py:8` ("AGENTS.md's Aug 27 corpus-ingestion handoff"). Both headings survive verbatim in the archive file. Suggested follow-up, not part of this split: append "(now in docs/agent/claude-md-archive/AGENTS-handoffs-2026-10-22.md)" to those two comments.
6. Docs citing headings, by name: `docs/COST_MEMORY_AUDIT_2026-10-04.md:88` and `docs/PROD_READY_OWNER_PACKAGE.md:81` (Cost-effectiveness, Security Invariants: both stay). Many `docs/` and `.claude/tasks/` files say "read AGENTS.md first" generically; the file still exists, so they keep working, they just read less.
7. `README.md` lines 13 and 221, `docs/DEVELOPER_GUIDE.md`, `docs/architecture/SYSTEM_ARCHITECTURE_HLD_LLD.md`, `docs/operations/documentation-governance-register.md`: link to the file by name. No change.
8. Pre-existing breakage, unrelated to this split: `evals/run_safety_scenarios.py:33` cites an AGENTS.md section "Local Dev Caveats" that is not in the file (it went to an archive earlier).
9. `docs/archive/agents-handoffs-2026.md` is the precedent for an earlier move (Jul-Aug 2026 handoffs, 2026-09-26). AGENTS.md line 438 points at it. Line 438 stays.

## 6. Problems found in the current file (owner decisions, not part of the move)

1. **Conflict on where the serving collection is set.** Root `CLAUDE.md` invariant 23 says the rollback is `FIRST_PERSON_COLLECTION=first_person_v7` "in root `.env`". AGENTS.md line 86 (extract X25) says the value lives in `backend/.env` "not the repo-root `.env`". Both also name different collections (v8 vs v9; line 24 says the alias points at v10). I kept X25 verbatim because the rule is binding if true, but it needs a check against `backend/docker-compose.yml` `env_file`. I did not resolve it.
2. **Dangling pointer, line 284** (`"Connection issue" chat responses...`): "see root `CLAUDE.md`'s \"Embedding dimension contract\" section". The slimmed CLAUDE.md has no such section; it moved to `docs/agent/claude-md-archive/CLAUDE-full-2026-10-22.md` line 293 (the pinned-pair rule survives as one bullet under "Data stores and caches"). Suggested wording: "see root `CLAUDE.md` \"Data stores and caches\" (embedding dimension / collection size pinned pair); detail in the CLAUDE-full archive, section \"Embedding dimension contract\"".
3. **Stale statement, line 150**: "Curated `/app/memory/okf/compiled.json` ... remain absent." Root CLAUDE.md says `memory/okf/compiled.json` is a 10.4 MB tracked artifact read at runtime. Line 150 is not extracted (the "do not manufacture placeholders" rule is, as X37), but the "absent" claim should not survive in the kept text. Note the AGENTS.md line 9 says the same file is "read at runtime".
4. **Stale statement, line 73**: "not wired into serving" (see section 4).
5. **Scoped files**: root CLAUDE.md line 3 names `AGENTS.md` as scoped in `backend/` and `src/`; it is not.

## 7. Target layout and exact wording

### 7.1 Archive file

Path: `docs/agent/claude-md-archive/AGENTS-handoffs-2026-10-22.md`

Content: the header below, then AGENTS.md lines 5-163 byte-for-byte from the working tree (including the blocks that are kept in AGENTS.md, so the archive is a complete record of the range and can be diffed). Command to build it, run only after approval (shown, not run):

```bash
{ cat <<'HDR'
# AGENTS.md handoffs and lessons, Aug-Oct 2026 (verbatim archive)

Moved verbatim out of root `AGENTS.md` on 2026-10-22: lines 5-163 of the working-tree file, 17 `###` blocks. Dated narratives and point-in-time measurements. Binding sentences inside them were copied back into `AGENTS.md` under "Standing rules extracted from dated handoffs"; `Ingestion Safety Invariants` and `Fresh audit invariants` were also left in place. Where this file and the code disagree, the code wins; re-check any number before citing it.

Index of blocks: see the heading list below.

HDR
  sed -n '5,163p' AGENTS.md; } > docs/agent/claude-md-archive/AGENTS-handoffs-2026-10-22.md
```

Also add one row to `docs/agent/claude-md-archive/README.md` (that file already has uncommitted edits from another session; append, do not overwrite):

`| AGENTS-handoffs-2026-10-22.md | Dated first-person v10 / ingestion / Railway handoffs and lessons (Aug-Oct 2026) cut from AGENTS.md; read when you need the narrative behind a standing rule in AGENTS.md |`

### 7.2 AGENTS.md edits (after approval)

- Replace lines 5-163 with: the new "Standing rules extracted" section (section 3), then the two kept blocks unchanged.
- Replace line 3 (status note) with:

> > **Active operating status — reviewed 2026-10-22.** This file holds binding repository invariants. Dated session handoffs and lessons (Aug-Oct 2026) are archived verbatim in `docs/agent/claude-md-archive/AGENTS-handoffs-2026-10-22.md`; older ones in `docs/archive/agents-handoffs-2026.md`. For a conflict, current source configuration, scoped instructions, and approved runbooks prevail; dated measurements are provenance, not live state.

### 7.3 Root CLAUDE.md pointer (exact wording)

Line 3, replace the sentence "Confirm behaviour against code and scoped `AGENTS.md`/`CLAUDE.md` (`backend/`, `src/`) before acting." with:

> Confirm behaviour against code and the scoped `backend/CLAUDE.md` / `src/CLAUDE.md` before acting. `AGENTS.md` is the rule file for other agents and for Docker, ingestion-safety, security, Supabase and cache work; read it only for those, not on every task. Its dated handoffs are in `docs/agent/claude-md-archive/AGENTS-handoffs-2026-10-22.md`.

Line 98 can stay as is. Optional rewording so the update rule is explicit about where dated detail goes:

> Update this file and `AGENTS.md` when directory layout, services, env config or core pipeline patterns change; put dated handoffs in the archive folder, not in `AGENTS.md`.

## 8. Optional further trims (outside the brief, not part of this proposal's approval)

Sizes are the current byte counts. Only worth doing if the target is a much smaller file.

- Lines 367-411, Ponytail/Headroom/caveman text (~2,677 B): duplicated by the SessionStart hooks for Claude Code; kept because other agents read AGENTS.md and have no hook.
- Lines 308-365, MCP tool tables and local MCP layer (~3,915 B): partly a generated block; the Node 22 and worktree-cleanup constraints (lines 358-361) must stay.
- Line 482, 2026-08-22 latency measurements (~1,008 B) and lines 489-490, 2026-08-22 Railway cost figures: dated; Railway is stopped.
- Line 235: "current working provider ... `LLM_PROVIDER=nim`" is dated (CLAUDE.md says `openrouter` is live).

## 9. Approval checklist (block by block)

Owner marks each line; nothing runs until these are decided.

- [ ] 17 blocks in section 2 marked MIXED / ARCHIVE: approve the verdict per block (default: as proposed).
- [ ] Extracts X1-X39: keep, drop or edit each (default: keep all).
- [ ] Section 4 "not extracted" list: overrule any item.
- [ ] Section 6 items 1-5: decide, separately from the move.
- [ ] 7.3 CLAUDE.md wording.
- [ ] Then, in one pass: build archive (7.1), edit AGENTS.md (7.2), edit CLAUDE.md (7.3), append archive README row, re-run `grep -c` checks: every X-quote must still be an exact substring of the new AGENTS.md, and every original `##`/`###` heading must exist in AGENTS.md or in the archive.
- [ ] Commit only when the owner asks.

## 10. Post-move verification (to run after approval)

1. Every extract X1-X39 is an exact substring of the new `AGENTS.md`.
2. Archive is byte-identical to the old lines 5-163: `diff <(sed -n '5,163p' <old copy>) <(tail -n +N archive)`.
3. Every heading in the old file appears in the new file or in the archive.
4. `cd backend && .venv/bin/pytest tests/test_repo_layout.py -q` (guards nothing here, but is the layout test that touches scripts/docs trees).
5. `git grep -n "AGENTS.md"` shows no reference to a section that exists in neither place.
