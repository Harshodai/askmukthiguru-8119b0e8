# Master Plan: first-person answers, routing, profile and chat (rev 2, 2026-10-17)

Owner: Harsha. Rewritten from rev 1 (`.bak_rev1_2026-10-17` beside this file) after a review against the code, CLAUDE.md invariants and the A1–A24 task list (`docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`). Every one of Harsha's 18 requests from the 2026-10-16 session is mapped to a task in section 2. Verdict stays **NO-GO** until the clean-Docker run on final main is graded.

## 0. Rules every thread follows (not negotiable without Harsha's typed word)

1. **The teachers' words are never edited.** No grammar fixes, no stripping "Yes,"/"So,", no bracketed inserts inside a quote. Served text must match `transcript_hash` byte for byte (invariants 2, 13; A20). We fix unclear quotes by choosing better clip boundaries and by writing *our own* framing text *outside* the quote, clearly separate.
2. **No improvised teachings.** If no recording answers a part of the question, say so plainly for that part. Never fall through to the generating graph to fill the gap (invariant 21, owner decision 2026-10-11).
3. **No hand-picked thresholds.** Keep `first_person_uncalibrated_direct_enabled=False` and keep "Related, not a direct answer" until a 299-label calibration exists (invariant 3). The relevance gate (min 3) stays until a replacement is measured on human labels to be at least as good (invariant 24: it cut the judge's DON'T-SHOW share from 42% to 12%).
4. **Safety first.** Crisis and topic rails run before retrieval (invariant 8). After any change to gates, routing or prompts, run `evals/run_safety_scenarios.py` and the crisis tests; report 0 crisis misses and the control false-positive count.
5. **Measure on the collection faculty will get.** The Mac compose serves `first_person_v7` (`f0964cf`); prod config says `first_person_v8`. Every run records collection name and point count. Harsha picks the faculty collection before any coverage number is quoted (task P0.3).
6. **Report more than "served".** Every answer-quality run reports: served count, out-of-scope leaks (must stay 0, 32/32 abstain), indeterminate (must be 0), the independent judge's DON'T-SHOW share, p50/p95 latency.
7. Small PRs off `main`, one task each, flags default off. Nothing new joins PR #68. Only the audit thread merges.
8. Cost: Sonnet 5.5 for build work, Haiku 5.5 for bulk checks, Opus only for the safety/verbatim review in its own thread.

## 1. What the review found in rev 1 (why it changed)

| Rev 1 item | Problem | Rev 2 handling |
|---|---|---|
| 1.1 fallback on, uncalibrated direct on, 0.45 calibration | Reverses owner decision; 0.45 served "capital of France" as teaching (Audit D P0) | Dropped. Rules 2, 3 |
| 1.3 abstain → general generation | Improvised teachings | Replaced by per-facet honest "no recording" line (F2) |
| 2.1 strip openers, bracket clarifiers | Edits verbatim | Replaced by boundary snapping + framing outside quotes (F3, F4) |
| 2.3 rewrite `GURU_SYSTEM_PROMPT` | Anti-impersonation clause lives there | Untouched; first-person path doesn't use it |
| 2.4 swap relevance gate for cross-encoder, crag 0.75→0.58 | Removes a measured gate; hand-set number | Parallelize first; swap only if measured equal on labels (L1, L2) |
| 3.1 drop `require_aal2` on personal KG | Was framed as a blanket relax | Narrowed: own subgraph at the same login level as the memory API, which already uses `get_current_user_from_supabase` (U4) |
| §4 sample answer | Its "verbatim" quotes are not from any transcript | Replaced by an answer *shape* with placeholders (section 4) |
| E1 "claims 100%" / E4 END | By design (registry) | Not a bug; router task starts from a live repro (R1) |
| E2 v8 404 | Already overridden locally | Becomes a decision (P0.3) |
| 1.2 Neo4j in first-person | Graph is Memgraph and reaches no answer today | Optional later research only |

## 2. Your 18 requests → tasks

