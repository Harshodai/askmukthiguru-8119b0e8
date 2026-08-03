# Corpus remediation + `spiritual_wisdom_contextual` migration plan

**Written 2026-08-01** after the corpus audit in `OKF_AND_ANTI_HALLUCINATION.md` §4.
Every number here was measured against the live Qdrant instance, not estimated.

---

## 0. The finding, in one paragraph

**24.3% of the 89,061 live `spiritual_wisdom` chunks (~21,641) contain the
extraction LLM's own chain-of-thought**, embedded and retrievable as doctrine.
186 of 391 source videos are affected; some are total losses
(`8mmungGgDNw` 63/65 chunks, `UZHSssZflFQ` 35/35, `O1VkNuEChD4` 27/27). Live,
verbatim, retrievable today:

> *"Sadhana is a term in the teaching. a common transcription error where a space is omitted."*
> *"1. **Deconstruct the User's Request:**"*

No prompt change fixes this. Retrieval over a poisoned corpus produces poisoned
answers, and every downstream quality layer — reranking, CRAG grading,
LettuceDetect faithfulness — is *working correctly* when it faithfully grounds an
answer in a chunk that happens to be machine reasoning.

**Combined total.** With both vectors gated (LLM chain-of-thought, §1; Whisper
decoder loops, §5), the shipped filter rejects **29.4% of 8,000 sampled live
chunks — an estimated 26,161 of 89,061**: 1,930 LLM artifacts + 420 repetition
loops per 8,000. That is the size of the re-ingest.

**Confirmed against the full corpus (2026-08-01).** All 89,061 chunks scanned
(`benchmarks/reports/corpus_audit_20260801_full.json`): **26,913 contaminated,
30.2%** — 22,176 LLM artifacts + 4,737 repetition loops. The 8,000-chunk
estimate was accurate to 0.8 pt, and the sampled projection of 26,161 landed
within 3% of the true 26,913.

The full scan also splits by chunk tier, which the sample did not. The result
inverts the intuition that short, single-sentence chunks carry the poison:

| Tier (body length after header strip) | Total | Poisoned | Rate |
|---|---|---|---|
| **passage** (≥200 chars) | 18,556 | 8,518 | **45.9%** |
| proposition (<200 chars) | 70,505 | 18,395 | 26.1% |

Passage-tier chunks are **1.8× more contaminated**. A longer chunk has more
surface area for a single chain-of-thought fragment to land in, and one hit
condemns the whole chunk. This closes off the tempting shortcut of dropping the
proposition tier and re-ingesting only passages — it would leave the *worse*
half in place.

---

## 1. Root cause analysis

### 1.1 Immediate cause

`IngestionPipeline._extract_topics` asked an LLM for a JSON array of topics. When
the array failed to parse, the fallback **salvaged the raw text through a
blocklist** of ~20 reasoning phrases. Any line not on that list became a topic,
was written into the chunk header
(`[Source: … | Speaker: … | Topic: <reasoning text>]`), embedded, and served.

A blocklist is the wrong shape for this job. It fails **open** by construction:
it can only reject what someone already saw. The corpus is full of phrasings
nobody put on the list — `**Deconstruct` (631 hits), `**Analyze` (503),
`**Brainstorm` (84), `**Synthesiz` (83).

