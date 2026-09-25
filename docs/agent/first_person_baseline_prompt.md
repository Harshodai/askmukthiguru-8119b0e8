# AskMukthiGuru — Claude Code End-to-End Production Baseline Prompt

You are working on the AskMukthiGuru repository. Build a **production-safe first-person, verbatim-answer baseline** for Sri Preethaji and Sri Krishnaji teachings, while preserving the existing general MukthiGuru RAG/chat product.

The first-person answer must be a pointer to the teachers’ recorded words—not an LLM-invented quotation:

```text
user question
→ crisis/safety pre-check
→ exact-match cache where safe
→ first-person retrieval path
→ confidence/abstention decision
→ one to three source clips
→ verbatim/hash validation
→ timestamped citation and video playback
```

The product target is: **correct teacher, exact recorded words, exact timestamp, and honest confidence/coverage reporting**. Aim for 100% precision on the confident-answer subset so the system can eventually demonstrate at least 99% precision on that subset. Do not claim this target until it is proven with a non-circular, human-labelled evaluation set.

## Non-negotiable operating rules

1. **Data and measurement before feature work.** Do not add unrelated product features until the first-person data path has a reliable baseline.
2. **Read before writing.** Inspect the current implementation, tests, git status, active configuration, and relevant handoff documents before changing code.
3. **Use the shortest correct diff.** Reuse existing abstractions and tests wherever possible.
4. **Never claim a result without evidence.** Every final claim must be labelled `VERIFIED`, `PARTIAL`, or `UNVERIFIED`, with the command, count, report, or reason.
5. **Do not fabricate labels, quotes, timestamps, or speaker identity.** Human gold labels must come from human reviewers.
6. **Use dry-run → report → snapshot → explicit approval → apply** for every Qdrant, OKF, Neo4j, Memgraph, or other persistent-data write. Make all backfills idempotent.
7. **Do not commit or push unless explicitly asked.** Before every change, check `git status`; before every commit, check changed paths and shared-file mtimes.
8. **Never place large audio/model artifacts, `__pycache__`, credentials, or generated scratch data in the repository.** Use a scratchpad outside the repo.
9. **Keep the first-person route behind `FIRST_PERSON_MODE` or an equivalent feature flag.** Do not destabilize ordinary general-chat RAG.
10. **Crisis/safety detection remains in front of the first-person route.**
11. **Do not use the semantic cache as a correctness mechanism for first-person answers.** Initially bypass or disable semantic-cache reuse only for this specialized route; preserve ordinary chat semantic-cache behavior unless separately proven safe.
12. **The live production graph is currently documented as Neo4j, not Memgraph.** Do not assume Memgraph. Verify the actual topology before any graph migration or alias backfill.

## Read these files first

Read and reconcile the current versions of:

- `README.md`
- `CLAUDE.md`
- `backend/CLAUDE.md`
- `src/CLAUDE.md`
- `PLAN.md`
- `docs/END_TO_END_ARCHITECTURE.md`
- `docs/RAILWAY_GO_NO_GO_2026-09-15.md`
- `docs/RUTHLESS_AUDIT_2026-09-17.md`
- `docs/PRODUCTION_READINESS_CHECKLIST.md`
- `docs/DEPLOY_READINESS.md`
- `docs/ROLLBACK_PLAN.md`
- `docs/PENDING_AND_EDGE_CASES.md`
- `docs/agent/` if the first-person research report or baseline prompt already exists
- relevant lessons/handoff files if present

Verify the current repository state:

```bash
git status --short
git log -1 --format=fuller
find backend -maxdepth 3 -type f | sort
```

Do not trust a document if current source or live configuration contradicts it.

## Current repository architecture to preserve

The existing system is broader than this first-person feature:

- Frontend: React/TypeScript under `src/`.
- Backend API and orchestration: Python under `backend/`.
- Supabase/Postgres: identity-linked durable state, conversations, messages, memory, telemetry, and administrative data.
- Qdrant: primary hot-path vector retrieval, with dense/sparse/hybrid capabilities and metadata filters.
- Redis: caching, queues, coalescing, and operational coordination.
- Neo4j: graph access in the current documented/live architecture.
- LightRAG: ingestion/administrative/operational graph work; standard chat should not require a LightRAG call.
- External model/provider gateway: timeout, retry, circuit-breaker, and fallback boundaries.
- Existing ingestion, chunking, RAPTOR, quality gates, provenance, citation, memory, safety, evaluation, and observability subsystems.

The general chat flow remains conceptually:

```text
request
→ authentication/user/tenant resolution
→ crisis and request safety checks
→ routing and context budget
→ retrieval from Qdrant plus bounded optional graph context
→ context engineering
→ LLM gateway and generation
→ reflection/verification/fallback
→ citation extraction and formatting
→ output safety
→ streaming/final response
```