| # | Your request (short) | Task(s) |
|---|---|---|
| 1 | Deploy to Docker, inspect profile + chat with DevTools; profile looks bad; chat cluttered; share with Ekam/Serene Mind photo themes; remove Wisdom Map; user KG; LLM ranker too slow; "Yes, this resolves…" unclear; check ingestion/retrieval; subagents; plan | U1–U5, L1–L2, F3–F4, I1–I3, V1 |
| 2 | First-person (not general chat); user-based KG; check FP ingestion/retrieval with research | F1–F5, U4, I1–I3, X1 |
| 3 | Adopt contextual ideas from `spiritual_wisdom_contextual`; hybrid search; agentic/Graph RAG instead of regex; join verbatim smarter; only authorised users | I2, F1, F2, X1, U4 |
| 4 | Will contextual ingestion change answers? | I2 measured against the frozen 29 before any switch |
| 5 | Tags and context as separate Qdrant fields; OKF wiring | I2, I3 |
| 6 | Append to plan | this file |
| 7 | Deeper research for answers that fit the question | X1 |
| 8 | Close every gap between question and answer | F1, F2, F5 |
| 9 | No split, gappy answers | F4 (one continuous answer layout) |
| 10 | Bugs and gaps remain | R1, Q1 |
| 11 | Company blogs leaking; router broken; swarm; ponytail | R1, R2, threads in section 5 |
| 12 | Routing broken; answers tuned to the user; ChatGPT/Claude-style points | R1, F4, F5 |
| 13 | Answers feel AI-generated, not verbatim | F3, F4 (quotes dominate; framing marked as ours) |
| 14 | More research | X1 |
| 15 | One master plan linking all plans | section 6 |
| 16 | What makes us much better | section 3 |
| 17 | Missing requests | this table |
| 18 | Check plan for mistakes | section 1; Q1 |

## 3. What makes us better (honest version)

1. **Every teaching sentence is a real recording**, playable at the exact second, labelled by verified speaker or channel (A17). Competitors paraphrase; we don't.
2. **Compound questions get one answer per part.** Each part gets its own clip or an honest "I don't have a recording on this yet".
3. **Clips start and end on complete thoughts**, so "this" always has its subject inside the clip.
4. **Clear layout**: short headings per part, the quote as the body, a ▶ Listen button, and sources at the end. Points and headings, ChatGPT/Claude-style, without rewriting the teacher.
5. **Fast**: target p95 under 6 s uncached, measured, never claimed.
6. **Safe**: crisis rails first; no clip for out-of-scope questions; no web blogs in teachings.

## 4. Answer shape for a compound question (placeholders, not real quotes)

```
[Our framing, 1 line, visibly ours: "Your question has three parts: suffering, love, prosperity."]

### On suffering and meditation
> «exact clip text, byte-identical to transcript» — Sri Krishnaji · ▶ 01:12
### On love
> «exact clip text» — shared in <channel> (unverified speaker) · ▶ 02:25
### On prosperity and success
I don't have a recording that answers this part yet.   ← honest gap, no improvising

Related, not a direct answer (until calibration exists)
Sources: [1] video title @ 01:12 · [2] video title @ 02:25
```

Framing lines are optional (flag `FIRST_PERSON_FRAMING_ENABLED`, default off). If they are switched on, an LLM writes them, they never state a teaching, and they render in a different style from quotes. A check rejects any framing line that makes a doctrinal claim. Harsha decides whether to switch them on after reading 20 examples.

## 5. Tasks

### P0: unblock (do first)
- **P0.1** PR #68 green. Fix the two reds this PR caused, then any others. (a) `.gitleaks.toml`: config fails to load ("'Allowlist' expected a map, got 'slice'"), so no secret scan ran; use the form gitleaks 8.24.3 accepts and verify locally. (b) `src/test/personalizeTeaching.test.ts:49`: mock `@/integrations/supabase/client`; no real keys in CI. Never skip tests.
- **P0.2** Triage the 27 uncommitted Mac files (`ClipReportsPage`, Auth/MFA/AgeConfirm/ResetPassword pages, 15 locales, `source-hashes.json`, `docs/reviews/A12_*`, `A24_*`). Move them to their own branch and PR; review auth pages on their own.
- **P0.3** Decision (Harsha): faculty collection, v7 or v8. Record the point counts of both.

### R: routing and web leaks
- **R1** Reproduce "router broken" live. Ask the exact compound question plus 10 others on the Mac stack; log `route_decision`, `model_used` and the first-person status per request. Fix what the trace shows, with a test per bug. Don't fix the rev 1 E1–E4 claims blind: E1 and E4 are by design.
- **R2** Web firewall (rev 1 task 1.5 kept). Allow-list only official domains; drop the LinkedIn/social entries; never merge web docs into doctrine retrieval (`retrieval.py` `web_docs + all_docs`); no fixed 0.70 score for web docs; narrow the temporal patterns in `intent.py` (`needs_web_search=True` at lines 239, 478, 498, 713). First find how a blog reached a first-person-only chat (R1 trace).