This is the failure mode the structured-output literature names directly:
*"a schema-valid payload with wrong values is worse than a parse error. A parse
error fails loudly and immediately, while a valid-but-wrong value fails
downstream, hours later, in a place nobody expected."*
([TianPan.co, 2026](https://tianpan.co/blog/2026-04-09-structured-output-failures-production-llm))

### 1.2 Why nothing downstream caught it

The codebase already contained a validator for exactly this text —
`OKFQualityFilter`, whose pattern table was written after finding the *same*
artifacts inside `memory/okf/`. It was wired to **one** call site:
`OKFStore.list_entries()`, guarding 23 entries. It never guarded the 89,061-chunk
corpus.

Three validators existed, each guarding one path, none shared:

| Validator | Guards | Shape | Verdict |
|---|---|---|---|
| `OKFQualityFilter` | OKF bundle (23 entries) | blocklist of artifact patterns | correct, wrong scope |
| `raptor.py:269` topic-label check | RAPTOR summary labels | **positive validation** (length, newline, period count) → fail closed | **correct** |
| `_contains_prompt_leak` | `ingest/corrector.py` output | prompt-echo detection | correct, narrow |
| *(nothing)* | **the Qdrant write path** | — | **the gap** |

The repo already knew the right pattern. `raptor.py:269` rejects a malformed
topic label and falls back to empty. `_extract_topics`, solving the identical
problem, salvaged instead. Same defect class, two authors, opposite failure
modes, no shared code.

### 1.3 The five whys

1. Why is LLM reasoning in the corpus? → `_extract_topics` returned it as a topic.
2. Why? → JSON parse failed and the fallback salvaged free text.
3. Why salvage? → written to "never fail ingestion" — resilience implemented as fail-open.
4. Why did nothing downstream catch it? → the artifact validator was scoped to OKF only.
5. Why was it scoped to OKF only? → **no single validation chokepoint on the write path.** Each guard was added where a bug was found, never promoted to shared infrastructure.

**Root cause: LLM output reaches persistent storage without a mandatory, shared,
positively-validating gate.**

### 1.4 Second defect at the same chokepoint

`_embed_and_upsert` filtered chunks with `scan_chunks_for_injection`, which
returns a *shrunk list*, then indexed `extra_metadatas[i]` by **post-filter**
position although the list was built for the **pre-filter** chunks. One dropped
chunk shifted every subsequent chunk's metadata onto the wrong chunk — silently,
no error. Same chokepoint, same class: a lossy interface that discards the
information callers need to stay consistent.

---

## 2. Prevention — landed 2026-08-01

Fixes are in the working tree. Suite: `1268 passed, 4 failed`, all 4 pre-existing
(2 langhanam flag/test drift, 1 Qdrant Docker hostname, 1 `cwd="backend"` assumption).

| Change | File | Effect |
|---|---|---|
| Shared artifact detector — one pattern table, index-preserving API | **new** `backend/services/text_quality_filter.py` | single source of truth for every persistence path |
| `_extract_topics` fails **closed** — blocklist salvage deleted, `clean_topic_label` positive validation, loud warning on unparseable output | `backend/ingest/pipeline.py` | reasoning text can no longer become a topic |
| Artifact gate at the Qdrant write chokepoint, beside the injection scan | `backend/ingest/pipeline.py:_embed_and_upsert` | nothing reaches Qdrant unvalidated |
| Index-based filtering; `extra_metadatas` and `chunk_speakers` re-sliced by kept indices | `backend/ingest/pipeline.py:_embed_and_upsert` | metadata can no longer drift onto the wrong chunk |
| `OKFQualityFilter` inherits the shared table | `backend/services/okf_quality_filter.py` | OKF gains the 12 patterns it lacked; two lists can no longer drift |
| 32 regression tests incl. false-positive guard on verbatim guru speech | **new** `backend/tests/test_text_quality_filter.py` | a pattern that would delete doctrine fails CI |

**Deliberate design constraint:** the shared table is **high-precision, not
high-recall**. `"We are given"` stays out of the corpus table — it appears in real
teachings (*"We are given this life…"*) and a false positive deletes doctrine. It
remains in the OKF-only table, where rejection merely blocks an auto-extracted
entry from going live and a human can override. Verified: all 23 live OKF entries
still pass; 6 verbatim `guru_tone_podcast` sentences are pinned as
must-never-reject.

---

## 3. Remediation + migration

The stated goal is to move from `spiritual_wisdom` (89,061 pts, poisoned) to
`spiritual_wisdom_contextual` (**11 pts today**). These are the same operation: a
clean re-ingest *is* the migration. Do it once, not twice.

> ⚠️ **`settings.qdrant_collection` already defaults to `spiritual_wisdom_contextual`**
> (`app/config.py:146`), which holds 11 points. `.env` and `.env.example` override
> to `spiritual_wisdom`. **If Railway production does not set `QDRANT_COLLECTION`,
> production is retrieving from 11 chunks while `/api/health` reports green.**
> Verify before anything else.

### Phase 0 — Verify and freeze (hours)

1. Confirm prod `QDRANT_COLLECTION`. If unset, set it to `spiritual_wisdom` now.
2. Snapshot `spiritual_wisdom` (`scripts/ops/backup_qdrant.py`). Nothing is deleted until cutover succeeds.
3. Freeze ingestion, or confirm every new run exercises the §2 gates.

### Phase 1 — Measure and quarantine (~1 day)

Full-corpus audit, not a sample. Produce a per-source contamination report
(`source_url, total_chunks, poisoned_chunks, pct, matched_artifacts`) and route
rejects to a **quarantine store rather than deleting them** — the
dead-letter-queue / quarantine pattern is standard for exactly this
([PipeCode](https://pipecode.ai/blogs/data-quality-frameworks-great-expectations-vs-dbt-tests-vs-soda-core),
[Unstructured](https://unstructured.io/insights/data-governance-your-path-to-quality-transformation)).

Bucket the 391 sources:
- **Total loss** (>80% poisoned) → re-ingest from source, mandatory.
- **Partial** (5–80%) → re-ingest; cheaper and safer than surgical deletion.
- **Clean** (<5%) → eligible for migrate-in-place.

### Phase 2 — Blue-green re-ingest (compute-bound)

Standard zero-downtime vector migration
([Qdrant](https://qdrant.tech/documentation/tutorials-operations/embedding-model-migration/),
[Vector Database Reindexing Pipeline](https://medium.com/@kandaanusha/vector-database-reindexing-pipeline-87efa1d1cd19)):

1. **Green collection** — build `spiritual_wisdom_contextual` fresh, same 1024-dim
   config. Blue keeps serving. Doubles storage during the move; that is the price
   of instant rollback.
2. **Dual-write** — new ingestion writes to both until cutover.
3. **Backfill** — re-ingest all affected sources through the fixed pipeline. Resume
   via `ingest/handlers/checkpoint.py:IngestionCheckpoint` (Redis → Supabase → JSON),
   **never** a hand-rolled local file — Railway's filesystem is ephemeral.
4. **Fix the two ingest gaps while re-embedding** — the embed cost is paid once:
   - **Real contextual retrieval.** Today `chunk_with_contextual_headers` prepends
     one *static per-document* header. Anthropic's technique generates a
     *chunk-specific* 50–100 token context from the full document: **35%**
     retrieval-failure reduction, **49%** with contextual BM25, **67%** with
     reranking ([Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)).
     `CONTEXTUAL_CHUNK_HEADER_PROMPT` already exists and is never called — wire it,
     but **strip its "Speaker: Sri Preethaji or Sri Krishnaji" field**: asking an
     LLM to guess the speaker from chunk text is how a teaching gets misattributed.
   - **Speaker identity.** `guru_tone_podcast` carries `guru_name: preethaji|krishnaji`
     keyed by `source_id`. Join it onto the corpus during backfill for real
     per-source attribution instead of a guess.

### Phase 3 — Shadow, then atomic cutover

1. **Held-out query set** — run identical queries against blue and green; compare
   recall and answer quality before switching anything.
2. **Shadow 5–10% of traffic** to green; compare telemetry.
3. **Atomic switch** — flip `QDRANT_COLLECTION` (config is already
   collection-name-driven, so this is a one-variable change); disable dual-write.
4. **Rollback** = flip the variable back. Blue stays intact at least one week.

### Phase 4 — Standing gates so it cannot recur

- **CI corpus audit** — sample N points from the live collection, fail the build if
  the artifact rate exceeds a threshold. Reuses `text_quality_filter`; ~20 lines.
- **Ingestion rejection metrics** — emit `chunks_rejected_total{reason}`. A source
  whose rejection rate spikes is a source whose LLM went off the rails; today that
  is invisible.
- **Quarantine review** — inspect rejected chunks periodically. A rising rejection
  rate on clean input means a pattern is over-matching and deleting doctrine.
- **Extend the gate to every LLM-output persistence path.** This audit covered the
  chunk path. Still unaudited, same defect class plausible: `triple_extractor.py`
  (Neo4j entities), `quality_gate.py`, `hyper_extract_adapter.py`,
  `contextual_reingest.py`.

---

## 4. Answer-path work — LANDED 2026-08-01

Independent of the corpus fix; shipped ahead of it. Full evidence in
`OKF_AND_ANTI_HALLUCINATION.md` §4. Suite after: **1285 passed, 2 failed**
(both pre-existing and environmental — `test_graphrag_fusion` hardcodes
`cwd="backend"`; `test_ruthless_phase2` dials the Docker hostname
`qdrant:6333`). Up from 1230 passed / 3 failed.

| # | Fix | Status | Verified behaviour |
|---|---|---|---|
| 1 | Persona cap 512 → `_PERSONA_TOKEN_BUDGET` (2048) in `context_engineer` | ✅ | constitution delivered **1286/1286 words** (was 393). The ban on invented quotes, the crisis-helpline rule, the clinical redirect, `## Who you are`, the Voice section, and the `[USER CLASSIFICATION]` block all now reach the model. `max_tokens_per_request` is 12000, so the old cap was never budget-driven — just wrong. |
| 2 | OKF scoring `0.9 + cos*0.1` → `cos * 1.10` with a 0.45 floor; keyword fallback gains a 30% coverage gate and a 0.60 ceiling | ✅ | cosine 0.00/0.30/0.44 → **not injected** (previously all scored ≥0.90 and outranked every real hit). A genuine Qdrant hit at 0.75 now wins. |
| 3 | `LANGHANAM_VOICE_BLOCK` rebuilt from the 157 labelled exemplars | ✅ | Sanskrit quota, "Our ancients in India", and the flat 20-word cap **removed**; second-person address, preserve-their-first-person, their own doctrinal vocabulary, rhetorical questions, and short-then-long rhythm **added**. |
| 4 | `LANGHANAM_ELIGIBLE_INTENTS` + `FACTUAL`/`FOLLOW_UP`/`GUIDED_TOUR` | ✅ | voice now fires on **7/8** realistic seeker questions (was 1/8). `CASUAL`/`GREETING` still excluded. |
| 5 | Pronoun rule inverted at all 4 prompt sites + `GURU_SYSTEM_PROMPT` | ✅ | the gurus' retrieved "I" is preserved and attributed instead of flattened to "they"; manufacturing a first-person sentence absent from context remains forbidden. This is the mechanism behind the *Miracle of Mind* effect. |
| 6 | `format_final_answer` fast-tier reports the **measured** LettuceDetect score and gates on `faithfulness_floor` | ✅ | the hardcoded `faithfulness_score: 1.0 / method: "fast_tier_bypass"` is gone; a fast answer below the floor now falls through to graduated gating instead of being waved through. Hallucination rate becomes measurable on the ~73% majority path. |

Regression coverage: `backend/tests/test_answer_path_regressions.py` (persona
budget, every critical rule surviving the cap, no additive OKF floor, no
hardcoded fast-tier pass) and the corrected
`backend/tests/test_guru_voice_langhanam.py`.

**Still open on the answer path:** the fast graph has no reranker, so OKF entries
and retrieved chunks are never re-scored against each other there, and
`_map_docs_to_relevant` still takes `documents[:5]`. The §4.2 threshold reduces
the damage but does not replace reranking.

---

## 5. Second contamination vector: Whisper decoder loops

Measured 2026-08-01 on 10,000 live chunks, independent of the LLM-artifact scan.

| Signature | Rate | Est. corpus |
|---|---|---|
| Decoder repetition loop (5-gram repeated ≥4×) | **2.72%** | **~2,422 chunks** |
| YouTube caption boilerplate ("thanks for watching", `[Music]`, `©`) | 0.02% | ~18 chunks |

Worst observed: a single chunk containing the word **"Each" repeated 3,924 times**.

Two consequences, both bad:

1. **Degenerate embeddings.** A vector built from one token repeated thousands of
   times sits in a pathological region of the space and can surface for
   effectively arbitrary queries. This is worse than a useless chunk — it is an
   attractor.
2. **Compound failure.** The samples show the loop *and* the corrector LLM's
   commentary about the loop, both persisted:
   `*   The input is: "Each Each Each Each…"`. Whisper hallucinated → the
   corrector was handed the hallucination → it reasoned about it in prose → the
   reasoning was written to the corpus. Neither stage rejected the other's
   garbage.

This is the known Whisper long-form failure mode, not a local bug: *"during long
pauses or silent segments, Whisper sometimes invents plausible-sounding text…
hallucination errors are most prevalent in long-form audio transcription,
particularly when the audio contains large amounts of silence"*
([arXiv:2501.11378](https://arxiv.org/pdf/2501.11378),
[arXiv:2606.07473](https://arxiv.org/abs/2606.07473)). Published mitigations are
cheap and this pipeline uses none of them.

Caption boilerplate at 0.02% means that class is already effectively handled —
do not spend effort there.

---

## 6. Ingestion hardening — the top-notch target state

Ordered by (measured impact ÷ effort). Everything here rides along with the
Phase 2 re-ingest; the embed cost is paid once either way.

### 6.1 ASR gate — reject before the corrector ever sees it (highest ROI)

The corrector LLM cannot be trusted to clean a decoder loop; it writes prose
about it instead. Reject at the transcript stage.

| Control | Mechanism | Why |
|---|---|---|
| **VAD preprocessing** | Skip silent segments before decoding | Silence is the primary hallucination trigger; the single highest-value fix |
| **`repetition_penalty`** | Already exposed by `faster-whisper` | Suppresses the loop at decode time rather than detecting it after |
| **`compression_ratio_threshold`** | Whisper's built-in degenerate-output signal | A looping segment compresses absurdly well — this is the cheapest detector that exists and it is already in the API |
| **`avg_logprob` / `no_speech_prob` floors** | Per-segment confidence | Low-confidence segments are where invention happens |
| **n-gram loop detector** | 5-gram repeated ≥4× within a chunk | Backstop for whatever the above miss; ~15 lines, catches the "Each"×3,924 class outright |
| **`min_speakers`/`max_speakers`** | Known: 2 gurus + interviewer | Diarization accuracy improves materially when speaker count is constrained |

Contrastive decoding (Whisper-CD) reports up to **24.3 pp WER reduction** on
long-form benchmarks and is training-free
([arXiv:2603.06193](https://arxiv.org/html/2603.06193v1)) — worth evaluating, but
only after the four config-level controls above, which cost nothing.

### 6.2 Speaker identity — you already own the labelled data

`guru_tone_podcast` carries `guru_name: preethaji | krishnaji` on 157 segments
keyed by `source_id`. That is a ready-made **enrollment set**, and pyannote's
embedding model shares a vector space with its diarizer, so enrollment and
diarization are directly comparable
([pyannote discussion #1667](https://github.com/pyannote/pyannote-audio/discussions/1667)).

Pipeline: extract reference embeddings per guru from labelled segments → diarize
new audio → cosine-match each anonymous cluster (`SPEAKER_00`) against the
reference set → threshold-gate, falling back to `unknown`. *"No popular
open-source pipeline does this end-to-end out of the box"* — it is a real build,
but it converts speaker attribution from LLM guesswork into measurement.

**This is the prerequisite for every first-person feature.** You cannot render
the gurus' "I" until you know whose "I" it is.

Corpus skew to watch: 129 Preethaji vs 14 Krishnaji exemplars. Krishnaji's
enrollment set is thin and his threshold will need separate tuning.

### 6.3 Chunking — late chunking beats prepending a header

Two upgrades over today's static per-document header, in increasing order of ambition:

1. **Anthropic contextual retrieval** — per-chunk LLM-generated context before
   embedding: **35%** retrieval-failure reduction, **49%** with contextual BM25,
   **67%** with reranking ([Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)).
   Costs one LLM call per chunk at ingest.
2. **Late chunking** — embed the *whole document* with a long-context model, then
   pool per chunk. Every chunk embedding carries document context with **zero
   extra LLM calls**
   ([arXiv:2409.04701](https://arxiv.org/pdf/2409.04701),
   [Jina](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)).

**`bge-m3` — the model already in use — has an 8192-token context, so late
chunking is available today at no additional inference cost.** For a
transcript corpus, where a chunk's meaning depends heavily on the discourse
around it, this is the better first move. Contextual retrieval and late chunking
are complementary, not exclusive; measure late chunking first because it is free.

#### 6.3.1 Measured 2026-08-01 — "free" is not quite right, and one obvious route is a dead end

Late chunking needs **token-level vectors in the same space as the query
embedding**. Two candidate sources exist in this stack; only one works, and it
is not the one the production encoder exposes.

| Vector source | cosine vs production dense (same text) | Verdict |
|---|---|---|
| Pooled **ColBERT** head (`encode_with_colbert`) | **−0.041** | ❌ dead end |
| **CLS** of `last_hidden_state` | **0.914** | reference — this *is* the dense vector |
| **Mean-pooled** `last_hidden_state` | **0.703** | ✅ viable, with caveats |

1. **The ColBERT head is not usable for this.** `encode_with_colbert` already
   returns per-token vectors (`[n_valid, 1024]`), which looks like exactly the
   raw material late chunking wants. It is not: the ColBERT head is a separate
   linear projection, and pooling it lands **orthogonal** to the dense query
   space (−0.041). Chunk vectors built this way would be near-random against a
   dense query. Anyone reaching for the obvious API here will get silent garbage,
   not an error.

2. **The correct source is `last_hidden_state`, which the ONNX export does not
   emit.** The ONNX session returns exactly three outputs — dense, sparse,
   ColBERT. Production runs `RERANKER_BACKEND=onnx_int8` with an ONNX encoder, so
   late chunking requires *either* a new ONNX export that also emits
   `last_hidden_state`, *or* running the PyTorch `XLMRobertaModel` path for
   ingestion. That is a real architectural decision, not a config flag, and it is
   the thing §6.3 quietly assumed away.

3. **BGE-M3 is CLS-pooled; late chunking is mean-pooled.** The published recipe
   (Jina) mean-pools token vectors, and jina-embeddings is mean-pooled natively
   so query and chunk stay in one space. BGE-M3 is not: its dense vector is the
   normalized CLS token (confirmed at 0.914 against the live encoder). Mean
   pooling therefore sits ~0.70 from the query space — a *systematic* offset, not
   noise, so relative ranking may well survive it. But it means late-chunked and
   CLS-chunked vectors **cannot coexist in one collection**, and queries should
   probably be mean-pooled too. That is a bake-off question (§8.5), not something
   to settle by argument.

**Status: not built.** The measurements above are the go/no-go evidence; the
build is gated on decision (2) above. Cost is no longer "zero extra inference" —
it is zero extra *LLM* calls, plus an encoder-path change.

### 6.4 Deduplication — byte-exact is leaving most duplicates on the table

Empirical comparison on real corpora: byte-exact dedup catches **5.81%** of
duplicates, MinHash-LSH catches **31.32%**
([arXiv:2605.09611](https://arxiv.org/pdf/2605.09611)). MinHash-LSH is the
production standard behind C4, RefinedWeb, RedPajama, and FineWeb.

This corpus is unusually duplicate-prone: the gurus deliver the same core
teachings across hundreds of talks. Near-duplicate chunks do not merely waste
space — they **crowd the top-k by sheer count**, so one heavily-repeated teaching
can monopolise retrieval and starve the specific answer a seeker asked for.
Deduplicate at ingest, and keep the highest-`authority_tier` copy.

#### 6.3.2 Derived stores — audited 2026-08-01, rebuild DECIDED

The corpus audit covered `spiritual_wisdom` only. The stores *built from* it were
never checked, and they are worse than the source:

| Store | Points | Contaminated |
|---|---|---|
| `lightrag_vdb_chunks_*` | 770 | **41.4%** |
| `lightrag_vdb_entities_*` | 1,638 | 7.6% |
| `lightrag_vdb_relationships_*` | 1,922 | 1.4% |
| Neo4j (curated ontology) | 184 named / 8,745 nodes | **0** ✅ |

Extraction did not merely copy the poison, it **laundered it into schema**: the
graph holds an entity literally named `"Kan Kan Kan"` (an ASR decoder loop,
described as "a repeated word within the data") and a relationship node
`"Punctuation Transcription Errors"`. A transcription *defect* became a concept
with a name, a description, and edges — and graph traversal can return it as a
"related concept" to a seeker's question.

Two further findings:

- **Coverage, not just contamination.** `lightrag_vdb_chunks` holds 770 points
  against a corpus of 89,061 — **0.86%**. `KNOWLEDGE_GRAPH_QUERY_ENABLED` is
  justified in CLAUDE.md by Neo4j's edge count (accurate: 8,745 nodes / 13,300
  rels), but that number says nothing about LightRAG's coverage. Every query pays
  traversal latency for a retrieval graph that sees under one percent of the
  teaching.
- **Neo4j is regenerable.** `backend/scripts/seed_neo4j_okf.py` holds the 5-node
  ontology literally and emits a checked-in `seed_neo4j_okf.cypher` (219 lines).
  Despite the name it does **not** read `memory/okf/` at runtime — "OKF" there is
  the ontology *schema*, not the doctrine bundle. Deleting Neo4j loses nothing
  that git cannot restore.

**Decision (operator, 2026-08-01): once the green Qdrant collection is stable,
delete and re-ingest both Neo4j and LightRAG.** Sequencing matters:

1. Green `spiritual_wisdom_contextual` built and passing the boundary gate.
2. Rebuild LightRAG **from green**, never from blue.
3. Reseed Neo4j from `seed_neo4j_okf.py`.
4. Re-audit both with the same `find_artifact` gate; target < 1%.

**The rebuild must gate the extractor's *input*, not just its output** — an
extraction LLM handed noise will always emit a well-formed entity for it
(lesson #23). Without an input gate the rebuild re-creates "Kan Kan Kan" from a
clean corpus's remaining edge cases. Fix coverage in the same pass: a graph over
0.86% of the corpus is not the asset the config note assumes.

### 6.4.1 Measured on the live corpus (2026-08-01) — the premise above was wrong

Full-corpus run over all 89,061 `spiritual_wisdom` chunks
(`benchmarks/reports/dedup_measurement_20260801.json`; cross-validated by
re-running the same workload through the production `LSHNearDupIndex` API,
which returned an identical 20.29%):

| Metric | Measured | Plan assumed |
|---|---|---|
| Total duplicate rate | **20.29%** (18,071) | — |
| **Cross-source** near-dup | **0.38%** (335) | ~31% (the whole rationale) |
| Same-source duplicates | **19.9%** (17,736) | not considered |
| Gold-source chunks lost to a non-gold source | **1** of 89,061 | must be 0-ish ✅ |

**The cross-source hypothesis is false for this corpus.** The 31.32%-vs-5.81%
figure comes from web-scale corpora (C4/RefinedWeb/FineWeb), where the same
document is re-hosted across domains. Here, 95.8% of duplicate groups
(2,044 of 2,134) never leave a single `source_url`. MinHash-LSH banding is
still the right structure — it is what made a 20% measurement possible in 111s
— but it earns its place by cutting embedding + contextualiser-LLM cost and
top-k crowding, **not** by cross-source curation.

**Root cause of the same-source 19.9% — a writer failure loop, not duplication.**
14,292 redundant copies trace back to just 2,134 distinct texts. The worst
groups are 227, 222, and 195 identical copies, each sharing one `source_url`,
one `parent_id`, and *consecutive* `chunk_index` values. Their content is
degenerate — e.g. `"source topic power of observation the streets are the way
we are"`: a contextual-header remnant plus a chain-of-thought topic label, with
no teaching in it at all.

So dedup here is a **backstop over an ingestion bug**, and the green build must
fix it upstream. Two consequences:

1. A per-chunk quality gate structurally **cannot** catch this.
   `has_repetition_loop` detects an n-gram loop *within* one chunk; a loop that
   emits the same chunk 227 times in a row is invisible to it. The prevention
   gap is at batch level.
2. `services/qdrant/indexer.py:upsert_chunks` already receives the whole batch
   and already gates it on quality (`select_clean`), but does **no** dedup —
   which is exactly how 227 copies were written. The batch-level guard belongs
   there, alongside the existing filter. Tracked in §7.

Threshold `0.85` is validated, not assumed: at that setting exactly **one**
gold-source chunk in 89,061 was dropped in favour of a non-gold source. The
0.80 similarity bucket holds 3,433 further chunks — available headroom, but
nothing currently justifies spending it.

**Short texts (<200 chars) are matched exactly, never by similarity.** Pairwise
Jaccard over the 41,951 short chunks in this corpus is 880M comparisons —
**~4.4 hours, measured** — and it is what hung the first two measurement
attempts. On a 2,500-chunk sample, exact matching catches 8.6% while
near-but-not-exact adds only **0.48%**. A dict lookup buys back the quadratic
for almost nothing. MinHash is not an alternative at that length: it is
variance-heavy below ~200 chars (a one-word change in a 245-char text scores
0.844, under the 0.85 bar).

### 6.5 Validation as a first-class stage, not a config option

The literature converges on **four independent failure layers** — syntax, schema,
semantic, distribution — and the guidance is explicit: *"teams that build
reliably on top of structured outputs treat output validation as a first-class
engineering concern rather than a configuration option"*
([FutureAGI](https://futureagi.com/blog/what-is-llm-input-output-validation-2026/),
[TianPan.co](https://tianpan.co/blog/2026-04-09-structured-output-failures-production-llm)).

Current coverage after the §2 fixes:

| Layer | Checks | Status |
|---|---|---|
| Syntax | valid JSON from the topic extractor | ✅ (fails closed) |
| Schema | topic is a short noun phrase | ✅ `clean_topic_label` |
| Semantic | text is teaching, not machine reasoning | ✅ `text_quality_filter` |
| **Distribution** | **artifact rate per source vs. baseline** | ❌ **missing** |

The distribution layer is what turns this from a fix into a system: a source
whose rejection rate jumps from 2% to 60% is a source whose LLM went off the
rails, and today that is invisible. Emit `chunks_rejected_total{reason,source}`
and alert on the delta.

### 6.6 Quarantine, never delete

Rejected chunks go to a dead-letter store, not `/dev/null`
([PipeCode](https://pipecode.ai/blogs/data-quality-frameworks-great-expectations-vs-dbt-tests-vs-soda-core)).
Two reasons: a rising rejection rate on known-clean input is the only way to
detect an over-matching pattern **before** it deletes doctrine, and a quarantined
chunk can be re-admitted after a pattern fix without re-running ASR.

### 6.7 Gate every ingestion change on recall@k

Build a golden set of **50–200 real seeker queries** with the correct source
document(s) labelled, drawn from actual query logs. Then: *"Gate every retrieval
change on recall@k before touching prompts or LLMs"* and *"evaluate retrieval
separately from generation — conflating them makes it impossible to diagnose
which stage failed"*
([Data AI Hub](https://www.dataaihub.co/learn/retrieval-evaluation),
[Label Your Data](https://labelyourdata.com/articles/llm-fine-tuning/rag-evaluation)).

Recall@k is the binding constraint: **if the right chunk is not in the top-k, no
prompt and no model can recover it.** Every item in §6.1–6.4 is a hypothesis
about recall@k, and without this harness the whole plan is opinion. Build it in
Phase 1, before the re-ingest, so blue-vs-green in Phase 3 is a measurement
rather than a vibe.

### 6.8 Sequencing

```
Phase 1  golden set + recall@k harness      ← nothing downstream is measurable without this
         full-corpus audit + quarantine
Phase 2  ASR gate (6.1)      ← reject at source; everything after is cleaner
         dedup upgrade (6.4) ← before embedding, so you embed less
         late chunking (6.3) ← free with bge-m3; measure vs. baseline
         speaker enrollment (6.2)
Phase 3  shadow, compare recall@k blue vs green, atomic cutover
Phase 4  distribution-layer metrics (6.5) + quarantine review (6.6)
```

Do **not** reorder 6.1 ahead of the eval harness. Without recall@k you cannot
tell whether an aggressive ASR gate improved the corpus or silently deleted a
tenth of the teachings.

---

## 7. Every write path is now gated — LANDED 2026-08-01

The original fix gated `ingest/pipeline.py:_embed_and_upsert`. An audit of every
Qdrant writer found that was **one path of four**:

| Writer | Route | Was gated? |
|---|---|---|
| `ingest/pipeline.py:2261` | `QdrantService.upsert_chunks` | ✅ |
| `ingest/raptor.py:118` | `QdrantService.upsert_chunks` | ❌ writes **LLM-generated summaries** |
| `ingest/contextual_reingest.py:507` | raw `client.upsert()` | ❌ **this is the migration script** |
| `ingest/video_pipeline.py:223` | raw `.upsert("mukthi_guru", …)` | ❌ different collection |

Plus four standalone scripts that build chunks themselves and never touch
`IngestionPipeline` at all: `ingest_four_sacred_secrets.py`,
`ingest_pageindex_json.py`, `ingest_structure_to_qdrant.py`,
`smart_extract_and_ingest.py`.

**The migration script bypassing the gate is the dangerous one** — the re-ingest
would have faithfully copied all 26,161 contaminated chunks into the clean
collection and accomplished nothing.

Fixed by moving the gate **down to the storage boundary**:

- `services/qdrant/indexer.py:upsert_chunks` — the chokepoint every
  `QdrantService` caller crosses. Covers the pipeline, RAPTOR, and every present
  and future script that uses the service. Filters by index so metadata, vectors,
  and sparse vectors stay aligned; returns the count *actually* written.
- `ingest/contextual_reingest.py` — gated directly, since it writes through the
  raw client.

Verified with a mocked client: a 4-chunk batch containing one LLM artifact and
one ASR decoder loop wrote **2** points, with payloads `["A","D"]` — metadata
still on the correct chunk. An all-poison batch wrote nothing and did not call
`upsert` at all.

**Still ungated:** `ingest/video_pipeline.py:223` writes raw to a separate
`mukthi_guru` collection. Out of scope for the teaching corpus, but it should
route through `QdrantService` rather than the raw client.

### 7.1 Batch-level repeat guard — LANDED 2026-08-01

The quality gate judges **one chunk at a time**, which is the wrong unit for a
generator loop. §6.4.1 found 227 identical copies under one `source_url`, one
`parent_id`, with consecutive `chunk_index` values — each copy individually
innocent, and `make_point_id` hashes `chunk_index`, so all 227 earned distinct
point ids and persisted. The signal exists only across the batch.

`upsert_chunks` already receives the whole batch, so the guard goes there:

- `services/text_quality_filter.collapse_repeats(texts, sources, metadatas=None)`
  returns `(keep_indices, repeats)` — the same index-preserving contract as
  `select_clean`, so vectors, metadata, and sparse vectors stay aligned.
- Keyed on `(normalized_text, source_url)`. The gurus repeat teachings across
  talks; that is doctrine and survives. The same text twice under **one** source
  is redundant by construction and collapses to the highest-authority representative
  (using `authority_tier` metadata when available).
- `is_repeat_alarm()` splits ordinary duplication from a loop: ≥5 copies of one
  text logs at **ERROR** and names the upstream writer as the thing to fix.

**Nothing is deleted or quarantined** — redundant copies are simply not written,
and the existing corpus is untouched.

Verified against live Docker Qdrant in a scratch collection: 228 chunks in
(227 looped + 1 real teaching) → **2 stored**, payload `chunk_index` 0 and 227,
confirming metadata still tracks its own chunk after the collapse. Unit-covered
by tests in `backend/tests/test_text_quality_filter.py` (run via `pytest backend/tests/test_text_quality_filter.py`).

**Defence in depth, deliberate:** the pipeline-level gate stays. It rejects
*before* embedding, so it also saves the embed cost; the storage gate guarantees
correctness for callers that skip the pipeline.

---

## 8. Which chunking strategy — the evidence

The instinct to "move to contextual chunking" is half right. The benchmarks say
the bigger wins are elsewhere.

### 8.1 What the benchmarks actually found

| Strategy | Retrieval recall | End-to-end accuracy | Source |
|---|---|---|---|
| Semantic | **91.9%** (best) | 54% | Chroma eval |
| Recursive character | lower | **69%** (best) | Vecta/FloTorch |
| Fixed-token recursive | — | 50% | clinical task |
| Adaptive | — | **87%** (p = 0.001) | same clinical task |

**The most important line in this table is that semantic chunking wins recall and
loses accuracy.** Topic-pure chunks retrieve beautifully and then starve the LLM
of surrounding context. Optimising recall@k alone would have led us to the worse
answer. ([Denser](https://denser.ai/blog/rag-chunking-strategies/),
[FutureAGI](https://futureagi.com/blog/evaluating-rag-chunking-strategies-2026/),
[Firecrawl](https://www.firecrawl.dev/blog/best-chunking-strategies-rag))

The adaptive-vs-fixed result (87% vs 50%) comes from a *clinical decision support*
task — a domain, like spiritual guidance, where a confidently wrong answer is the
failure that matters.

### 8.2 Transcripts are not documents

This corpus is ~100% spoken discourse. The guidance for that is specific and it
is not the generic document advice:

> *"For meeting recordings, deposition transcripts, customer support calls, and
> podcast episodes, there are no headers, and sentences are the only boundary
> that makes sense."*

Three rules follow:
1. **Sentence-boundary chunking** — never split mid-sentence.
2. **Speaker-aware chunking** — one speaker's turn should be contained in a chunk.
3. **Sliding overlap of 20–50%** for unstructured speech, far above document defaults.

### 8.3 Verdict for this corpus

**Keep the boundary chunker. It is already the right family.** `use_boundary_chunker`
is on and splits on sentence boundaries — exactly rule 1. Do not switch to pure
semantic chunking; it would trade 69% accuracy for 54%.

Four changes, in order of expected gain:

| # | Change | Current | Target | Why |
|---|---|---|---|---|
| 1 | **Overlap** | `overlap_sentences=1` ≈ **4%** | 20–25% | The single biggest gap vs. the transcript guidance. A teaching that straddles a boundary is currently retrievable from neither side. Note `rag_chunk_overlap=200` exists but the boundary path ignores it — an inconsistency worth resolving. |
| 2 | **Late chunking** | none | on | **Free with `bge-m3` (8192-token context).** Embed the document, pool per chunk; every chunk embedding carries document context with zero extra LLM calls, and [gains grow with document length](https://arxiv.org/pdf/2409.04701) — these are long discourses. |
| 3 | **Speaker-turn boundaries** | role labels exist, unused for chunking | prefer breaks at speaker change | Prevents a chunk containing half a seeker's question and half the guru's answer — which is how a question gets retrieved and quoted as doctrine. |
| 4 | **Chunk size** | 1500 chars ≈ **375 tokens** | ~512 tokens (~2000 chars) | 512 is the benchmarked sweet spot; current setting is slightly under. Lowest-confidence change — measure, don't assume. |

**Anthropic contextual retrieval (per-chunk LLM context) is item 5, not item 1.**
It costs one LLM call per chunk and — given what §1 established about LLM output
reaching storage — it is a new contamination surface. Do it *after* late chunking,
and only behind the same quality gate.

Every one of these is a hypothesis about recall@k **and** end-to-end accuracy.
Measure both: §8.1 is the proof that optimising recall alone picks the wrong
strategy.

---

### 8.4 `ekimetrics/adaptive-chunking` — candidate, not default

[github.com/ekimetrics/adaptive-chunking](https://github.com/ekimetrics/adaptive-chunking).
Published benchmarks are genuinely strong:

| Metric | Adaptive | LangChain recursive | Page splitting |
|---|---|---|---|
| Retrieval Completeness | **67.7** | 58.1 | 59.1 |
| Answer Correctness | **78.0** | 70.1 | 73.3 |
| Answered queries | **65/99** | 49/99 | 49/99 |

33% more queries answerable is the number worth chasing. Accepted at LREC 2026.
Intrinsic eval: 91.07% mean across five metrics over 33 documents / ~1.18M tokens.

**Three reasons it is a candidate and not the default:**

1. **Benchmarked on documents; our corpus is speech.** The package also accepts
   raw text and custom chunking callables — page parsers are optional — but the
   published benchmark contains **no speech/transcript validation**: its metrics
   are *Block Integrity*, *Reference Continuity*, *Size Compliance*, and it ships
   page-based splitting with PDF parsers. A YouTube transcript has no pages and
   no blocks — **the mechanisms producing its win largely do not exist in our
   data.** We must therefore assess the raw-transcript path ourselves and
   **replace or disable the page-specific metrics (Block Integrity, page-based
   splitting)** before trusting any win. Its 33 documents across 3 domains are
   document domains.
2. **Licence trap.** Core is MIT ✅, but `[coref]` is **CC BY-NC-SA 4.0
   (non-commercial)** and `[parsing]` is **AGPL-3.0 or Artifex Commercial** — both
   outside this project's "Apache-2.0 / MIT / Meta Community only" rule
   (`CLAUDE.md`, `LICENSE-EXCEPTIONS.md`). Before the bake-off, do not rely on
   the core package's MIT licence alone: **pin the upstream package version,
   generate and review its SBOM, and scan the complete resolved runtime
   dependency closure** against the allowed-licence rule. Install **core only**;
   explicitly disable the `[coref]` and `[parsing]` extras **and all LLM-based
   modes** so no non-commercial/AGPL code or LLM-output-to-persistence surface
   can be pulled in. Note the irony: coreference resolution is the extra that
   would help transcripts most — spoken discourse is dense with unresolved
   pronouns ("*this* is what I want you to see") — and it is the one we cannot
   legally use.
3. **Its "LLM regex chunking" mode generates chunking patterns with an LLM.**
   Per §1, that is another LLM-output-to-persistence surface. Gate it or avoid
   that mode.

Its *concept* — select the strategy per document — is well supported: adaptive
beat fixed-token 87% vs 50% (p = 0.001) on a clinical task. The concept is right
for us; the document-tuned implementation may not be.

### 8.5 The bake-off — decide from our data, not their benchmark

Run all four against the **same golden set** from §6.7. Score **recall@k AND
end-to-end accuracy** — §8.1 is the standing proof that optimising recall alone
selects the worse strategy.

| # | Candidate | Cost | Hypothesis |
|---|---|---|---|
| A | Boundary chunker + **overlap 20–25%** (from ≈4%) | free | Largest expected gain; pure config |
| B | Boundary + **late chunking** | free (bge-m3 8192 ctx) | Document context per chunk, zero LLM calls |
| C | **adaptive-chunking, core/MIT only** | new dependency | Strong published numbers, wrong data shape — test it |
| D | Boundary + **speaker-turn breaks** | small | Stops question/answer bleed across a chunk |

Rules:
- **Pre-declare the hard limits before evaluation** — a p50 latency ceiling, a
  p95 latency ceiling, and quality-gate compliance (write through §7). A
  candidate that fails **any** pre-declared limit is ineligible, whatever its
  accuracy or recall.
- Candidate B precondition — **RESOLVED 2026-08-01: candidate B stays in the
  plan.** Late chunking needs bge-m3's 8192-token context, and
  `services/embedding_service.py` now runs **BAAI/bge-m3 as the primary model**
  (ONNX INT8 path `gpahal/bge-m3-onnx-int8`, 1024-dim, tokenizer pinned to an
  immutable commit SHA); `all-MiniLM-L6-v2` remains only as the 384-dim
  emergency fallback (`sentence-transformers/all-MiniLM-L6-v2`, also pinned).
  Decision: **option (a) — bge-m3 is the corpus embedding model**, embeddings
  already flow through `services/embedding_service.py`, and the 384-dim
  fallback never writes to the corpus (it is a degraded-response path only).
  Residual risk to record in the bake-off: late chunking must be evaluated on
  the **ONNX INT8** encoder, not the PyTorch fp32 baseline — quantization must
  not degrade the pooling behaviour late chunking depends on. External
  embedding APIs remain forbidden (§8.1).
- Baseline first (current config), or the comparison is meaningless.
- Change **one** variable at a time; A and B are separable and both free.
- Among candidates that pass every pre-declared limit, a candidate wins only if
  it beats baseline on **both** metrics, or wins accuracy without materially
  losing recall.
- Record p50/p95 latency per candidate — a winner that doubles TTFT is not a winner.
- Whatever wins, it still writes through the quality gate (§7). No exceptions.

Expected outcome, stated in advance so we notice if we are fooling ourselves:
**A and B are the likely wins** because they address defects measured *in this
corpus* (4% overlap; long discourses losing document context). C is the
higher-variance bet. If C wins on our golden set, adopt it — that is what the
bake-off is for.

---

## 9. Pre-re-ingest: snapshot before you clear

Order matters. Do not clear anything until the snapshot is verified restorable.

1. **Snapshot Qdrant** — `scripts/ops/backup_qdrant.py`, or Qdrant's native
   snapshot API per collection. Snapshot `spiritual_wisdom` (89,061 pts) **and**
   `guru_tone_podcast` (157 pts — the only labelled speaker data in the system,
   and irreplaceable if lost).
2. **Verify the snapshot restores** into a throwaway collection and returns the
   expected point count. An unverified backup is not a backup.
3. **Snapshot Neo4j** (`scripts/ops/backup_neo4j.py`) — entity/relationship state
   is derived from the same poisoned chunks and will be re-derived.
4. **Do NOT `docker compose down -v`.** §3 records that this previously purged the
   `telemetry_data` volume and destroyed LightRAG's bookkeeping. Use
   `docker compose down` with no `-v`.
5. **Build green fresh, keep blue.** Do not clear `spiritual_wisdom` at all until
   green has passed the recall@k comparison and served shadow traffic. "Clear
   everything" is the *last* step of the migration, not the first.
6. **Snapshot `memory/okf/`** — it is git-tracked, so a commit is sufficient, but
   confirm `compiled.json` is current before the cutover.

---

## 10. The ≥99% accuracy target — what it actually requires

Stating the honest position: **≥99% is not currently measurable, let alone
achievable**, and no amount of tuning changes that until three things exist.

1. **A definition.** "Accurate" must mean something falsifiable — the standard
   decomposition is *groundedness* (every claim traceable to a retrieved chunk),
   *answer relevance*, and *context relevance*. A single "accuracy" number without
   these is unauditable.
2. **A golden set** (§6.7). 50–200 real seeker queries with labelled correct
   sources. Without it there is no denominator.
3. **A clean corpus.** With 30.2% contamination (26,913 contaminated chunks confirmed across the full corpus), the ceiling on groundedness is
   set by the corpus, not the model. **This is why the re-ingest gates the target.**

What the shipped work does buy:
- Faithfulness is now **measured** rather than stamped `1.0` on ~73% of traffic,
  so a real number exists for the first time.
- The four empty-context abstentions mean the system answers "I don't have that"
  instead of inventing — the correct behaviour when accuracy cannot be met.
- 30.2% (26,913 contaminated chunks) can no longer enter the corpus from any gated path.

Realistic sequence: clean corpus → golden set → measure → *then* set a target.
A 99% claim made before step 3 is a number, not a guarantee.

### Latency

The user constraint is "less latency" alongside higher accuracy. These trade off,
and the current design already spends latency in the wrong places:

- **Free wins:** late chunking (§8.2) adds **zero** query-time cost. The OKF
  threshold (§4.2) *reduces* prompt tokens by dropping irrelevant injected
  entries. Deduplication (§6.4) shrinks the candidate set.
- **Real cost:** adding a reranker to the fast path. Mitigate with the ONNX INT8
  reranker already in the codebase (`RERANKER_BACKEND=onnx_int8`) rather than the
  PyTorch cross-encoder.
- **Wasted latency to reclaim:** `KNOWLEDGE_GRAPH_QUERY_ENABLED` puts a LightRAG
  traversal inside the retrieval `asyncio.gather`, so every query waits on it up
  to `LIGHTRAG_RETRIEVAL_TIMEOUT` while Qdrant returns in ~150ms — and §3 records
  that LightRAG's stores are **empty**, so it currently returns nothing. That is
  pure latency for zero signal until the stores are rebuilt.

Measure p50/p95 per stage before optimising. The largest latency line item today
is almost certainly a timeout on an empty store, not the model.

---

## 11. Sources

- [Anthropic — Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- [TianPan.co — JSON Mode Won't Save You: Structured Output Failures in Production LLM Systems](https://tianpan.co/blog/2026-04-09-structured-output-failures-production-llm)
- [Qdrant — Migrate to a New Embedding Model](https://qdrant.tech/documentation/tutorials-operations/embedding-model-migration/)
- [Vector Database Reindexing Pipeline](https://medium.com/@kandaanusha/vector-database-reindexing-pipeline-87efa1d1cd19)
- [Version Your Vectors — Index Versioning in RAG Observability](https://safjan.com/version-your-vectors-index-versioning-as-the-missing-layer-in-rag/)
- [PipeCode — Great Expectations vs dbt Tests vs Soda Core](https://pipecode.ai/blogs/data-quality-frameworks-great-expectations-vs-dbt-tests-vs-soda-core)
- [Unstructured — Data Governance: Your Path to Quality Transformation](https://unstructured.io/insights/data-governance-your-path-to-quality-transformation)
- [Databricks — Build an unstructured data pipeline for RAG](https://docs.databricks.com/aws/en/agents/tutorials/ai-cookbook/quality-data-pipeline-rag)
- [Google Cloud — Open Knowledge Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)

**ASR quality / hallucination**
- [Investigation of Whisper ASR Hallucinations Induced by Non-Speech Audio (arXiv:2501.11378)](https://arxiv.org/pdf/2501.11378)
- [Whisper Hallucination Detection and Mitigation via Hidden Representation Steering and Sparse AutoEncoders (arXiv:2606.07473)](https://arxiv.org/abs/2606.07473)
- [Whisper-CD: Accurate Long-Form Speech Recognition using Multi-Negative Contrastive Decoding (arXiv:2603.06193)](https://arxiv.org/html/2603.06193v1)
- [pyannote-audio — diarization of known speakers (enrollment)](https://github.com/pyannote/pyannote-audio/discussions/1667)

**Chunking**
- [Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models (arXiv:2409.04701)](https://arxiv.org/pdf/2409.04701)
- [Jina — Late Chunking in Long-Context Embedding Models](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- [Milvus — Late chunking with Jina Embeddings v2](https://milvus.io/blog/smarter-retrieval-for-rag-late-chunking-with-jina-embeddings-v2-and-milvus.md)

**Deduplication**
- [Byte-Exact Deduplication in RAG: A Three-Regime Empirical Analysis (arXiv:2605.09611)](https://arxiv.org/pdf/2605.09611)
- [SEDD: Scalable and Efficient Dataset Deduplication with GPUs (arXiv:2501.01046)](https://arxiv.org/pdf/2501.01046)
- [Zilliz — Data Deduplication at Trillion Scale](https://zilliz.com/blog/data-deduplication-at-trillion-scale-solve-the-biggest-bottleneck-of-llm-training)

**Validation / evaluation**
- [FutureAGI — What is LLM Input/Output Validation? The 2026 Explainer](https://futureagi.com/blog/what-is-llm-input-output-validation-2026/)
- [Data AI Hub — Retrieval Evaluation for RAG: Metrics Guide](https://www.dataaihub.co/learn/retrieval-evaluation)
- [Label Your Data — RAG Evaluation: 2026 Metrics and Benchmarks](https://labelyourdata.com/articles/llm-fine-tuning/rag-evaluation)
- [RAG Evaluation in the Era of LLMs: A Comprehensive Survey (arXiv:2504.14891)](https://arxiv.org/html/2504.14891v1)

**Chunking strategy benchmarks**
- [Denser — RAG Chunking Strategies 2026: 8 Methods Compared](https://denser.ai/blog/rag-chunking-strategies/)
- [FutureAGI — Evaluating RAG Chunking Strategies 2026](https://futureagi.com/blog/evaluating-rag-chunking-strategies-2026/)
- [Firecrawl — Best Chunking Strategies for RAG (and LLMs) in 2026](https://www.firecrawl.dev/blog/best-chunking-strategies-rag)
- [Digital Applied — RAG Chunking Strategies: A 2026 Retrieval Playbook](https://www.digitalapplied.com/blog/rag-chunking-strategies-2026-retrieval-quality-playbook)
- [Cohere — Effective Chunking Strategies for RAG](https://docs.cohere.com/page/chunking-strategies)
- [Microsoft Learn — Develop a RAG Solution on Azure: Chunking Phase](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-chunking-phase)