The first-person route is a specialized evidence-serving path and should not call the general generation pipeline unless a benchmark proves that a constrained LLM step materially improves quality without violating latency or verbatim guarantees.

## Current known defects to validate, not blindly assume

The attached audit found the following problems. Reproduce them against current code/data before fixing them:

- `backend/services/teacher_attribution.py` currently permits text mentions to influence teacher attribution.
- Current callers include `backend/ingest/pipeline.py`, `backend/ingest/contextual_reingest.py`, `backend/services/qdrant/indexer.py`, and `backend/services/intelligent_metadata_extractor.py`.
- `backend/tests/test_teacher_attribution.py` may not exist yet; create it if needed.
- `backend/scripts/ops/fix_teacher_tags.py` may not exist yet; create it if needed, following the existing backfill pattern.
- `backend/scripts/ops/backfill_qdrant_teacher_id.py` exists and is a useful pattern.
- The actual extractor path must be verified; do not assume `backend/scripts/ingestion/corpus/parallel_corpus_extractor.py` exists.
- `backend/app/schemas/__init__.py` contains the current `Citation`; add first-person fields compatibly rather than breaking ordinary citations.
- Frontend citation files are under `src/components/chat/CitationCard.tsx` and `src/components/chat/ChatMessage.tsx`.
- Existing tests include citation, Qdrant, ingestion, OKF, transcript-quality, benchmark, and security tests. Discover exact names before adding duplicates.
- Existing semantic-cache implementation and tests must not be removed globally without a separate migration decision.
- Existing repository production audits identify Railway OOM/crash/recovery and graph-topology blockers. The first-person work does not automatically clear them.

## Target first-person data model

Represent a served answer as a validated pointer, not free text:

```json
{
  "video_id": "...",
  "start_ms": 123000,
  "end_ms": 148000,
  "speaker": "preethaji|krishnaji|both|unknown",
  "transcript_hash": "...",
  "group_id": "...",
  "source_url": "...",
  "verbatim_text": "..."
}
```

Required invariants:

- The served span is an exact substring of the immutable verbatim transcript.
- The transcript hash matches the indexed source.
- `start_ms >= 0` and `end_ms > start_ms`.
- The timestamp is within the video duration when duration is known.
- The speaker is supported by source identity and/or verified voice evidence; text mentions alone never determine speaker.
- Host words are never presented as the teacher’s words.
- Summary-only records without a backing video are never served as first-person teaching.
- If confidence is below threshold, show the closest clip with the explicit label: **“Related, not a direct answer.”**
- Full teaching may return up to three clips, with no more than one clip per video, plus a full-video link.

## Execution phases

Execute phases sequentially. Stop and report after each phase. Do not proceed to the next phase until its gate passes or the user explicitly accepts a documented exception.

### B0 — Honest measurement and repository alignment

1. Build a current file/path map from source, not stale documents.
2. Implement or repair a benchmark harness so timeouts, 429s, empty answers, malformed results, and infrastructure errors count as system errors.
3. Add rate limiting, bounded retries, backoff, resumable checkpoints, and per-question status.
4. Run the current data-quality and benchmark tools against reachable local data.
5. Record baseline metrics twice when feasible; report exactly what is unavailable.
6. Confirm the actual Qdrant collection, payload schema, model/dimension configuration, and live graph topology.

Gate:

- Baseline is reproducible.
- Empty answers and timeouts are not silently counted as success.
- No persistent data is modified.
- Any unavailable dependency is recorded as `UNVERIFIED`.

### B1 — Human gold set and valid evaluation

Do not generate the gold set from the target corpus passages.

Create tooling for reviewers to label:

- answerable questions;
- near-miss questions;
- unanswerable questions;
- acceptable equivalent-teaching groups;
- exact verbatim text;
- speaker;
- word/timestamp boundaries;
- clip quality.

Target approximately 2,000 real/seeker-style questions over time, with an initial smaller pilot. Use two annotators where practical, define adjudication, and report agreement. Keep the existing generated golden set only as regression material, not proof of accuracy.

Gate:

- Review protocol is documented.
- Questions are not circularly generated from the answer passage.
- Held-out videos/questions exist for evaluation.
- Precision, coverage, abstention, strict top-1/top-3, group-level top-1/top-3, wrong-speaker rate, timestamp error, and verbatim mismatch rate are defined.

### P0 — Immediate live-harm controls

Before rebuilding stores:

1. Add a shared verbatim check for OKF extraction/loading.
2. Prevent fabricated quotes from entering staged OKF data or being served.
3. Identify video-less summary points and either quarantine or explicitly label them as non-first-person material.
4. Report counts before applying changes.
5. Add regression fixtures for each defect.

Do not silently delete data. Use dry-run, snapshot, approval, and idempotent application.

### T1 — Teacher attribution root fix