### F: first-person answers
- **F1** Facet split inside the first-person pipeline. Split compound questions into up to 3 parts (one fast-model call, or deterministic for "X and Y"). Retrieve per part with the existing dense+sparse RRF on the chosen collection; batch the embeddings.
- **F2** Per-part gates. Each part's clip must pass the answerability check and relevance ≥3 on its own. If a part fails, say "no recording yet" for it. If every part fails, the existing abstain applies. Extend `FIRST_PERSON_SECOND_QUOTE_ENABLED` (default off) to up to 3 quotes, from different videos where possible.
- **F3** Unclear openers ("Yes, this resolves…"): handled at the boundary, not in the text. At serve time, if a clip opens with an orphan demonstrative, prefer a neighbouring clip that contains the antecedent, or skip it (`_standalone_problem` already rejects orphan openers). At index time, see I1.
- **F4** One continuous layout (section 4). Frontend renders headings, quote blocks, ▶ Listen and sources; no separate cards and no URLs mid-sentence. Retire `_format_clip_block` output on this path.
- **F5** Tuned to the seeker. Use opted-in personalisation (T-B14) only to *order* parts and choose between equally relevant clips, never to change text. Measure on the frozen 29 plus 10 compound questions.

### L: latency
- **L1** Run the answerability check and the relevance scorer concurrently with retrieval where their inputs allow (answerability needs only the question). Measure p50/p95 before and after on the same 29 questions and the same collection.
- **L2** Cross-encoder as relevance scorer: an A/B only. Score the 29 questions' top-3 clips with both; switch only if the human or independent-judge DON'T-SHOW share is no worse. `crag_skip_confidence` stays 0.75 (general path; not first-person).

### I: ingestion and storage
- **I1** Complete-thought boundaries: run the existing builder stage (`--complete-thoughts`, `387550f`, `tests/test_index_completeness.py`) on a pilot of 20 videos. Count clips starting with an orphan demonstrative before and after. Text stays verbatim; only start/end move to sentence boundaries (invariants 6, 10, 11).
- **I2** Context as separate fields, not in the vector. Add payload fields `discourse_context`, `tags`, `okf_concept_id`, `okf_title` (LLM-made offline, passing the review gate and `find_artifact()`, L-INGEST-1). Optionally add a separate named vector `context_dense`; `passage_dense` stays pure verbatim. This is a new collection (invariant 4), built host-side (invariant 18). Compare against the current collection on the frozen 29 before any switch (answers your request 4). **Decide I2 before the 299-label calibration batch**: any change to embedded text, vectors or fusion invalidates a fitted threshold, and no profile exists yet, so the change is free now and costly later (research report, section 3). First check which score the abstention gate reads (fused RRF, dense cosine or the scorer).
- **I3** OKF wiring: OKF may route a question to a concept and tag clips; it is never rendered as teacher voice (invariant 12).

### U: profile, chat, share, KG (frontend)
- **U1** Profile redesign: one header across tabs, Journey stats (`ProfileStatTiles`, `SadhanaHeatmap`), consistent cards. Build on `b1ab5ca` and `74e51b1`, which already decluttered parts.
- **U2** Chat declutter: one source pill opening the citation panel; Listen/Share/Copy as primary actions; no debug scores.
- **U3** Share card photo themes (Ekam Sanctuary, Serene Mind, Sacred Dawn, Night) using the licensed photos from `85f5e3b`; native share plus PNG download.
- **U4** User KG: remove the public Wisdom Map from nav, palette and messages. Personal subgraph lives in Profile → Memory → Graph. Allow it at the same login level as the memory API (`get_current_user_from_supabase`, which the memory endpoints already use), scoped to the caller's own data, anonymous → empty. Keep `require_aal2` on `kg_sparql` and the other KG routes. Add a test that user A cannot read user B's subgraph.
- **U5** Verify in the browser on the Mac Docker stack: profile, chat, share export, KG as user A and B. Screenshots in the PR.

### X: research (feeds F and I, no code)
- **X1** Short research note: verbatim-answer products (exact-second anchoring, span trimming), multi-span answer assembly, contextual retrieval with metadata instead of vector-prefixing, agentic/graph RAG for multi-part questions. Real, checkable sources only; say "unverified" where you can't confirm. Output one page of recommendations with expected effect and how we would measure it.

### Q: quality and release
- **Q1** After each merged task: backend + frontend suites, safety evals, frozen 29 + 10 compound questions with the section 0 metrics, and a runbook artifact update.
- **Q2** Opus thread: one review of every change touching gates, safety or quote rendering, before merge.
- **Q3** Clean-Docker run on final main, caches verified empty (`make verify-cache-empty`), graded by the audit thread.

