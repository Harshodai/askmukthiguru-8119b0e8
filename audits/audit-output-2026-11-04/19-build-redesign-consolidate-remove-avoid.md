# 19 — What to build, redesign, consolidate, remove and avoid

Owner: lead. The full component decision table is in `17` §4. This page is the short version for decision-makers.

## 1. Build (new, because a measured need exists)

| Build | Need | Task |
|---|---|---|
| Offline PR evaluation suite | Today no quality signal blocks a merge (EVAL-003) | T2-01 |
| Outcome events and the "useful answer" metric | Cannot tell HTTP 200 from a useful answer (SYS-011) | T2-03 |
| Held-out, human-labelled golden set | No independent labels exist (EVAL-002) | T2-04 + human work |
| Route-decision service with one scope file | Scope defined three times; core topics misrouted (AI-001, ANS-003) | T4-03 |
| Topic-vs-state distress discriminator | The most common emotional questions get a template (ANS-001) | T4-04 + clinician |
| Postgres source registry with `takedown()` | No authority for lineage, rights or deletion (DATA-07) | T3-06 |
| Private evidence store and source bundle | Rights, sign-offs and the corpus cannot be verified or rebuilt (DATA-01, GURU-005) | T3-09 + owner |
| AnswerPlan, layered composer and verifier (flagged) | One clip cannot answer most questions (ANS-004) | T5-01, T5-03, T5-04 + owner decision |
| Seeker clip report, save and revisit | No correction channel; no continuity (PRD-006) | T6-04 |
| Railway staging with smoke and real-model load tests | Nothing deployed since August (SYS-007) | T9-01, T9-02 |

## 2. Redesign

| Redesign | From → To | Task |
|---|---|---|
| Teaching lane | 2,145-line sync function with 3 LLM gates → async steps with one evidence-judge call | T7-01, T4-06, T7-02 |
| Retrieval order and fusion | Dedup before gates, dense-only → gates first, hybrid RRF | T4-01, T4-02 |
| Release gate | File presence → verified provenance by hash | T1-11 |
| Hash fields | One ambiguous `transcript_hash` → `video_transcript_sha256` + `span_text_sha256` | T3-03 |
| Corpus builder | Add-only, snapshot after write → per-video replace, snapshot first | T3-04 |
| Memory use | Read and ignored → consented continuity (no repeated clips, follow-up offers) | T6-02 |

## 3. Consolidate

| Consolidate | From → To | Task |
|---|---|---|
| LLM provider modules | ~14 → one gateway | T7-03 |
| Caches | ≥8 → 2–3 versioned tiers | T7-04 |
| Memory planes | 7 → canonical memory | T6-01 |
| Teacher registries | 7 + 2 vocabularies → `gurus.yaml` | T8-01, T3-07 |
| Prompts | 37 constants + 72 inline → versioned registry | T5-07 |
| Vector schemas and engines | 3 → `fp-context` vNext | T7-06 |
| First-person surfaces | Chat bridge + Teacher's Words page → one contract | T5-03 |
| Agent documentation | 11.2 MB of markdown → one short status file plus guards | T1-15 |

## 4. Remove

| Remove | Why | Task | Owner decision needed? |
|---|---|---|---|
| Public teaching text, transcripts, teacher audio, data backups | Exposure (P0) | T0-02 | Yes (history rewrite) |
| Quote-weaver editorial/hybrid LLM paths | Rewrite teacher words (latent P0) | T1-02 | No |
| Ingestion first-person dual-index | Fabricated provenance (latent P0) | T1-02 | No |
| `REFERENCE_VOICE` | Health claims in a serving module | T1-02 | No |
| Unsourced teacher attributions | Misattribution risk | T1-03 | No |
| Sadhguru / ISKCON / "SKY private teachings" seeds and personas | No corpus, no rights | T1-04 | Confirm |
| Churn funnel and win-back emails | Dark pattern at deletion | T1-12 | Confirm |
| Repo-root shims, `langdetect` stub, dead WhatsApp signer | Shadowing and dead code | T1-13 | No |
| Memgraph, LightRAG, atomic GraphRAG from serving and deploy | No measured value; no provenance | T3-11 | Yes (ADR-005) |
| Generating graph from chat serving | Fail-open target; not the product | T7-06 | Yes (ADR-002) |
| Semantic cache on teaching answers | Staleness and personalisation risk | T7-04 | No |
| `ToneAdapterStage` and dormant modules listed in root `CLAUDE.md` | Unreachable or no-op | after T7-06 | Yes (root `CLAUDE.md` currently forbids it) |
| `personalization/unified_engine.py`, `memory/episodic.py` | No importers | T6-01 | No |