Modify the actual shared implementation in `backend/services/teacher_attribution.py`.

Required behavior:

- Primary teacher comes from trusted source identity/channel/video allowlist.
- Voice attribution may strengthen or correct identity when available.
- If no stronger evidence exists, use the approved source fallback.
- Text mentions produce `mentions:<teacher>` metadata only.
- Text mentions must never determine `teacher_id`, primary teacher, filtering, or citation identity.

Add or update tests so these words cannot create external attribution by themselves:

- `digital`
- `Mahishasura`
- `Krishnaji`
- `oneness`
- `deeksha`
- `grammar`
- `Isha`

Test that a Preethaji/Krishnaji source mentioning Sadhguru remains attributed to the source teacher while receiving a mention tag.

Run the attribution tests, cross-tenant leak probe, backfill-related tests, and every test importing the module.

Create a dry-run backfill script only if needed. It must:

- report every changed tag/teacher ID;
- support `--dry-run`;
- be idempotent;
- never write in dry-run mode;
- target the actual store and graph topology after verification;
- create a rollback/snapshot record.

### D1 — Transcription and clip-data bake-off in scratch space

Use eight representative videos or verified substitutes. Keep all files, audio, models, scratch corpora, and collections outside the repository and never write live Qdrant/OKF stores.

Compare the current baseline with candidate ASR/alignment pipelines only after verifying model availability, language support, compute feasibility, commercial licence, gated terms, and redistribution constraints.

Measure:

- word error rate where reference data exists;
- glossary-term hits;
- voice-activity hallucinations;
- real-time factor;
- word-level timing agreement;
- speaker attribution;
- content-word preservation;
- verbatim/display consistency;
- clip boundary accuracy;
- disk/RAM/CPU cost.

The preferred design may include:

```text
VAD
→ candidate ASR models
→ constrained word-level merge only among aligned alternatives
→ forced alignment
→ punctuation with zero-word-change assertion
→ speaker/voice verification
→ silence-snapped clip boundaries
→ immutable verbatim layer + derived display layer
```

Do not assume a specific model wins. Benchmark it. Do not use non-commercial components for a commercial deployment without explicit legal approval.

### D2 — Shared ingestion hardening

Implement every winning capability in the shared ingestion pipeline, not only in a one-off repair script.

Locate the actual current implementation before editing. Ensure every new video can produce:

- immutable verbatim transcript;
- derived display transcript;
- word timestamps and confidence where supported;
- speaker turns;
- source/voice teacher attribution;
- host/teacher turn separation;
- clip boundaries;
- transcript hash;
- verbatim-checked OKF extraction;
- per-video `quality_report.json`;
- quarantine status on failure;
- no Qdrant indexing when the gate fails.

Add an end-to-end scratch test using the real ingestion entry point and scratch corpus/Qdrant collection. Delete the scratch collection afterwards.

### D3 — Versioned store rebuild

Create a new versioned Qdrant collection rather than mutating the live collection in place.

The target index may contain:

- dense passage vectors;
- sparse passage vectors;
- a separate question vector/field containing the host question plus offline-generated candidate questions;
- payload pointers: video ID, start/end, speaker, transcript hash, group ID, source, teacher identity, provenance, and quality status.

Do not embed generated questions into the teacher passage text if doing so weakens verbatim provenance. Validate deterministic IDs by rebuilding twice. Keep the previous collection available for rollback. Use an alias swap only after all audit gates pass.

Drop or quarantine summary points with no backing video from the first-person serving path. Do not necessarily delete them from ordinary general-chat retrieval without a separate product decision.

### R — Retrieval comparison and calibration

Benchmark at least:

- `R0`: current dense/sparse or hybrid baseline;
- `R1`: baseline plus separate question field;
- `R2`: R1 plus existing production reranker;
- `R3`: LLM-assisted HyDE/query rewrite/ranking only if it can be executed with strict latency, cost, and unknown-ID rejection.

The LLM must never write the teacher’s words. It may assist offline or select among verified candidate pointers.

Tune hybrid fusion weights using labelled data rather than assuming untuned RRF is optimal. Measure per-video and aggregate metrics with uncertainty intervals. Fit calibration only on appropriate training data and evaluate on held-out questions/videos. Report precision/coverage curves and abstention behavior.

A useful target is a one-sided 95% upper confidence bound on confident-answer error at or below 1%, but do not claim this until the gold set is large and valid. Coverage must always be reported beside precision.

### F — First-person serving path

Implement behind `FIRST_PERSON_MODE` or an equivalent feature flag:

```text
crisis/safety pre-check
→ exact cache
→ first-person hybrid Qdrant retrieval
→ rerank
→ calibrated threshold
→ direct-answer or related-clip decision
→ select up to 3 clips, max 1 per video
→ render only from verbatim transcript
→ exact-substring and transcript-hash validation
→ citation fields
→ frontend timestamped playback
```

