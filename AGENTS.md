# Agentic Lessons & Environment Context

> **Active operating status — reviewed 2026-10-22.** This file holds binding repository invariants. Dated session handoffs and lessons (Aug-Oct 2026) are archived verbatim in `docs/agent/claude-md-archive/AGENTS-handoffs-2026-10-22.md`; older ones in `docs/archive/agents-handoffs-2026.md`. For a conflict, current source configuration, scoped instructions, and approved runbooks prevail; dated measurements are provenance, not live state.

### Standing rules extracted from dated handoffs (2026-10-22)
Verbatim from the entries archived in `docs/agent/claude-md-archive/AGENTS-handoffs-2026-10-22.md`. Source heading and line are noted per item; counts and states inside them were true on their stated date, not necessarily now. For a conflict, code and scoped CLAUDE.md files prevail.

**X1** (from "Repository dead-code sweep + script-tree drift closure — Oct 22, 2026", was line 6)
- **Binding:** the `scripts/` ↔ `backend/scripts/` duplicate trees are now **fully reconciled and pinned**. Three duplicated paths outside `scripts/ops/` had drifted in both directions, and because `backend/docker-compose.yml` bind-mounts repo-root `scripts/` at `/app/scripts` (shadowing the image's baked `backend/scripts`), the **container ran the stale copies** while CI and the host ran the backend ones. Worst case: `scripts/verify_rls_policies.py` was missing the `canonical_memories` RLS probe — a **security control** silently skipping the most sensitive table. All shared paths are byte-identical now, and `backend/tests/test_repo_layout.py::test_cross_tree_shared_scripts_are_identical` pins every one of them. **Any new script duplicated across the two trees must be added byte-identical in both, or not duplicated at all.**

**X2** (from "Repository dead-code sweep + script-tree drift closure — Oct 22, 2026", was line 7)
- **Binding:** `backend/scripts/` holds the canonical content for every shared path. The single intentional exception is `eval/run_ragas_eval.py` (root = standalone RAGAS runner, tested by `tests/test_ragas_claim_ledger.py`; backend = older golden-set harness) — it is declared in `_DIFFERENT_TOOLS` and asserted to **stay** distinct.

**X3** (from "Repository dead-code sweep + script-tree drift closure — Oct 22, 2026", was line 9)
- **What was deliberately NOT removed (owner decisions):** `memory/okf/staging/` (820 entries — read by the admin review queue; the `_excluded_parts` filter in `services/memory/okf_store.py` is the release-critical gate), `memory/okf/compiled.json` (10.4 MB tracked artifact — read at runtime), `docs/production-readiness/` raw captures (governance register classifies it append-only historical), `.agent/` vs `.agents/` skill trees (each serves a different harness), and `backend/scripts/eval/run_ragas_eval.py` (a planning note still targets it).

**X4** (from "Repository dead-code sweep + script-tree drift closure — Oct 22, 2026", was line 10)
- **How to verify a file is dead:** resolved-import check only — `ast.parse` for Python, import-specifier resolution for TypeScript. A name grep is not evidence: `form` matches `chat.py`, `security` matches every skill doc, and a doc mention is a reference to *update*, not a reason to keep the file. **Rule:** prove no import resolves to it before deleting it.

**X5** (from "First-person v10 public-release remediation — Phase 0/1 done, Phase 2+ not started — Oct 21, 2026", was line 14)
- **Binding:** the public-release verdict is **NO-GO** and unchanged. `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` **and** inside the container (re-verified at Phase 0). Do not enable it until B1–B7 in `docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md` are closed and recorded.

**X6** (from "First-person v10 — the three evidence defects fixed + owner-only preview live in Docker — Oct 22, 2026", was line 24)
- **Binding:** the public-release verdict is **NO-GO and unchanged**. `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false` in `backend/.env` **and** in the container; the public `first_person` alias still points at `first_person_v10` (4,197 points); **no Qdrant write, no alias change, no Redis mutation, no deployment, no Railway action.** The local-review flag (`FIRST_PERSON_LOCAL_REVIEW_ENABLED`) is the only first-person flag that is on, and only in the local container.

**X7** (from "First-person v10 — the three evidence defects fixed + owner-only preview live in Docker — Oct 22, 2026", was line 25)
Schema is now `first-person-speaker-conflict-v2`: `audio_duration_ms` is **removed** (never repurposed) and replaced by `audio_file_duration_ms` + `audio_slice_duration_ms` + `audio_start_ms` + `audio_end_ms`.

**X8** (from "First-person v10 — the three evidence defects fixed + owner-only preview live in Docker — Oct 22, 2026", was line 26)
`(video_id, guru_id)` is **not** an identity.

**X9** (from "First-person v10 — the three evidence defects fixed + owner-only preview live in Docker — Oct 22, 2026", was line 27)
**No namespace fix was applied** — it would re-key the corpus and invalidate the 1,600 Phase-2 verdicts, the rights join and the pinned contract. The collision is **unresolved** and both members are quarantined in the new tier `deterministic_id_collision_quarantine`.

**X10** (from "First-person v10 — the three evidence defects fixed + owner-only preview live in Docker — Oct 22, 2026", was line 29)
Rebuild with `cd backend && FIRST_PERSON_LOCAL_REVIEW_ENABLED=true bash ../scripts/docker-safe.sh docker compose up -d --build --no-deps backend`.

**X11** (from "First-person v10 — the three evidence defects fixed + owner-only preview live in Docker — Oct 22, 2026", was line 30)
- **The label is now two canonical lines** — `REVIEW CANDIDATE — NOT PUBLIC RELEASE` and `AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION` — in the service, the route, the CLI, the contract, every citation and the owner guide. A contract pinning a different label is stale and the mode **refuses to start**.

**X12** (from "First-person v10 — Phase 4/5 done: independent rights register, corpus tiers, B4 isolation, owner-only test mode — Oct 22, 2026", was line 36)
It runs only when `FIRST_PERSON_LOCAL_REVIEW_ENABLED=true` **and** `IS_PRODUCTION=false`, refuses to start when any pinned artifact is missing or whose sha256 changed, and every response carries `"review candidate / not public release"`.

**X13** (from "First-person v10 — Phase 4/5 done: independent rights register, corpus tiers, B4 isolation, owner-only test mode — Oct 22, 2026", was line 37)
- **B4 is implemented and tested** (`backend/services/first_person_serving_contract.py` + `backend/config/first_person_serving_contract.json`): a legacy store may not point at an fp-context collection, a context store may not point at a legacy-only collection, the two may not share a collection, and the exact-cache fingerprint must carry `legacy_collection`, `legacy_schema`, `legacy_corpus_version` and `evidence_policy`. **Production raises at startup; outside production the legacy path fails closed by itself** (`abstain_reason=serving_contract_violation`) instead of taking the whole app down — do not "fix" that back into a startup raise. Adding the four fingerprint components invalidated the 24 h exact cache once, by design.

**X14** (from "First-person v10 — Phase 4/5 done: independent rights register, corpus tiers, B4 isolation, owner-only test mode — Oct 22, 2026", was line 38)
**B5 register exists but is NOT signed off.** `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json` (751 assets) is built from `docs/rights/CONTENT-RIGHTS.md`, never from a Qdrant payload field.

**X15** (from "First-person v10 — Phase 4/5 done: independent rights register, corpus tiers, B4 isolation, owner-only test mode — Oct 22, 2026", was line 39)
**The first tier is NOT "public verified":** its evidence policy is `automated_evidence_candidate`, and the 1,127 variants need a separate owner decision.

**X16** (from "First-person v10 — Phase 4/5 done: independent rights register, corpus tiers, B4 isolation, owner-only test mode — Oct 22, 2026", was line 40)
- **The 45 speaker-label conflicts are quarantined**, never relabelled: `audits/evidence/public_release_phase4_speaker_conflict_review_2026-10-22.md` is the human review packet (window, WAV sha256, YouTube link, scores, empty decision/reviewer/timestamp).

**X17** (from "First-person v10 — Phase 4/5 done: independent rights register, corpus tiers, B4 isolation, owner-only test mode — Oct 22, 2026", was line 42)
- **B4 gate scope:** the gate is armed for the **real** serving path (a real `FirstPersonStore`, or a store pointed at `first_person*` / `fp_context*`). A stand-in store in a unit test is not gated — the first, wider version turned 102 existing tests into `abstained / serving_contract_violation`.

**X18** (from "First-person v10 — Phase 2 (per-span ECAPA evidence) done; B1 measured — Oct 22, 2026", was line 50)
- **Binding for any future Phase-2 consumption:** the reference is built from the **two human-confirmed anchor moments** in `backend/scripts/ops/speaker_attribution.py::ANCHORS` (recomputed here with a **pinned** ECAPA revision — the repo's `speaker_attribution.py` loads the model *unpinned*, which breaks the HF-pin invariant), widened over train-split slices. Method constants (`ENROLL_MIN=0.75`, `ANCHOR_LABEL_MIN=0.55`, `ANCHOR_MARGIN=0.15`, `CLUSTER_DISTANCE=0.6`, 2 s window / 1 s hop) are **inherited unchanged** from that file and **not re-tuned** on this corpus. The expected guru of a span is the corpus assignment carried by the Phase-3 candidate — it is the **claim under test, never the evidence**; a span whose voice contradicts it is `refused_guru_mismatch` and is never verified.

**X19** (from "First-person v10 — Phase 2 (per-span ECAPA evidence) done; B1 measured — Oct 22, 2026", was line 51)
- **Honest limit (do not overstate):** the trial labels come from the same two anchors the references are widened from, so the measured FAR/FRR is a *relative* consistency measurement on held-out videos, **not** a human-certified false-accept rate. The repo has no filled human speaker-label sheet (`docs/attribution/*.csv` speaker columns are blank), so certification is a **B7** dependency. The margin gate also collapses to an ordering requirement (every held-out impostor margin is negative).

**X20** (from "First-person v10 — Phase 2 (per-span ECAPA evidence) done; B1 measured — Oct 22, 2026", was line 52)
`torch` and `scikit-learn` are already in `backend/requirements.lock`; `speechbrain` is **not** in the lock and is imported **lazily** inside the embedding function, so the app import graph and the test suite never depend on it. `backend/requirements.txt` / `requirements.lock` are **unchanged**; no lock regeneration, no runtime-image change, no service recreate. In-image execution needs its own approval plus `uv pip compile backend/requirements.txt --output-file backend/requirements.lock`.

**X21** (from "First-person v10 — Phase 3 (ASR coordinates + audio windows) candidate only — Oct 21, 2026", was line 59)
- **Binding for Phase 2:** slice ECAPA audio from `audio_archive/wavs/`, **never** from `<asr_root>/audio/` — 515 of 516 files in `mass_ingest_2026-10/audio/` are 86-byte WAV stubs with a correct declared duration and **no PCM data**. Use the candidate's rebuilt `[audio_start_ms, audio_end_ms]`, not the live payload's.

**X22** (from "First-person v10 — Phase 3 (ASR coordinates + audio windows) candidate only — Oct 21, 2026", was line 60)
- **Binding for any future candidate write:** the rebuilt corpus declares `corpus_version=fp-context-transcript-v2` because **502 of 1,600 candidate spans would collide with a live span id** under the live corpus version. Never repoint the `first_person` alias at a v2 collection while the speaker evidence is still open.

**X23** (from "First-person context harness — phases A/B/D landed, serving unwired — Oct 20, 2026", was line 77)
- **Prohibitions:** never default a missing `speaker_verified` to `true` (attribution without verification); never give the harness an LLM-authored sentence (its `answer_text` is exactly the stored span text, in order); `_serving_policy_fingerprint` already carries `context_harness`, `context_max_spans`, `context_selector` and `context_schema` (landed before wiring on 2026-10-20), so wiring must not remove them; without those entries a pre-harness answer replays for the 24 h exact-cache TTL.

**X24** (from "`first_person_mode` default corrected to `retrieval_only` — Oct 20, 2026", was line 81)
- **Binding:** the code default is `retrieval_only` (was `hybrid` since 2026-10-11 while its own comment and `services/first_person_release.py` both said `retrieval_only`). `hybrid` is now an explicit owner opt-in: set `FIRST_PERSON_MODE=hybrid` and expect LLM-authored opening/connective/question prose. Production still accepts **only** `retrieval_only`.

**X25** (from "Local first-person serving pointer + answer-quality measurement — Oct 19, 2026", was line 86)
The switch is the `FIRST_PERSON_COLLECTION` env value in the **project** `.env` — `backend/.env` for this stack, not the repo-root `.env` — applied with `docker compose up -d --no-deps --force-recreate backend` (`restart` never rereads `env_file`).

**X26** (from "Local first-person serving pointer + answer-quality measurement — Oct 19, 2026", was line 88)
`first_person_bridge` declines a clip at `_DISTRESS_DECLINE_LEVEL = 2` (MODERATE; deliberate 2026-10-05 fix), the graph then routes `intent=DISTRESS`, and the seeker gets scripted compassion boilerplate instead of the teacher's clip.

**X27** (from "Local first-person serving pointer + answer-quality measurement — Oct 19, 2026", was line 88)
Router margin data: DISTRESS embedding route threshold 0.66 → 32/150 on-topic hijacks; 0.72 → 10; but at **0.74+** `"I am suicidal"` stops matching the router (still caught by the guardrail `self_harm` rail and `assess_distress`). Do not tune this boundary without a clinician-review pass.

**X28** (from "Local first-person serving pointer + answer-quality measurement — Oct 19, 2026", was line 89)
Per `L-OPS-MOUNT-1`, `backend/scripts/` is NOT bind-mounted into the container, so anything needing `docker exec` must live in repo-root `scripts/ops/`.

**X29** (from "Local first-person serving pointer + answer-quality measurement — Oct 19, 2026", was line 90)
`/api/chat` is rate-limited to **20/min** (batch sweeps must throttle and retry on 429)

**X30** (from "First-Person Pipeline Quality Breakthrough — Oct 11, 2026", was line 94)
Per binding `L-FP-HYBRID-SCAFFOLD-1`, a gateless run cannot speak to answerability.

**X31** (from "First-Person Pipeline Quality Breakthrough — Oct 11, 2026", was line 96)
`"shared in <channel>"` is the intended label for unverified speakers; the fix belongs at ingest via speaker verification, never via ID-to-name mapping. Head `86cc77f6` implements that lane (`backend/ingest/verbatim/speaker_verify.py`, `speaker_verified` plumbing, 15 tests). Displayed speaker stays as-verified until then.

**X32** (from "Corpus ingestion handoff — Aug 27, 2026", was line 117)
- **Staleness invariant**: `PRE_EXTRACTED_MAX_AGE_SKIP=30 days`. Always `touch` projected transcripts before running ingestion or they will be skipped and fall back to live YouTube API.

**X33** (from "Corpus ingestion handoff — Aug 27, 2026", was line 118)
- **LLM provider for ingestion**: Use `OpenRouterService` (cloud-only mode, `OLLAMA_CLOUD_ONLY=true`). `bulk_ingest_video.py` was fixed from `OllamaService` → `OpenRouterService`. `LLM_PROVIDER=openrouter` env required.

**X34** (from "Fresh Railway handoff — Aug 23, 2026 post-audit correction", was line 145)
- Grounded partials are deterministic source excerpts only: maximum two excerpts of 360 characters, absolute URLs, `verification.method=grounded_partial_evidence`, `partial=true`, `verification.passed=false`, and `faithfulness_score=0.0`. They are not verified generated teachings.

**X35** (from "Fresh Railway handoff — Aug 23, 2026 post-audit correction", was line 146)
- Partial evidence may be written only to exact/hot scoped caches. Semantic/vector writes are forbidden until those tiers gain fresh evidence, source-version, and support gates. Never use a global Redis flush to address this policy.

**X36** (from "Fresh Railway handoff — Aug 23, 2026 post-audit correction", was line 147)
Direct fetch-stream reconnect/resume remains unimplemented or unproven; do not generalize queued replay to direct streaming.

**X37** (from "Fresh Railway handoff — Aug 23, 2026 post-audit correction", was line 150)
- Curated `/app/memory/okf/compiled.json` and `/app/data/doctrine_lexicon.json` remain absent. Do not manufacture placeholders, activate ONNX/RRF/DBSF, mutate Neo4j schema, widen graph concurrency, or modify `scripts/ingestion/corpus/` without approved audited artifacts and held-out evidence.

**X38** (from "Localhost safety-order handoff — Aug 23, 2026", was line 159)
- The default pipeline now runs `InputGuardrailStage` before `CircuitBreakerStage`. This is required so deterministic acute self-harm and other input safety decisions are not bypassed when an LLM provider circuit is open. The change is limited to `backend/app/pipeline/stages/pipeline_builder.py` and is covered by an explicit stage-order regression.

**X39** (from "Localhost safety-order handoff — Aug 23, 2026", was line 160)
- Provider distress-classifier failures remain indeterminate and do not invoke degraded intent classification. An unblocked `ERROR` or `TIMEOUT` maps to public `grounding_state=system_error`, not `abstained` or `safety_redirect`.

### First-person serving invariants — Oct 27, 2026
These are **binding** for every first-person serving path. Violation is a P0 bug. Lessons:
`L-UI-LABEL-IN-BODY-1`, `L-PLAN-DONE-IS-NOT-DONE-1` in `lessons.md`.

1. **Answer text is evidence, directness is metadata.** A served clip's `answer` / `teaching` body is the verbatim quote plus its speaker/source attribution — nothing else. "Related, not a direct answer" is a UI affordance carried by `status="weak_match"`, `is_direct_answer=False`, and `verification["direct"]=False` (the frontend already renders it from `verification.direct`, `src/components/chat/ChatMessage.tsx`). Never prepend a heading to a verbatim quote; where a heading must be carried (the bridge abstain path), it lives in `route_metadata.related_clips_heading`.
2. **`first_person_primary_mode` is the master posture switch; `first_person_serve_weak_match` is the finer knob under it.** Both default `True`. Neither weakens a gate (relevance minimum, integrity, boundary, output rail). A served first-person response carries `route_metadata.fp_served=True`; abstain/crisis/error results never do.
3. **The two context-expansion features are additive and off by default.** `first_person_enrichment_window_enabled` re-hydrates a retrieved parent to its full span set so an antecedent is visible; `first_person_graph_expansion_enabled` appends a concept-filtered retrieval **after** the vector results. Neither may reorder, drop, or replace a primary context, and neither may introduce generation — `retrieval_only` (X24) still forbids LLM-authored teaching prose.
4. **The fp-context enrichment window is not `get_neighbor_chunks`.** `services/qdrant/neighbor.py` keys on `source_url + chunk_index` and cannot see `fp-context-v1` `parent_unit_id` spans. The first-person path uses `FirstPersonContextStore.enrich_to_parent_window`; the general RAG path uses `get_neighbor_chunks` (`rag/nodes/reranking.py:549`).

### Ingestion Safety Invariants — Aug 28, 2026
These are **binding repository invariants** for all LLM-to-Qdrant persistence paths. Violation is a P0 bug. Full reference: `backend/docs/INGESTION_SAFETY.md`. Lessons: `L-INGEST-1`, `L-INGEST-2`, `L-INGEST-3` in `lessons.md`.

1. **Every LLM `.generate()` output reaching Qdrant MUST pass `find_artifact()`** (from `services.text_quality_filter`). This includes: chunk text, topic labels, RAPTOR summaries, context headers (`[Context: ...]`), potential questions, and OKF entries. `find_artifact()` catches three contamination vectors: (a) CoT reasoning leaks from Sarvam-105b / DeepSeek-R1, (b) provider graceful-degradation canned strings from OpenRouter / NIM, (c) ASR decoder loops. Adding a new LLM call site in `backend/ingest/` or `backend/services/` that writes to Qdrant without this gate is a P0 bug.

2. **Provider graceful-degradation returns content, not exceptions** — `OpenRouterService._graceful_degradation()` and `NimService._graceful_degradation()` return "I'm currently experiencing a temporary connection issue..." instead of raising. Correct for live chat, catastrophic for ingestion. As of Aug 28, `is_graceful_degradation()` is wired into `find_artifact()` itself, so all callers of `find_artifact` / `is_clean` / `select_clean` automatically catch it.

3. **Every idempotency checkpoint MUST cross-validate against actual data store state.** Three independent layers exist: (a) Redis `IngestionCheckpoint` (URL-keyed + content-hash-keyed), (b) local `ingestion_state.json` (`contextual_reingest.py`). After wiping Qdrant/Neo4j, you MUST clear ALL checkpoint layers or the survivor will silently short-circuit with phantom `{"status": "success", "chunks_indexed": 0}`. `contextual_reingest.py` now auto-detects stale state by cross-checking Qdrant `points_count`.

4. **OKF Scaffolding & Graceful Fallback**: The Ontological Knowledge Framework (`memory/okf/compiled.json`) represents curated offline extraction subject to human review. When `compiled.json` is absent, runtime retrieval gracefully falls back to Qdrant dense vector search and Neo4j relational traversal without fabricating uncompiled doctrine.

### Fresh audit invariants — Aug 21, 2026
- The standard graph can terminate at `handle_fallback` after CRAG rewrite exhaustion, bypassing `generate_answer`, `format_final_answer`, and their quality-gated fallback logic. For bounded product cases, inspect `route_after_grading` and terminal nodes; `final_answer` plus reducer-preserved citations and `verification=null` is the diagnostic signature.
- The only terminal comparative exception currently permitted is the narrow meditation-versus-contemplation request. It returns a clearly labelled general distinction with `verification.method=limited_comparison_fallback`, zero citations, and `grounding_state=abstained`; it must not be presented as a corpus teaching.
- Production smoke requests must obtain a signed token from `POST /api/auth/anon-session` and send the token itself in the POST `session_id` field or the route-specific session header. The derived `anon:<id>` identity is server output, never a client credential.
- Pure greeting short-circuits may use deterministic localized phrases for supported Indic locales, but this optimization is limited to `_GREETING_RE` matches. Substantive responses always use the normal safety, retrieval, generation, and translation pipeline.
- Browser-facing SSE metadata is a public projection. Provenance fields must pass through an explicit allowlist; never stream `memory_context`, `attachment_context`, prompts, safety state, raw graph state, or arbitrary future state fields.
- The historical production baseline remains a known risk: simple English 14.67s pipeline latency, comparative English 31.39s with honest zero-source abstention, and Hindi 19.90s. Newer warm controls improved some paths, but do not claim that long-tail latency or refusal quality is solved until a held-out benchmark improves these classes.
- Local validation in the sandbox is dependency-limited: do not install packages. `py_compile`, the regex safety gate, `git diff --check`, and the corpus guard are valid local gates; `pytest` and dependency-complete tests must run in CI or the production/test image.

## Deployment Readiness Checklist (Jul 19 to Aug 10, 2026) — archived

The July/August completion checklists, audit-remediation logs and local-dev caveats moved to `docs/agent/claude-md-archive/agents-md-deployment-readiness-2026-07.md`. One binding rule that lived inside it is kept here verbatim:

- **Aug 21 rotation invariants:** Second Brain persistence timestamps use PostgreSQL-compatible timezone-aware ISO-8601 values at the write boundary and normalize both ISO and legacy numeric forms on reads. BRAIN_KEK rotation is a staged transaction: take a read-only backup/snapshot, dry-run and CAS-verify every Mode-A row, apply only after explicit authorization, set the replacement on backend and worker, clear BRAIN_KEK_NEXT in service and shared scopes, explicitly redeploy both processes, and verify an authenticated vault unlock. Key material must never be printed, committed, or left in shell history; padded and unpadded base64url inputs are accepted but operational generation should use padded output.

### Security Invariants (as of Aug 1, 2026)
- **nginx `/ui`**: IP-restricted. Only RFC1918 + 127.0.0.1 allowed. Never remove the `deny all` without adding explicit IP allowlist.
- **CSP domains**: Every third-party domain in CSP must have a comment naming what it is and who owns it. Unattributed domains get removed.
- **CSP embeds (A30, 2026-10-19)**: An allowlist that admits a thumbnail but not its player is an oversight, not a policy. `img-src` allowed `img.youtube.com` while `frame-src` omitted `youtube.com`, so `nginx.conf` blocked **every** discourse-clip and meditation embed — the player rendered a black box that still claimed to be `Playing …`. `frame-src` now carries `www.youtube.com` + `www.youtube-nocookie.com` (commented). **Editing `nginx.conf` does not change the header the running container serves — it takes effect only on a frontend image rebuild.** When adding any embedded player, add its frame origin in the same edit as its thumbnail origin. And never infer playback success from "the iframe mounted": a frame refused by CSP/offline posts **no** `onError` at all, so observation needs both YouTube's postMessage codes and a bounded no-sign-of-life timer (see `src/hooks/useYouTubeEmbedError.ts`, `L-A30-EMBED-FALLBACK-1`).
- **Bandit**: Must NOT run with `|| true`. Add known FPs to `backend/.bandit` with justification comments.
- **Docker Compose env self-reference**: Never `${VAR}` in an `environment:` block if `VAR` is also defined in the same block. Use literal values or host env.
- **`The_Four_Sacred_Secrets.pdf`**: Removed from git history 2026-08-01. Do not re-add. Embeddings derived from this book may still be in Qdrant — rights basis unconfirmed. See `CONTENT-RIGHTS.md`.
- **git-filter-repo**: Answer `N` to "treat as continuation" prompt for a fresh rewrite. Re-add `origin` remote manually after run.
- **HF model pins**: Every `from_pretrained`/`snapshot_download`/`SentenceTransformer`/`CrossEncoder`/`BGEM3FlagModel` load MUST pass a pinned commit SHA (resolved from the HF API; comment "resolved 2026-08-01; do not bump to a repo head"). Registry: `backend/scripts/download_models.py::_MODEL_REVISIONS`. `BGEM3FlagModel` has no `revision=` kwarg — load from a pinned local `snapshot_download` dir. Any new model added to the repo gets a SHA in `_MODEL_REVISIONS` first. Never add a mutable repo-head load.
- **ONNX model pins (encoder + reranker)**: ONNX snapshot loads (`embedding_service.py::_load_onnx_encoder`, `services/onnx_reranker.py::_load`) MUST pass `snapshot_download(revision=<pinned SHA>)`. `HF_REVISION` (the env override for the ONNX encoder) MUST be a full 40-hex commit SHA (`^[0-9a-f]{40}$`) — reject missing or non-40-hex/mutable values before loading (fail-closed, never a repo head); `_load_onnx_encoder` validates and raises. Code constants `_ONNX_ENCODER_REVISION`/`_ONNX_RERANKER_REVISION` are themselves full SHAs. ONNX artifacts are pre-baked into offline images by `backend/scripts/download_models.py` (temsa reranker pinned in `_MODEL_REVISIONS` at `59d3305e...`; snapshot lands under `HF_HOME/hub/models--<org>--<model>` so the runtime cache lookup hits without network).
 - **Credentialed HTTP clients**: Any urllib/httpx client sending a key must validate scheme (`https`) + expected hostname, and refuse to follow 3xx redirects (`HTTPRedirectHandler` override) — see `backend/scripts/verify_sarvam.py`.
 - **Sarvam gateway keyed traffic** (Aug 11, 2026): `sarvam_http.py::_validate_base_url` sends `api-subscription-key` ONLY to https + `_SARVAM_ALLOWED_HOSTS = {api.sarvam.ai}`; an unallowlisted host (self-hosted E2E 30b endpoint) is accepted only when NO key is set; client uses `follow_redirects=False`. Key rotation takes an excluded-index set and returns None only when ALL keys are exhausted.
 - **Client-supplied assistant config vs shared caches** (Aug 11, 2026): `PipelineContext.assistant_config_present` bypasses shared cache read/write; coalesce key carries a bounded SHA-256 fingerprint (`_assistant_config_fingerprint`, M3 auth gate: system_prompt only for authenticated users); raw prompt text NEVER enters keys.
 - **`FORWARDED_ALLOW_IPS` gate**: `start_railway.py` requires an explicit non-wildcard allowlist (`app.config.settings.forwarded_allow_ips`) and exits at startup when missing or `"*"`. Docker compose runs plain uvicorn (`backend/Dockerfile` CMD) — unaffected. Railway is currently **paused**; set `FORWARDED_ALLOW_IPS` (e.g. `10.0.0.0/8`) before the next Railway deploy.

This file serves as a knowledge base for AI agents interacting with this workspace.


## Plan & Review
### Before starting work
- **CRITICAL: First read `lessons.md`** — search for keywords matching the task scope. Existing lessons contain fixes for repeated regressions (Serene Mind double-wrap, telemetry blocking, Lovable key hard-dependency). Reading first prevents re-debugging known issues.
- Always in plan mode to make a plan.
- After getting the plan, write the plan to `.claude/tasks/TASK_NAME.md`.
- The plan should be a detailed implementation plan with the reasoning behind it, and tasks broken down.
- If the task requires external knowledge or certain packages, research to get the latest knowledge (using appropriate tools).
- Don't over-plan: always think MVP.
- Once you write the plan, ask the user to review it. Do NOT continue until the user approves the plan.
### While implementing
- Update the plan file as you work.
- After completing tasks in the plan, update and append detailed descriptions of the changes you made, so following tasks can be easily handed over to other engineers.

## Docker Execution on Host
- **Docker Path**: The Docker binary is not in the default `/usr/local/bin` or `/opt/homebrew/bin`. It is located at `/Users/harshodaikolluru/.docker/bin/docker`.
- **Command Prefix & Makefile Usage**: Whenever executing `docker` or `docker compose` commands, agents MUST explicitly set the PATH or use the absolute path. Alternatively, and preferably, use the workspace `Makefile` commands which automatically configure the correct PATH.
  - **Preferred (Makefile)**: `make docker-rebuild-web` (to rebuild and restart frontend and backend services without data loss or volume purges).
  - **Other Makefile commands**: `make docker-up` (start full stack), `make docker-down` (stop full stack), `make logs` (view logs).
  - **Raw Command Example**: `export PATH="/Users/harshodaikolluru/.docker/bin:$PATH" && docker compose up -d --build backend frontend`
- Failure to do this will result in "unexpected user interaction type: not permission" errors from the agent runner, or `command not found: docker` errors in standard shells.
- **Keychain Credentials Error (-25293) & .docker_clean**: If Docker image pulls/builds fail on macOS with keychain credential errors (e.g., `-25293`), we bypass this by pointing `DOCKER_CONFIG` to a clean folder `.docker_clean/` with a custom `config.json` containing `"credsStore": ""`.
  - **CLI Plugins & Contexts Symlinks**: When overriding `DOCKER_CONFIG`, Docker hides the host's plugins and context directories. To prevent errors like `unknown shorthand flag: 'd' in -d`, you MUST symlink the host's `cli-plugins` and `contexts` into the clean directory:
    ```bash
    ln -s /Users/harshodaikolluru/.docker/cli-plugins .docker_clean/cli-plugins
    ln -s /Users/harshodaikolluru/.docker/contexts .docker_clean/contexts
    ```



## Supabase
- The application stack relies on Supabase for auth and persistence.
- **Local Supabase**: Can be run via `npx supabase start`, but requires the Docker path to be properly mapped if executed programmatically.
- **Google OAuth (Local)**: To test Google Sign-in locally, set `VITE_USE_NATIVE_OAUTH=true` in `.env.local` and ensure `supabase/config.toml` has valid Google credentials. Restart the stack with `npx supabase stop` and `npx supabase start` after changes.
- **Environment Variable Binding**: Missing `SUPABASE_URL` and `SUPABASE_KEY` must be populated in `backend/.env` for Docker builds.
- **Benchmark Auth Backdoor (local only)**: The `X-Test-Key` header is accepted only when ALL THREE conditions are met:
  1. `IS_PRODUCTION=false` (or unset)
  2. `ENABLE_TEST_AUTH=true`
  3. `BENCHMARK_SECRET` is set (non-empty)
  The `X-Test-Key` value must match `BENCHMARK_SECRET`. Without these, `ruthless_benchmark.py` and manual `curl -H X-Test-Key` will receive 401. Never enable this in production.

## Local Benchmarking
- After setting the auth backdoor vars above, run from `backend`:
  ```bash
  JWT_SECRET=$(grep '^JWT_SECRET=' .env | cut -d= -f2- | tr -d '\n\r')
  BENCHMARK_SECRET=$(grep '^BENCHMARK_SECRET=' .env | cut -d= -f2- | tr -d '\n\r')
  .venv/bin/python -u benchmarks/ruthless_benchmark.py --endpoint http://localhost:8000 --test-key "${BENCHMARK_SECRET:-$JWT_SECRET}" --concurrency 2
  ```
- The current working provider for low-latency local runs is `LLM_PROVIDER=nim`. Sarvam and OpenRouter keys are present as fallbacks.


## Cache Management & Ingestion Isolation
- `REDIS_CACHE_MAX_KEYS` applies only to exact-query keys matching `mukthiguru:cache:*`; never apply it to queues, sessions, quotas, telemetry, rate limits, or Second Brain namespaces.
- Cache telemetry uses fixed namespace labels and bounded SCAN sampling. `REDIS_CACHE_MAX_KEYS=0` is the explicit backward-compatible disable value. Existing keys must remain refreshable when the ceiling is reached.
- Never run global `FLUSHALL` for routine query-cache maintenance. Use the targeted Qdrant/Redis namespace procedure in the production readiness runbook, then verify preserved queue, session, quota, telemetry, and memory namespaces.
- Celery workers accept only the allowlisted queues `ingestion`, `embedding`, `indexing`, `okf`, and `memory`; `CELERY_QUEUES` and `CELERY_CONCURRENCY` are validated at startup. Do not remove `memory` or change concurrency until queue throughput and user-memory SLA are measured.

- **Query-Side Caches (GPTCache & Redis)**: The application uses GPTCache (for semantic caching) and Redis (for response caching) to optimize frontend query latency.
- **In-Memory Cache Flushing**: Caches can be flushed safely at any time using:
  - **Preferred (Makefile)**: `make flush-cache` (executes `python3 scripts/ops/flush_cache.py`, which scans and deletes only query-cache namespaces; it never runs `redis-cli flushall`).
- **Ingestion Pipeline Isolation**: Flushing these query-side caches has **zero** impact on the active or pending ingestion processes. Ingestion is an ETL pipeline that writes exclusively to Qdrant and Neo4j and maintains its own resumption checkpoints in `scripts/ingestion_state.json`. Agents can confidently assure the user that cache flushing is fully isolated and safe to execute.

## Non-Interactive Shell Commands
**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

## Troubleshooting Guidelines for Agents

### React Component Crashing
- **Symptom**: Frontend serves HTTP 200 but renders a blank page, and console shows `ReferenceError: [FunctionName] is not defined`.
- **Action**: When modifying React components, ensure all referenced functions in event handlers (e.g. `onClick={handleSignOut}`) exist in the component scope. If undefined, it will throw a `ReferenceError` during render and unmount the entire app.

### Code-Review-Graph MCP "Context Canceled"
- **Symptom**: `code-review-graph: INFO Starting MCP server 'code-review-graph' with transport 'stdio' : context canceled`
- **Action**: This is normal behavior when the IDE restarts or the agent session ends. Do **NOT** try to "fix" the MCP server code. If it fails to start entirely, verify `mcp_config.json` is valid JSON and points to `.venv/bin/code-review-graph`.

### "Connection issue" chat responses that are actually retrieval failures
- **Symptom**: `/api/health` reports `ready: true`, but chat answers come back as a generic "I'm experiencing a temporary connection issue" instead of doctrine, and Railway logs show `Qdrant dense search failed ... Vector dimension error`.
- **Action**: This is the 2026-07-16 embedding-dimension incident — see root `CLAUDE.md`'s "Embedding dimension contract" section for the full invariant, fix locations, and still-open items (Docker model pre-caching, OpenRouter→NIM failover). Don't re-diagnose from scratch; verify the fix is still in place in `embedding_service.py`/`qdrant/client.py` first.

## Post-Change Documentation Checklist
Agents MUST update the following documentation after completing a fix, feature, or architectural change:
- [ ] **lessons.md**: Document the specific implementation pattern, architectural decision, or "lesson learned".
- [ ] **README.md**: If a new service, route, or environment variable is added, update the README to reflect these changes.
- [ ] **docs/PRODUCT_OPPORTUNITIES.md** (Roadmap section): Mark items as complete or add new technical debt discovered during the change.
- [ ] **docs/DEVELOPER_GUIDE.md**: Update if the onboarding or development workflow has changed.
- [ ] **CLAUDE.md**: Update structural directory map, commands, or URL matrix.
- [ ] **AGENTS.md**: Update agent context, checklist, or guidelines if necessary.

## Session Completion
**When ending a work session**, present the final changes and run validation. Commits and pushing are optional and should only be performed if explicitly approved by the user.

**WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update Documentation** - Perform updates using the Post-Change Documentation Checklist, requiring applicable documentation updates when markdown files change
4. **Hand off** - Provide context for next session
## Agent Technical Skills
- **Pre-Compiled Technical Skills**: There are 15 pre-compiled agent skills containing structured summaries, patterns, and cheatsheets from technical books. They are located locally under `.agents/skills/<slug>` and mirrored globally at `~/.config/agents/skills/<slug>`.
- **How to Use**: Agents MUST read the `skill.md` file in these directories to load the core frameworks, or query the specific chapter files (e.g. `chapters/ch01-...`) for deep-dive technical context on topics like LangChain, LangGraph, RAG, System Design, or Database Internals.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

## Local Codebase Intelligence & Memory MCP Layer

In addition to `code-review-graph`, this workspace is integrated with four dedicated local/global MCP servers and plugins:
1. **Graphify**: Offline AST codebase graph tool (provides `code-review-graph` MCP tools).
2. **Claude-Mem**: Long-term episodic/semantic memory worker (SQLite + ChromaDB).
3. **CodeGraph**: AST query engine using WASM-compiled tree-sitter grammars.
4. **Understand Anything**: Multi-agent codebase knowledge graph builder and visualizer.

- **Auto-Sync Hook**: A post-commit hook at `.git/hooks/post-commit` automatically runs `node scripts/ops/update-understand-graph.cjs` in the background on every commit to keep the graph (`.understand-anything/knowledge-graph.json`) fresh.
- **Manual Sync**: Run `node scripts/ops/update-understand-graph.cjs` to force sync the graph.

### Strict Environment Constraints
- **Node.js v22 LTS Only**: Do **NOT** upgrade Node.js to Node `25.x` or run CodeGraph commands under Node 25. Node 25 has a critical WASM compiler Zone allocation bug that causes out-of-memory crashes (`Zone allocation constraints`) during tree-sitter compilation. Always keep the shell environment linked to Node 22 LTS (`/opt/homebrew/opt/node@22/bin`).
- **Bun Dependency for Claude-Mem**: Claude-Mem's background worker service runs on Bun for high-performance sqlite bindings. Ensure `bun` is available at `/opt/homebrew/bin/bun`.
- **Git Worktree Cleanup**: In agentic sessions, temporary git worktrees (`.claude/worktrees/agent-*`) can accumulate. This causes severe local git indexing lag. You **MUST** run `git worktree prune` and explicitly delete any temporary worktrees you created (`git worktree remove --force <path>`) before finishing your session.

### Utilizing Local MCP Tools
- **Explore first, grep last**: Use CodeGraph, Graphify, and Understand Anything rather than running heavy recursive glob/grep commands across thousands of files. It saves token costs, prevents host memory thrashing, and respects structural linkages.
- **Memory Recalls**: Leverage `claude-mem` to recall key patterns or historical insights across conversation checkpoints.

## Ponytail & Headroom Guidelines

### The Ladder (hard rule — runs BEFORE writing any code)
Before writing code, the agent stops at the first rung that holds:

1. Does this need to exist?   → no: skip it (YAGNI)
2. Already in this codebase?  → reuse it, don't rewrite
3. Stdlib does it?            → use it
4. Native platform feature?   → use it
5. Installed dependency?      → use it
6. One line?                  → one line
7. Only then: the minimum that works

The ladder runs after it understands the problem, not instead of it: it reads the code the change touches and traces the real flow before picking a rung. Lazy about the solution, never about reading.

Lazy, not negligent: trust-boundary validation, data-loss handling, security, and accessibility are never on the chopping block.

### Ponytail Principle
Keep implementations lightweight, minimal-diff, and simple:
- **Thin wrappers**: Prefer small, focused helper scripts or inline functions over heavy abstractions or new classes.
- **Self-Checks**: Python files should contain a runnable `if __name__ == "__main__":` block at the bottom for quick verification.
- **Optional/Stubbed Features**: Gracefully degrade or skip components if dependencies are not available on the runtime host.
- **LRU Cache Usage**: Use simple caching patterns (e.g. `lru_cache`) instead of custom state tracking classes where possible.

### Headroom Principle
Implement system configurations and runtime operations with safety margins (headroom):
- **Cost Steering**: Automatically steer LLM prompting towards brevity (`COST_STEERED_BREVITY_LIMIT` words) when context/history length is high to optimize token usage.
- **Reversible Context Compression (CCR)**: Allow the LLM to request full text for compressed text using `[RETRIEVE: <source_url>]` pattern; generation stage will intercept and swap the original text.
- **Timeout and Resource Headroom**: Always configure timeouts with safety margins (e.g. 120s timeouts for sequence calls, or 10% GPU/CUDA headroom) to avoid transient service lockups.

Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.

## Mobile App

- **Capacitor 8** wraps the Vite/React build for Android + iOS. Same codebase, no separate mobile repo.
- **Package id** `com.askmukthiguru.app`, display name `AskMukthiGuru`.
- **Router**: HashRouter on native, BrowserRouter on web — selected in `src/App.tsx` (BrowserRouter breaks in the Capacitor WebView because assets are served from `https://localhost/` with no server fallback).
- **Backend URL**: `src/lib/backendUrl.ts` forces Railway prod on native (`Capacitor.isNativePlatform()` check) because `window.location.hostname` is `localhost` inside the WebView and the prod-host regex would miss it.
- **Push (frontend)**: `src/components/common/PushNotificationsManager.tsx` — registers device token via `@capacitor/push-notifications`, sends to backend. `addListener` returns a Promise → use a `disposed` flag for race-safe cleanup.
- **Push (backend)**: `backend/app/api/push.py` (routes) + `backend/services/push_service.py` (FCM + APNs dispatch). Device tokens stored in `push_devices` table (migration `20260713000000_create_push_devices.sql`).
- **OAuth deep link**: scheme `com.askmukthiguru.app://auth-callback` — captured via `App.addListener('appUrlOpen')` in `src/App.tsx`. Android intent-filter + iOS CFBundleURLTypes wired by Capacitor config. Add this URL to Supabase Auth redirect URLs.
- **Storage**: `@capacitor/preferences` (SharedPreferences / NSUserDefaults) via a `SupportedStorage` adapter for supabase-js — `localStorage` is unreliable in the WebView.
- **Build cmd**: `npm run cap:sync` (vite build + cap sync). Native open: `npm run cap:open:android` / `cap:open:ios`.
- **Re-create native projects**: `rm -rf android ios && npx cap add android && npx cap add ios` — only when package id or Capacitor plugins change drastically. Discards native-side customizations.
- **Icons/splash**: `python3 scripts/ops/generate_mobile_assets.py` (regenerates from `public/icon-512.png`).
- **Store submission**: `docs/MOBILE_RELEASE_RUNBOOK.md` — full Play + App Store guide.
- **Store listing copy**: `docs/STORE_LISTING.md`.
- **Signing + push creds**: `CREDENTIALS_GUIDE.md` → "Mobile App Credentials" (keystore, `google-services.json`, APNs `.p8`, backend env: `FIREBASE_CREDENTIALS_JSON`, `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_KEY_PATH`, `APNS_KEY_PEM`, `APNS_BUNDLE_ID`).
- **Known TODOs**: ~~Apple Sign-In~~ ✅ implemented (native iOS, `AuthPage.tsx` — requires Supabase Apple provider config before submission). ~~Delete-account flow~~ ✅ implemented (`ProfilePage.tsx` + `delete-my-account` edge function).

## Multimodal Chat Upload Invariants (Aug 19, 2026)
- `POST /api/chat/upload` is ephemeral extraction only. Upload bytes must not enter corpus, Second Brain, Qdrant, or Neo4j without a separate explicit indexing flow and consent boundary.
- Per-file cap is 10 MB; combined cap is 50 MB; chat `attachment_context` is capped at 8,000 characters. Enforce declared-size and bounded-read checks before extractor work.
- MIME declarations are untrusted. Prefer magic-byte sniffing, sanitize filenames with `Path(name).name`, and return truthful metadata-only fallback when OCR/transcription/PDF extraction is unavailable.
- Attachment context is separate from `user_message` and `memory_context`; generation must label it as untrusted evidence and never follow instructions found inside it.
- Any cache or coalescer key for attachment-backed turns must bypass shared reuse or include a bounded content digest. Never include raw attachment text in keys.

Historical session handoffs (Jul–Aug 2026) live in docs/archive/agents-handoffs-2026.md; current state is in handoff.md and lessons.md.

## Railway Deployment (Production) — archived

- Railway is paused; it stays stopped until Harsha says otherwise. Before any deploy set `FORWARDED_ALLOW_IPS` (non-wildcard, e.g. `10.0.0.0/8`) or `start_railway.py` exits at startup.
- Deploy with `railway up` (tarball), **not** `railway redeploy --from-source` (hangs at INITIALIZING). Run 1 replica. `/api/health` is the readiness gate.
- Link/log/variables commands and the E2E-user and `start_railway.py` import notes: `docs/agent/claude-md-archive/agents-md-railway.md`.

## ONNX Reranker + ColBERT MaxSim (Jul 27, 2026) — archived

- `RERANKER_BACKEND=onnx_int8` is the default (rollback: `flagembedding`). ONNX ColBERT MaxSim is shipped but off (`ENABLE_COLBERT=true` to enable); keep RAGatouille in `requirements.txt` until its path is confirmed dead.
- Fixed bug: `_load_onnx_encoder` never set `self._encoder`, so every encode call re-downloaded the 570 MB model. Validation scripts and numbers: `docs/agent/claude-md-archive/agents-md-onnx-reranker.md`.

### Dependency Lock Authority and Clean Release Installs (Aug 13, 2026)

`backend/requirements.txt` is the human-maintained production input and
`backend/requirements.lock` is the committed, fully pinned release artifact.
Docker images and CI install the lock file only. After changing the input, run
from the repository root:

```bash
uv pip compile backend/requirements.txt --output-file backend/requirements.lock
git diff --check backend/requirements.txt backend/requirements.lock
```

The default backend profile deliberately keeps `numpy<2.0` for the tested
PyArrow stack. LettuceDetect is a disabled-by-default optional model profile in
`backend/requirements-optional-ml.txt`; do not enable it in production until its
NumPy 2.x compatibility has passed a separate staging test.

`package-lock.json` is the frontend lock authority; never use `npm install` in
CI or deployment. Clean release evidence must include `npm ci`, `npm test --
--run`, and `npm run build`. Backend clean-install evidence must use a fresh
Python 3.12 environment and `pip install -r backend/requirements.lock` before
running the backend suite. Do not claim a release is reproducible solely because
the existing development virtual environment passes tests.


## Active latency and quality invariants — 2026-08-22

The production latency pass introduced two safe hot-path rules. First, the bounded meditation-versus-contemplation answer may short-circuit only after input and distress guardrails, only for English, and only with explicit limited-support metadata, zero citations, and abstained grounding. Second, translation is a bounded dependency: query, history, and final-answer provider calls use `translation_timeout_s` (default 5 seconds) and fail open with native/original text rather than blocking the full chat pipeline. The English-with-Indic-preference case must not invoke translation at all; native and code-switched Indic input must retain translation and guardrail coverage.

The following changes remain evidence-gated and must not be activated from intuition or an aggregate average: `EMBEDDING_BACKEND=onnx_int8` for query/index migration, RRF/DBSF weights or prefetch multipliers, Neo4j schema mutations, and broad graph parallelization. Activation requires a held-out evaluation with per-query-class NDCG/recall/precision, answer faithfulness, citation correctness, abstention/false-refusal behavior, p95/p99 latency, timeout/error rate, tenant/rights isolation, and a documented rollback. Existing fp32 query/index compatibility, fusion configuration, Neo4j schema, graph caps, and fail-open behavior are the production defaults until those gates pass.

The 2026-08-22 production verification observed the bounded comparison at approximately 7 ms with a 367-character limited-support response and no citations. The active 8655709 runtime returned an English FAQ under Hindi preference in approximately 4.3 seconds and a native Hindi FAQ in approximately 4.0 seconds, while the benchmark matrix also captured a 10.8-second pipeline/13.8-second wall-clock Hindi run, so multilingual latency remains variable. The attempted 940eb55 translation-timeout rollout failed during `Initialization › Snapshot code` after 15 minutes; Build/Deploy never started, and Railway continued to show 8655709 as ACTIVE. Deep health reported `ready=true`, `status=healthy`, embedding dimension 1024, queue size 0, exact-cache keys 0, and healthy Qdrant, Redis, Neo4j, LLM, embedding, fast graph, and LightRAG checks. The translation-timeout code is production-active through the successful `806799d` rollout; continue to treat multilingual tail variance as an open performance risk.

The sandbox has no `pytest` or `pydantic-settings`. Do not install packages for a release check when the task forbids installation, and never represent static compilation or regex safety as a substitute for dependency-complete tests. The focused regression test is committed for execution in CI or the locked production test image.


## Cost-effectiveness invariants — Aug 22, 2026

- Current Railway workspace usage is $28.7854, with $27.0931 (94.1%) from memory, $1.3513 (4.7%) from CPU, $0.2645 (0.9%) from volume, and $0.0766 (0.3%) from egress. The $30 hard limit is nearly reached and the current estimate is $53.84. Memory reduction is the first cost target.
- The observed 30-minute memory averages were approximately 8.07 GB backend, 2.45 GB Neo4j, and 154 MB worker. Do not reduce worker concurrency without queue/SLA evidence.
- Graph parallelization overlaps vector and graph calls but does not automatically reduce billable work. Require graph-on/off cost-per-successful-answer, quality, timeout, p95/p99, and resource evidence before broadening it.
- OpenRouter provider-reported cost, known-rate estimates, and unknown costs must remain separate. The configured Gemini generation model is not covered by the fallback-rate table; missing provider cost must never silently aggregate as zero.