### Human gates (unchanged, still open)
Clinician and native speakers (A7, A12, A24: self-injury and eating-disorder phrases get no helpline today; your decision on an interim), listening audit (A11), Supabase key, Railway login and go, merge of #69 via the audit thread.

## 5b. Threads for the coordinator to start

Each thread owns its files; no two threads edit the same file. Cloud threads write code and unit tests; anything live (Docker, Qdrant, paid calls) runs on the Mac, batched into one sitting for Harsha.

| Thread | Tasks | Model | Owns | Starts |
|---|---|---|---|---|
| T1 CI green | P0.1, P0.2 | Sonnet | `.gitleaks.toml`, `personalizeTeaching.test.ts`, stray-file branch | Now |
| T2 Routing and web | R1, R2 | Sonnet | `intent.py`, `web_search_service.py`, web parts of `retrieval.py`/`reranking.py`, `query_patterns.py` | Now; R1 repro needs the Mac |
| T3 First-person answers and speed | F1, F2, F3, F5, L1, L2, F4 backend payload | Sonnet | `first_person_pipeline.py`, `first_person_bridge.py`, `quote_weaver.py` | Now; measurements after P0.3 |
| T4 Ingestion and storage | I1, I2, I3 | Sonnet | `build_first_person_index.py`, `first_person_store.py`, `ingest/verbatim/` | Now; new collection only with Harsha's OK |
| T5 Frontend | U1-U5, F4 rendering | Sonnet | `src/` pages/components, `kg.py` personal route | Now |
| T6 Research | X1 | Sonnet | note under `docs/agent/` | Now |
| T7 Bulk checks | verify plan claims vs code; extract section 0 metrics per run | Haiku | no code | Now and after each run |
| T8 Safety review | Q2 | Opus, separate thread | review only | Before each merge touching gates or quotes |

Order that matters: T1 merges first. T3's answer shape lands before T5 renders it. P0.3 before any coverage number. Q3 last.

Doc version: https://claude.ai/code/artifact/be569d3d-04f8-4acd-9c26-2d18a4553271

## 5c. Research checks (web, 2026-10-16)
- Contextual retrieval = LLM context added to each chunk before embedding + BM25; Anthropic reports top-20 failures 5.7% -> 3.7% (contextual embeddings) -> 2.9% (+ contextual BM25): https://anthropic.com/news/contextual-retrieval . The 67% figure with reranking is secondary only (unverified). For I2 the context goes into its own named vector + sparse field so the verbatim passage vector stays untouched.
- Qdrant: several named vectors per point, combined with `prefetch` sub-queries fused by RRF in one call: https://qdrant.tech/documentation/hybrid-queries/ (fusion syntax differs by version; check ours).
- Query decomposition, retrieve per sub-question: https://python.langchain.com/docs/use_cases/query_analysis/techniques/decomposition . F1 does this, each part answered by a real clip, never generated text.

## 5d. Deep research
Full report: `docs/agent/research_verbatim_clip_2026-10-17/REPORT.md` (notes in `docs/agent/research_verbatim_clip_2026-10-17/notes/`). Most primary papers were read through search summaries only; the report marks each claim. Handoff prompt for a new agent: `docs/agent/HANDOFF_PROMPT_MASTER_PLAN_2026-10-17.md`. Seeker-side gaps: `docs/plans/USER_GAPS_2026-10-17.md` (task list A25-A33).

## 6. Linked documents
- Task list and evidence: `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` (A1–A24)
- First-person truth anchors: CLAUDE.md invariants; `docs/architecture/first-person-path-to-prod.md`
- Architecture: `docs/architecture/first-person-rag-architecture-2026-10-11.md`
- Answer quality history: `docs/FP_ANSWER_QUALITY_2026-10-04.md` (dated; not truth for numbers)
- Synthesis research (dated, several designs never built): `.claude/tasks/unified_book_style_teaching_synthesis_plan.md`, `..._research.md`, `ruthless_breakthrough_unified_synthesis_plan.md`, `quote_weaver_and_first_person_polish.md`
- Ingestion: `docs/RUTHLESS_PIPELINE_RESEARCH_AND_WORLD_CLASS_ARCHITECTURE.md`, `.claude/tasks/rigorous_ingestion_retrieval_first_person_production_plan.md`
- OKF: `docs/OKF_WIRING_RESEARCH_2026-10-04.md`; competitors: `docs/COMPANY_TEARDOWNS_2026-10-04.md`
- UX: `.claude/tasks/resonant_sacred_guidance_ux_transformation.md`; Docker: `.claude/tasks/world_class_production_elevation_and_docker_redeploy.md`
- Plan review: project file `reviews/pr68-plan-review-2026-10-16.md`