Extend the citation contract compatibly with existing citations. At minimum support:

- `timestamp_seconds` or equivalent;
- `text_snippet`;
- `speaker`;
- video/source ID where appropriate;
- provenance/verbatim status.

Update `src/components/chat/CitationCard.tsx` and `src/components/chat/ChatMessage.tsx` without hardcoding a teacher name or hiding timestamp zero. Add backend, frontend, and browser-preview tests.

The specialized first-person route must not call the general knowledge graph by default. Preserve crisis handling, tenant isolation, rights policy, and ordinary-chat behavior.

### S5 — Separate secure-memory workstream

Do not mix secure memory work into the first-person retrieval launch unless required by an existing broken contract. Treat it separately:

- propose-then-save;
- encrypted canonical memory;
- KEK outside `.env`;
- retention/purge verification;
- authenticated and user-scoped access;
- age/consent policy review.

### P — Production hardening and release

A first-person data-path pass is not the same as full-platform production readiness.

Before any broad production release, verify:

- real Railway boot with no OOM abort;
- no unrecoverable thread-pool/container wedge;
- health/readiness probes test actual executability, not only object presence;
- real restart-on-hang or an external watchdog exists;
- live graph topology matches the documented and budgeted architecture;
- Celery/worker mode is intentional and cost-controlled;
- Qdrant, Redis, Supabase, and graph dependencies have tested failure behavior;
- backups and restore drills are completed;
- collection alias rollback works;
- deployment config is not stale relative to repository HEAD;
- security, RLS, tenant isolation, upload, rate-limit, and secret checks pass;
- crisis/safety content receives native-speaker and clinician review where required;
- content rights/Ekam approval is complete;
- observability, alerting, audit sampling, and runbooks are active.

The current repository’s production audit contains a **NO-GO** verdict for unresolved OOM/recovery/graph-topology issues. Do not overwrite that verdict with a green document; replace it only with current evidence.

## Required verification commands

Discover exact project commands first, then run appropriate subsets such as:

```bash
cd backend
pytest tests/test_teacher_attribution.py tests/test_cross_tenant_leak_probe.py -q
pytest tests/ -k "ingest or okf or corpus or teacher or citation or benchmark" -q
pytest tests/ -q --tb=short
cd ..
npm test -- --run

git diff --check
git status --short
```

Run integration/scratch tests only with isolated collections, corpora, and credentials. Do not point tests at live production stores unless the test is explicitly read-only.

For each phase, report a table:

| Phase | Result | Evidence | Confidence | Still unproven |
|---|---|---|---|---|
| ... | ... | command/count/report | VERIFIED/PARTIAL/UNVERIFIED | ... |

## Final acceptance criteria

Do not call the first-person path production-ready until all applicable items below have evidence:

- no fabricated first-person quote reaches the serving path;
- no host words are labelled as teacher words;
- no wrong-speaker confident answer passes;
- no invalid/out-of-range timestamp passes;
- every served span matches the verbatim transcript hash;
- a fresh video passes the full ingestion gate;
- Qdrant rebuild is deterministic and rollback-capable;
- benchmark errors include timeouts, 429s, and empty results;
- precision and coverage are reported on valid human-labelled held-out data;
- confident-answer error meets the chosen threshold with the stated statistical method;
- first-person p95 latency meets the measured product budget under realistic load;
- citation and playback are browser-verified;
- feature flag and fallback behavior are tested;
- ordinary general-chat regression tests pass;
- monitoring, auditing, and rollback are operational.

Do not call the entire MukthiGuru platform production-ready until the independent infrastructure, security, rights, safety, backup, deployment, and recovery gates also pass.

## How to work

At the start of every action, write one short line describing what you are about to do. Work phase by phase. Prefer parallel read-only investigation where tasks are independent, but keep persistent writes sequential and approval-gated. After every phase, stop and report the changed files, commands run, evidence, confidence, risks, and the exact next gate. If a referenced file or assumption is wrong, correct the plan based on the actual repository rather than inventing a path or claiming completion.

Begin with **B0 read-only repository inspection and baseline measurement**. Do not modify persistent data, download large models, commit, push, or change production configuration until the baseline report and file map are complete.

---

## Immediate user decision points

Ask the user before these consequential choices:

- applying any Qdrant/OKF/Neo4j/Memgraph backfill;
- selecting strip versus quarantine for contaminated records;
- choosing whether video-less summaries remain in ordinary chat;
- accepting gated model licences or non-commercial restrictions;
- approving compute/download budget;
- choosing the precision/coverage operating point;
- deleting losing retrieval models or modes;
- enabling production traffic for the feature;
- changing content-rights, crisis, or clinical-review policy.

Until those decisions are made, remain read-only or operate only in isolated scratch space.