## 5. Avoid

| Avoid | Reason |
|---|---|
| Generating any text in a teacher's first person, for any reason | Impersonation. It also destroys the trust conversation with the teachers. |
| Adding retrieval techniques (HyDE variants, ColBERT, graph expansion) before the frozen bank and held-out set exist | Nothing can prove they help. Months were spent this way [DOC-CLAIM task list §1]. |
| Another plan or audit file in the repository | Docs sprawl is a root cause (RC-8). Update the one status file. |
| Tuning on AI-written labels or the tuning set | Invariant 3; EVAL-002 |
| Declaring "ready" without the command that computed it | RC-2 |
| Engagement mechanics: streaks tied to progress, guilt notifications, win-back at deletion | Mission rule; UX-001, UX-002 |
| New microservices, a second vector DB, a graph DB, agent frameworks | No measured need (`17` §6) |
| Merging to `main` before required checks pass | X-02 |
| More than one agent session writing to one working tree | Recorded contamination incident [DOC-CLAIM task list §1.7] |

## 6. Decision register: do not build, and freeze

Evidence labels per `CONVENTIONS.md`. "Freeze" means: keep running if it is live, but add no features until the stated evidence exists.

| # | Item | Category | Decision | Why | Evidence | Revisit when |
|---|---|---|---|---|---|---|
| N-01 | Kubernetes manifests, Helm charts, 10k/100k-user SPOF tiers | Premature scalability | Do not build further; archive | No deploy exists; one Railway environment is enough at pilot scale | `infrastructure/k8s/` (41 files under `infrastructure/`); root `CLAUDE.md` SPOF table [V-STATIC] | Sustained load above the staging capacity measured in T9-02 |
| N-02 | Multi-AZ Redis, Qdrant and graph clusters | Premature scalability | Do not build | No production traffic baseline | `04` §4 | After 3 months of production metrics |
| N-03 | A second mobile codebase (`mobile/expo/`) beside Capacitor (`android/`, `ios/`) | Duplicate infrastructure | Choose one; freeze the other | Two apps double the release surface; the store work is not ready | `mobile/expo/` 12 files; `docs/MOBILE_RELEASE_RUNBOOK.md` [V-STATIC] | Web beta exit |
| N-04 | WhatsApp bot | Feature with unproven value | Freeze | Disabled by policy; PR #91 closed unmerged; separate SQLite memory (ADV-06) | `whatsapp_bot/`; `03` [V-GIT] | Web beta shows demand; consent model ready |
| N-05 | Memgraph, LightRAG, GraphRAG communities, ontology guardrails on the serving path | Redundant retrieval / unnecessary DB | Remove from serving (ADR-005) | No measured lift; no span provenance; 41.4% contamination [DOC-CLAIM] | `08` RET-05 | An ablation on the held-out set shows lift |
| N-06 | RAPTOR summaries, contextual re-ingest, proposition chunking for teaching content | Unnecessary complexity | Do not apply to the teaching corpus | Summaries are not verbatim; they cannot be shown as teacher voice | `06`; PR #86 retired proposition chunking [V-GIT] | Never for teacher voice |
| N-07 | HyDE variants, query decomposition fan-out, ColBERT MaxSim, RAGatouille | Redundant retrieval | Do not enable | Nothing can prove benefit before the frozen bank and held-out set exist | `09`; `backend/CLAUDE.md` (ColBERT disabled) [V-STATIC] | T2-02 + T2-04 show headroom that these address |
| N-08 | Speculative generation, sentence buffer, claim verifier, federated 4-lane retrieval, streaming admission router | Dormant modules | Do not wire; delete after the graded run | They contradict invariants 1/15/21 or duplicate live paths | Root `CLAUDE.md` "Dormant modules" [V-STATIC] | Owner decision D-18 |
| N-09 | Multi-agent answer graphs (debate, critique loops, reflection agents) for teaching answers | Unnecessary agents | Do not build | A fixed pipeline with one judge call is cheaper and deterministic | `17` §6 | Never for the teaching lane |
| N-10 | Semantic cache (GPTCache) for teaching answers | Unnecessary complexity / risk | Do not use for teaching | Personalisation leak and staleness risk; exact cache suffices | `15`; `17` §4 [V-STATIC] | — |
| N-11 | Extra LLM providers (Sarvam, Ollama, NIM) as parallel stacks | Duplicate infrastructure | Consolidate (D-17) | Three non-sharing classes; drift | `09` AI-005; `13` CQ-002 | — |
| N-12 | DSPy, Gradio, `chat_engine` | Dead or experimental | Remove (`13` removal register) | No live caller | `13` §3 [V-STATIC] | — |
| N-13 | Personas for other teachers; assistant switcher personas | Unnecessary abstraction / rights risk | Remove (T1-04) | No corpus, no rights, impersonation risk | `11` GURU-011 | Written permission from that teacher |
| N-14 | Second Brain vault, study notebooks, personal concept-map KG, flashcards (SRS) | Features with unproven value | Freeze | Built without user research; they compete with the core job of understanding a teaching | `03` feature map; `src/components/kg/KGConceptMap.tsx` (48 changes since July) [V-GIT] | User study (T2-07) shows use and value |
| N-15 | 20-week streak heatmap, milestone celebrations, daily ritual nudges | Engagement mechanics | Neutralise or remove (T1-12) | They tie usage to spiritual progress; the mission forbids that | `12b` UX-002 | — |
| N-16 | Inferred "spiritual profile" (L3 persona) and emotion-arc-driven interventions | Excessive personalisation | Do not build; replace with stated preferences | Privacy and dependency risk; consent bypass | `12` MEM-003, MEM-004 | — |
| N-17 | Healing courses with attributed paraphrases | Feature integrity | Freeze content; fix attribution (T1-03) | Unsourced attributions | `11` GURU-012 | Sourced from spans |
| N-18 | Fine-tuned LLMs or a fine-tuned reranker | Premature optimisation | Not yet | No independent labelled data | `18` EVAL-002 | ≥299 independent labels + a measured gap |
| N-19 | More CI workflows (21 today, 4 nightly red for configuration) | Process complexity | Consolidate to a small required set + nightly | Noise hides real failures | `01` §8.4; `15` [V-GIT] | — |
| N-20 | More Prometheus system metrics (87 today) | Observability noise | Add outcome metrics only | Usefulness is unmeasured; system metrics are not | `15` SYS-011 | — |
| N-21 | More plan, audit or lessons documents in the repository | Process complexity | Do not add; update one status file | Docs sprawl is a root cause | `01` X-07; `13` CQ-009 | — |
| N-22 | Machine translation of quotes presented as the teacher's words | Integrity | Never | Invariant 16; ADV-05 | `26` | — |
| N-23 | A general-purpose assistant mode for the faculty review or beta | Scope creep | Static boundary (ADR-002) | Leak target; not the product | `17` ADR-002 | User research shows need, with a visible mode switch |
| N-24 | In-app gold labelling by AI subagents | Integrity | Never | Labels must be independent and human | `18`; root `CLAUDE.md` invariant 3 | — |
