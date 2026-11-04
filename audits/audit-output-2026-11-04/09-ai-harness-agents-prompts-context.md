# 09 — AI harness, agents, prompts and context engineering

Owner: S3. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.

> **Erratum (lead, after the independent review in `26`).** Questions that do not match `_ON_TOPIC_RE` are **not** sent to the general lane by default. Any question that is not classified off-topic goes to the teaching lane (`off_topic_stage.py:591-607`). Only questions that combine a general-task word with an emotion word take the general exit (`:625-669`). The triple scope definition (AI-001) is still real, but its impact is smaller (now P2). The general-mode voice block (AI-003) tells the model "how, not what" and forbids invented first-person sentences (`register.py:229-236,292`). It is still a risk to remove (T1-06), at P2. New P1 path: **turning the first-person bridge off** sends teaching questions to the generating prompt (ADV-03).
Line numbers were read at `main@46b808fb`. A range such as `:930-948` is approximate to about ±10 lines.
Related: `05` (S1, request flow and stages), `10` (answer behaviour), `14b` (safety), `15` (S1, cost and latency), `18` (evaluation).

## 0. Summary

| # | Statement | Label |
|---|---|---|
| 1 | The serving harness has two halves. A stage chain (17 stages) runs safety and routing. A LangGraph (Fast/Standard/Deep, 20+ nodes) runs either the first-person module or the general generating graph. | [V-STATIC] |
| 2 | Under the documented local config, a teaching question reaches 3 LLM calls on the first-person lane (rerank, answerability, relevance). None writes answer text. | [V-STATIC] |
| 3 | The general generating graph (HyDE, grading, generation, reflection, verification) still runs for general-mode questions, MODERATE distress (Standard strategy) and personalise turns. | [V-STATIC] |
| 4 | Prompts are spread across ~37 named constants and ~72 inline system prompts in 33 files. There is no prompt registry and no prompt version on serve-time calls. | [V-STATIC] |
| 5 | Two parallel LLM provider stacks exist (`services/*_service.py` and `services/llm/*_provider.py`) behind a gateway. The container attribute `ollama` holds the OpenRouter provider. | [V-STATIC] |
| 6 | Model routing is static by role (fast, classify, generation, scorer). It is not routed by intent or complexity on the first-person lane. | [V-STATIC] |

---

## 1. Harness topology

### 1.1 Stage chain

Order from `backend/app/pipeline/stages/pipeline_builder.py:47-95`:

`KillSwitch → CacheCheck → RequestState → InputGuardrail → Distress → CircuitBreaker → DoctrineCache → CasualShortCircuit → OffTopic → BoundedComparison → Personalize → Graph → MeditationGen → Translation → ToneAdapter → OutputGuardrail → Memory → CacheUpdate → ResultAssembly`

Note: root `CLAUDE.md` "Pipeline" lists a different order (no KillSwitch, no OffTopic, Distress after InputGuardrail but CircuitBreaker earlier). The builder is the truth. S1 owns the full stage audit (`05`).

### 1.2 Graph entry and modules

| Element | File | Behaviour |
|---|---|---|
| Registry | `backend/rag/pipeline_registry.py` | Two modules: `first_person` (priority 10) and `general` (100). Static topology, live predicates. |
| `first_person` enabled | `_first_person_enabled` → `first_person_bridge_enabled()` | True when `first_person_chat_bridge_enabled`, `first_person_route_enabled` and `first_person_mode != "disabled"`. Defaults make it True. |
| `first_person` claims | `_first_person_claims` | False for personalise turns and `general_knowledge_mode`. True for `domain_route=="teaching"`. Else `is_spiritual_domain_query(question)`. Import failure → False (fails toward general). |
| First-person node | `backend/rag/nodes/first_person.py` | Calls `run_first_person_bridge(ctx)`. A result → END; None → re-enter `parallel_start`. |
| Strategies | `backend/rag/graph_strategies.py`, `rag/graph_builder.py:36-40` | `fast`, `standard`, `deep`. Tier comes from cache-stage preclassification or on-device intent (`app/pipeline/stages/graph_stage.py:290-400`). |

### 1.3 Standard strategy nodes (general graph)

`intent_router ∥ handle_distress_check → resolve_parallel → {handle_distress | handle_meditation | handle_casual | web_search | resolve_followup}` → `navigate_and_hyde` → `retrieve_documents` → (`agentic_graph_traversal` if COMPARATIVE and flag) → `rerank_documents` → `grade_documents` → `cross_teacher_reasoning` → {`enrich_context` → `context_engineer` → `generate_answer` → `reflect_on_answer` → `verify_answer` → `extract_citations` → `format_final_answer` | `rewrite_query` | `handle_fallback` | `handle_distress`}. General-knowledge mode skips from `retrieve_documents` straight to `context_engineer`. Evidence: `rag/graph_strategies.py:290-440`.

### 1.4 First-person lane (inside the bridge)

`_bridge` (`app/pipeline/stages/first_person_bridge.py:660-1110`): distress gate → meditation carve-out → synthesis/relationship/addiction boundary → self-harm cue notice → follow-up concatenation → embed → optional HyDE → `FirstPersonPipeline.execute` (`services/first_person_pipeline.py:3509`): crisis pre-check (`:3546`), topic rail (`:3574`), serving-contract gate (`:3592`), exact cache (`:3620`), compound decomposition (`:3678`), v10 context harness (`:3762`, flag), retrieval (`:4498`), integrity gate (`:4742`), cross-encoder reorder (`:4929`, flag), LLM rerank (`:4960`), teacher diversity (`:5015`), abstain on zero (`:5081`), confidence decision (`:5107`), relevance and answerability gates.

---

## 2. LLM call sites (serve time)

"A" = live under code defaults. "B" = live under the documented local config (root `CLAUDE.md` invariants 21, 24). Models: `openrouter_fast_model` and `openrouter_classify_model` = `meta-llama/llama-3.1-8b-instruct`; `openrouter_generation_model` = `deepseek/deepseek-chat`; fallback `meta-llama/llama-3.3-70b-instruct` (`app/config.py:596-599`).

| # | Call site | Purpose | Model | Prompt | max_tokens / timeout | A | B |
|---|---|---|---|---|---|---|---|
| 1 | `services/first_person_pipeline.py:1450-1470` `_verify_answerability_async` | YES/NO in-scope check | fast (via `_generate_fast`) | `_ANSWERABILITY_SYSTEM_PROMPT` (`:1329`) | 16 / gate budget 6 s [DOC-CLAIM inv. 22] | Yes | Yes |
| 2 | `first_person_pipeline.py:1023-1103` `_relevance_select_scored` | Score top-3 clips 0–3 | `first_person_relevance_model` or generation model when empty | `_RELEVANCE_SYSTEM_PROMPT` (`:791`) / JSON variant (`:826`) | 16 (default) or 1024 (Haiku) / `first_person_relevance_timeout_s=25.0` (`config.py:480`) | Yes (deepseek) | Yes (Haiku 5.5) |
| 3 | `first_person_pipeline.py:1199-1242` `_llm_rerank_clips` | Reorder clips (indices only) | provider default | inline | — / 2.5 s | Yes (`first_person_llm_rerank_enabled=True`, `config.py:247`) | Yes |
| 4 | `first_person_pipeline.py:875-979` `_relevance_select_jev` | Optional picker | Jev router model | inline | — / `jev_timeout_s` | No (`first_person_relevance_jev_enabled=False`, `config.py:1985`) | No |
| 5 | `first_person_bridge.py:818-845` HyDE | Hypothetical teaching for retrieval | provider | `generate_hyde` | — / 2.5 s | No (`first_person_hyde_enabled=False`) | No |
| 6 | `services/first_person_context_selector.py:21` | v10 span selector | `first_person_context_selector_model` | `_SELECTOR_SYSTEM_PROMPT` | — | No (flag False) | No |
| 7 | `services/quote_weaver.py:1046-1154`, `:1310-1333` | Framing scaffold / editorial rewrite | `first_person_scaffold_model` | inline scaffolding + "Elite Spiritual Manuscript Editor" | 160 | No (`first_person_mode="retrieval_only"` → deterministic, `quote_weaver.py:1414-1420`) | No |
| 8 | `rag/nodes/intent.py:1047`, `:1090`, `:1102` `intent_router` | Intent + complexity | classify / Jev | `INTENT_AND_COMPLEXITY_PROMPT` (`rag/prompts/guardrails.py:69`) | — | General graph only | General graph only |
| 9 | `rag/nodes/retrieval.py:905-1045` `navigate_and_hyde` | Decompose + HyDE | fast/generation | `DECOMPOSE_QUERY_PROMPT`, `HYDE_PROMPT` (`rag/prompts/rag.py:96`, `:134`) | — | General graph | General graph |
| 10 | `rag/nodes/reranking.py:272`, `:393` `grade_documents` | Batch relevance grading | classify | `BATCH_GRADE_PROMPT` (`rag.py:154`) | — | General graph | General graph |
| 11 | `rag/nodes/generation.py:2632` `generate_answer` (`:3398-3547`, `:3690-3709`) | Answer generation | generation (+ fallback; `krutrim` branch) | `GURU_SYSTEM_PROMPT` or `build_general_system_prompt` + voice register | budgeted | General graph | General graph |
| 12 | `rag/nodes/verification.py:381` `reflect_on_answer`, `:1228-1262` | Self-check sub-questions | provider | inline | — / 8 s | General graph | General graph |
| 13 | `rag/nodes/intent.py:1409-1416` | Casual reply | gateway / provider | `CASUAL_SYSTEM_PROMPT` (`system.py:236`) | — | When not short-circuited | Same |
| 14 | `rag/nodes/short_circuit.py:181` | Short-circuit rewrite | gateway | inline | — | General graph | General graph |
| 15 | `rag/resolve_followup.py:135` | Follow-up resolution | provider | `RESOLVE_FOLLOWUP_PROMPT` | — | General graph | General graph |
| 16 | `services/serene_mind_engine.py:1890-1915` | Stage-2 distress classifier (below MODERATE, only if level>NONE or recent distress) | provider `classify_distress_structured` | `DISTRESS_CLASSIFICATION_SYSTEM_PROMPT` (`:1037`) | — | Conditional | Conditional |
| 17 | `app/pipeline/stages/distress_stage.py:169`, `:520-635` | LLM downgrade / escalation | provider | `_ESCALATION_SYSTEM_PROMPT` | — / 4 s | No (`config.py:1637`, `:1650`) | No |
| 18 | `app/pipeline/stages/off_topic_stage.py:440-470` | Ambiguous-domain router | Jev | — | — / 0.45 s | Ambiguous spiritual candidates only | Same |
| 19 | `app/pipeline/stages/meditation_gen_stage.py:103` | Teaching-infused meditation rewrite | provider | `MEDITATION_INFUSION_PROMPT` (`system.py:390`) | — / 60 s | When proactive Serene Mind + citations | Same |
| 20 | `app/pipeline/stages/guardrail_stage.py:210-468`, `cache_stage.py:376`, `:454` | Translation of non-quote text | translation provider | provider prompts | — | Indic users | Indic users |
| 21 | `guardrails/llama_guard_handler.py:41`, `:144` | Llama Guard | `meta-llama/llama-guard-3-8b` | `_PROMPT_TEMPLATE` | — | Only if `guardrails_provider="llama_guard"`; default is `"nemo"` with lightweight fallback (`config.py:575`, `guardrails/chain.py:24-62`) | [LIVE-L] |
| 22 | `app/orchestrator_utils.py:151` `CLASSIFY_COMPLEXITY_PROMPT`; `app/core/refiner.py:73-84` | Complexity / refine | provider | inline | — | Path-dependent | [LIVE-L] |

Per-request count for "What is the cause of my anxiety?": config A → 0 LLM calls in Fast, 2+ in Standard (calls 9, 10, then discarded; see AI-002). Config B → calls 1–3 (and 0 if the exact cache hits). [V-STATIC]

### 2.1 Provider stack

| Layer | Files | Note |
|---|---|---|
| Provider strategy | `services/llm/factory.py`, `services/llm/{openrouter,sarvam,ollama,nim}_provider.py` | Created by `app/container.py:61-70` `_create_llm_service` and stored as `container.ollama` (`:191`). |
| Legacy services | `services/openrouter_service.py` (1,878 lines), `sarvam_service.py`, `ollama_service.py` | `container.openrouter = OpenRouterService()` (`:237`) is the gateway secondary. |
| Gateway | `services/llm_gateway.py` (`app/container.py:347-360`) | Primary `container.ollama`, secondary OpenRouter, same-provider model fallback, coalescer. |
| Other | `services/gateways/anthropic_gateway.py`, `services/translation/*`, `krutrim` branch in `generation.py:3449` | Extra paths. |

Call sites use three entry points inconsistently: `_services._llm_gateway.generate`, `_services._ollama.generate`, `container.ollama.generate`. S1 owns de-duplication (`13`). Root `CLAUDE.md` "Gotchas" says the provider classes share no code; editing one does not fix the others.

---

## 3. Prompt inventory

### 3.1 Counts

| Measure | Value | Method |
|---|---|---|
| Named prompt constants (backend, non-test) | 37 in 21 files | `rg "_PROMPT\s*=|SYSTEM_PROMPT\s*="` |
| Inline system prompts in `app/ rag/ services/ guardrails/` | 72 occurrences, 33 files | `rg "system_prompt\s*=\s*(…)|\"role\": \"system\""` |
| Ingestion and offline scripts with prompts | 18 files (`ingest/`, `backend/scripts/`, `scripts/`) | `rg -l` |
| Prompt registry | None | — |
| Serve-time prompt version on calls | None, except `_SCAFFOLD_PROMPT_VERSION="v1"` (`quote_weaver.py:1207`) and a serving-policy fingerprint that hashes the answerability and relevance prompts (`first_person_pipeline.py:2885-2920`) | [V-STATIC] |
| `prompt_version_id` in telemetry | Column read by `app/telemetry_db.py:353-406`, `:1669-1760`; set only as a filter in `app/api/admin.py:80-89`; no serve-time writer found | [V-STATIC] |

### 3.2 Serve-time prompts (full inventory)

| Prompt | File:line | Responsibility | Inputs | Output | Invoked by | Live (B) | Conflicts / weaknesses | Required change |
|---|---|---|---|---|---|---|---|---|
| `_ANSWERABILITY_SYSTEM_PROMPT` | `services/first_person_pipeline.py:1329` | In-scope YES/NO | question only | 1 token | FP pipeline | Yes | Scope list differs from routing regex (`off_topic_stage.py:57`) → ANS-003. Reads question only, so cannot judge clip fit. | Single scope source shared with routing. Version it. |
| `_RELEVANCE_SYSTEM_PROMPT` / `_RELEVANCE_JSON_SYSTEM_PROMPT` | `first_person_pipeline.py:791`, `:826` | Score clips 0–3 | question + full clip texts | integers | FP pipeline | Yes | "3 = directly answers" is strict; served share 24–31% [DOC-CLAIM]. Model choice is env-only (AI-007). Clip text is untrusted input to the scorer. | Version; pin model in config; schema output for every model. |
| LLM rerank inline | `first_person_pipeline.py:1199-1242` | Order clips | question + clips | indices | FP pipeline | Yes | Duplicates the relevance scorer's job. | Merge with relevance scoring (one call). |
| `_SELECTOR_SYSTEM_PROMPT` | `services/first_person_context_selector.py:21` | v10 span selection | spans | ids | Harness | No | — | Keep dormant until measured. |
| Scaffolding prompt | `services/quote_weaver.py:1054-1076` | OPENING/CONNECTIVE/QUESTIONS | query + speaker labels + optional Memgraph doctrine | 3 fields | Weaver (hybrid mode) | No | Writes "Sri Krishnaji observes:" pointers; hardcoded names. | Remove or move to labelled L6 copy. |
| Editorial review prompt | `quote_weaver.py:1100-1154` | "Elite Spiritual Manuscript Editor" | clip texts | rewritten chapter | Weaver (hybrid + flag) | No | Edits teacher words; calls result "authentic". AI-006. | Remove. |
| `GURU_SYSTEM_PROMPT` + registry rule | `rag/prompts/system.py:122-184`, `build_guru_system_prompt` `:187-216` | Teaching-generation persona | evidence | answer | `generate_answer` | General graph | Well aligned with voice contract. ~1,940 tokens vs persona budget 2,048 (comment in `services/voice/register.py:327-329`). | Keep; shorten; version. |
| `GURU_VOICE_RULE` | `system.py:199-212` | Preserve-never-invent first person | — | — | Generation prompt branches | General graph | Good. | Keep. |
| Voice register blocks (`_CORE_RULES`, `_SHAPE_RULES`, "THE TEACHER'S VOICE — {display}") | `services/voice/register.py:212-334` | Style register | question, intent, docs | appended block | `_maybe_apply_langhanam_voice` (`rag/nodes/generation.py:1285-1335`) | General graph, including general mode | AI-003: teacher-style mimicry on assistant prose; conflicts with `GENERAL_ASSISTANT_SYSTEM_PROMPT` "Do not force a spiritual framing". | Apply only to L3 teaching explanations; never in general mode; rename to "assistant register". |
| `LANGHANAM_VOICE_BLOCK` | `services/guru_voice_langhanam.py:59-120` | Legacy register | — | — | Fallback when register fails | Fallback | Duplicate of register. | Remove. |
| `REFERENCE_VOICE` | `guru_voice_langhanam.py:15-35` | Benchmark reference | — | — | Benchmarks only | No | Paraphrased discourse with health claims inside a serving module. | Remove from serving code. |
| `GENERAL_ASSISTANT_SYSTEM_PROMPT` + `GENERAL_ANSWER_INSTRUCTIONS` | `system.py:47-90` | Neutral assistant | context, memory | answer | `generate_answer` (general mode) | Yes for general-mode questions | Receives grief/ego/attachment questions (ANS-003). | Keep for true general tasks only. |
| Inline "warm Guru" instruction block | `rag/nodes/generation.py:3195-3215` | Teaching answer rules | context | answer | `generate_answer` | General graph | "delivered as a warm, understanding Guru" is identity drift against `GURU_SYSTEM_PROMPT` ("You are not a teacher"). | Align wording with the voice contract. |
| `CASUAL_SYSTEM_PROMPT` | `system.py:236-249` | Small talk | message | 1–2 sentences | `intent.py:1409` | When greeting not short-circuited | Fine. | Keep. |
| `DISTRESS_PROMPT` | `system.py:251-370` | Distress acknowledgement | message | text | Generation branch | Limited (`handle_distress` uses templates) | Duplicates templates. | Keep one source (templates). |
| `MULTI_TURN_PROMPT` | `system.py:371` | Coherence rules | history | — | Generation | General graph | — | Merge into context builder. |
| `MEDITATION_INFUSION_PROMPT` | `system.py:390-440` | Rewrite meditation instructions | teachings + signals | JSON | `MeditationGenStage` | Conditional | AI-written text inside a "sacred, fixed" practice structure; not labelled as assistant-written in the response. | Label as L6/L4; review with teachers' team. |
| `INTENT_CLASSIFICATION_PROMPT`, `INTENT_AND_COMPLEXITY_PROMPT` | `rag/prompts/guardrails.py:21`, `:69` | Intent | message | label | `intent_router` | General graph | Second intent taxonomy next to regex routing and on-device intent. | One classifier. |
| `HYDE_PROMPT`, `DECOMPOSE_QUERY_PROMPT`, `QUERY_REWRITE_PROMPT`, `QUERY_TRANSFORMATION_PROMPT`, `IS_COMPLEX_QUERY_PROMPT`, `SUFFICIENCY_CHECK_PROMPT`, `TREE_NAVIGATION_PROMPT` | `rag/prompts/rag.py:82-229`, `:279` | Query planning | question | text | General graph nodes | General graph | Seven overlapping planners. | Consolidate into one planner prompt (§5). |
| `GRADE_RELEVANCE_PROMPT`, `BATCH_GRADE_PROMPT` | `rag.py:40`, `:154` | Doc grading | question + docs | labels | `grade_documents` | General graph | Duplicate of FP relevance scorer. | One relevance judge. |
| `FAITHFULNESS_CHECK_PROMPT`, `VERIFICATION_PROMPT`, `COMBINED_VERIFICATION_PROMPT`, `CITATION_REASONING_PROMPT` | `rag.py:50`, `:65`, `:168`, `:270` | Verification | answer + context | verdict | Verification nodes | General graph | Live faithfulness decision is LettuceDetect (root `CLAUDE.md`). LLM verifiers duplicate it. | Keep one verifier. |
| `HINT_EXTRACTION_PROMPT`, `SUMMARIZE_PROMPT`, `COMPACT_SUMMARY_SYSTEM_PROMPT`, `COMPRESS_CONTEXT_PROMPT` | `rag.py:105-134`, `:313` | Context ops | docs/history | text | Various | Path-dependent | Compression of teaching text risks paraphrase entering context unlabelled. | Mark machine summaries; never quotable. |
| `AGENTIC_TRAVERSAL_SYSTEM_PROMPT` | `system.py:18` | Graph walk | ontology | text | `agentic_graph_traversal` | Dead on live config (root `CLAUDE.md`) | — | Remove with the node. |
| `RESOLVE_FOLLOWUP_PROMPT` | `rag/resolve_followup.py:135` | Rewrite follow-up | history + question | question | General graph | General graph | FP lane uses a regex heuristic instead (ANS-007). | One follow-up resolver for both lanes. |
| `DISTRESS_CLASSIFICATION_SYSTEM_PROMPT` | `services/serene_mind_engine.py:1037` | Stage-2 distress | message | JSON | `async_assess_distress` | Conditional | Can only raise to MODERATE. | Keep; add topic-vs-state output (ANS-001). |
| `_ESCALATION_SYSTEM_PROMPT` | `distress_stage.py:169` | Escalate below crisis | message | level | Off | No | — | Clinician-gated. |
| `_PROMPT_TEMPLATE` (Llama Guard) | `guardrails/llama_guard_handler.py:41` | Safety classify | message | safe/unsafe | Chain | Config-dependent | — | Keep if provider used. |
| `CLASSIFY_COMPLEXITY_PROMPT` | `app/orchestrator_utils.py:151` | Complexity tier | message | tier | Graph selection | Path-dependent | Third complexity classifier. | Consolidate. |
| `PERSONALIZE_TEACHING_PROMPT` | `app/pipeline/stages/personalize_stage.py:71` | User-turn text for personalise | — | — | Personalize | Opt-in | — | Keep. |
| Layered memory prompts (`L1_SYSTEM_PROMPT`, L3 persona `_SYSTEM_PROMPT`) | `services/layered_memory/prompts.py:1`, `l3_persona_generator.py:14` | Memory extraction, persona | user turns | facts, persona | Celery tasks | When consented | L3 writes an LLM "spiritual profile" of the user (MEM-004). | See `12`. |
| Canonical memory extractor/judge prompts | `services/canonical_memory/extractor.py`, `judge.py` | Memory facts | turns | facts | Canonical integration | When `memory_write` + consent | Parallel to L1 extraction. | See `12`. |

### 3.3 Ingestion and offline prompt families (grouped)

| Family | Files | Count | Feeds | Risk |
|---|---|---|---|---|
| Transcript correction / polishing | `ingest/corrector.py:18` `CORRECTION_SYSTEM_PROMPT`; `services/transcript_polisher.py:24` | 2 | Chat corpus text | LLM edits transcript text. Invariant 13 requires `asr_cleaner` and hash updates for Qdrant first-person text; these LLM editors must never feed first-person collections. S2 to confirm lineage (`06`). |
| Quality gate | `ingest/quality_gate.py:435` | 1 | Admission | Low. |
| Contextual chunk headers | `services/contextual_chunking_service.py:43`; `rag.py:299` `CONTEXTUAL_CHUNK_HEADER_PROMPT` | 2 | Chat corpus | Headers are machine text next to teaching text. Must be marked machine. |
| Metadata / triples / ontology | `services/intelligent_metadata_extractor.py:57`, `:82`; `ingest/triple_extractor.py:51`; `ingest/ontology_writer.py:153-169` (Cypher templates) | 4 | Qdrant payload, Memgraph | LLM-derived entities. |
| Propositions / RAPTOR / topics | `rag.py:243` `TOPIC_LABEL_PROMPT`, `:253` `PROPOSITION_EXTRACTION_PROMPT`; `services/proposition_service.py` | 3 | Summary layers | Machine summaries; must not become quotes (invariant 12 for OKF). |
| OKF extraction | `backend/scripts/extract_okf_from_stores.py` (and root copy) | 1 family | `memory/okf/staging` | Review gate is `_excluded_parts` (root `CLAUDE.md`). |
| Offline first-person assist, grading | `backend/scripts/ops/*grade*`, `*judge*` | several | Evidence files | Labels are AI hints, never gold (`18`). |

---

## 4. Context construction and budgets

| Item | Where | Value / behaviour | Label |
|---|---|---|---|
| Persona budget | `generation_persona_token_budget` | 2,048 tokens; `GURU_SYSTEM_PROMPT` ≈1,940 [DOC-CLAIM code comment `services/voice/register.py:327-329`] | [V-STATIC] |
| Truncation | `cap_to_token_budget` | Truncates persona mid-sentence when over budget (comment in `rag/prompts/system.py:104-110`) | [V-STATIC] |
| Context fences | `rag/nodes/generation.py:3220-3226` `_fence('user_memory'…)`, `_fence('retrieved_context'…)`, `_fence('user_input'…)`, `_apply_delimiter_isolation` | Untrusted blocks delimited | [V-STATIC] |
| Memory | `app/orchestrator_utils.py:861-1190` | Up to five sources merged into one string, PII-scrubbed (`_scrub_memory_context` `:843`) | [V-STATIC] |
| First-person lane context | Relevance prompt carries full clip texts (`first_person_pipeline.py:1047-1056`); answerability carries the question only | No memory, no history beyond follow-up concatenation | [V-STATIC] |
| History | `chat_history_en` translated per message (`orchestrator_utils.py:505-540`) | Translation cost scales with history length for Indic users | [V-STATIC] |

---

## 5. Findings (harness and prompts)

### AI-001 — Routing scope is defined three times and disagrees
| Field | Value |
|---|---|
| Pillars | P2, P3 |
| Category | Routing |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | Regex scope `off_topic_stage.py:57-67`; answerability scope `first_person_pipeline.py:1329-1360`; LLM intent taxonomy `rag/prompts/guardrails.py:21-90`; on-device intent `rag/nodes/on_device_intent.py`; complexity classifiers `orchestrator_utils.py:151`, `services/semantic_router.py`. |
| Actual behaviour | A question can be "teaching" for the answerability gate and "general" for routing (ANS-003 in `10`). |
| Expected behaviour | One domain decision per turn, with one versioned scope definition. |
| Root cause | Incremental fixes added classifiers rather than replacing them. |
| User impact | Grief, ego, attachment, happiness questions get generic LLM prose. |
| Remediation | Introduce `route_decision` service: regex fast-path + embedding router over a topic map; outputs `{lane, state_signal, teacher_scope, confidence}`. Retire the other classifiers on the serve path. |
| Acceptance criteria | Routing accuracy targets in `10` ANS-003; one module owns the scope list. |
| Regression test | Routing table test over the `18` taxonomy set. |
| Implementation risk | Medium. |
| Verification | [V-STATIC] |

### AI-002 — Distress turns in Standard strategy pay for retrieval and LLM grading, then discard them
| Field | Value |
|---|---|
| Pillars | P1 |
| Severity | P2 |
| Type | Confirmed defect (waste) |
| Evidence | `route_after_intent` sends DISTRESS to `query` (`graph_strategies.py:95-99`); the chain runs `navigate_and_hyde` and `grade_documents`; `route_after_grading` then returns `distress` (`rag/nodes/intent.py:1872-1873`); `handle_distress` ignores `relevant_docs` except for quote cleanup (`intent.py:1560-1660`). |
| Actual behaviour | Two or more LLM calls and a retrieval per MODERATE+ turn on Standard, for a template answer. |
| Expected behaviour | Distress lane decides early and spends nothing it will not use. |
| Root cause | Docstring intent ("ground our response in teachings") was superseded by the zero-synthesis template rule, but the route stayed. |
| Remediation | Route DISTRESS to `handle_distress` in Standard as in Fast, or fetch only the gated first-person result. |
| Acceptance criteria | Zero LLM calls on the distress lane except the stage-2 classifier; latency p95 of distress turns ≤ cache-miss FP p95. |
| Regression test | Graph wiring test asserting `distress → handle_distress` for all strategies. |
| Implementation risk | Low. |
| Verification | [V-STATIC] |

### AI-003 — Teacher-style register is applied to assistant prose, including general mode
| Field | Value |
|---|---|
| Pillars | P4, P2 |
| Severity | P2 |
| Type | Probable defect |
| Confidence | Medium |
| Evidence | `langhanam_voice_enabled=True` (`config.py:1888`); `_maybe_apply_langhanam_voice` runs after `build_general_system_prompt` (`generation.py:3214-3250`); `is_voice_eligible` includes FACTUAL (`services/guru_voice_langhanam.py:289-298`); register text "THE TEACHER'S VOICE — {display}. Match this register" (`services/voice/register.py:291-300`). |
| Actual behaviour | Assistant-written prose is styled to sound like the teachers (second-person address, rhetorical questions, their vocabulary). In general mode this contradicts "Do not force a spiritual framing". |
| Expected behaviour | Assistant voice is the assistant's own. Teacher cadence appears only inside quotes. |
| Root cause | Register built to fix "machine-sounding" answers before the verbatim pivot. |
| User impact | Generated text can read as if a teacher said it. |
| Remediation | Disable for general mode; rename and restrict to L3 explanation tone (plain, warm, assistant); keep "never invent first person". |
| Acceptance criteria | Blind reviewers cannot tell assistant prose apart from "teacher quotes" in <5% of cases where they misattribute assistant text to a teacher (test in `18`). |
| Regression test | Unit test: general-mode prompt contains no register block. |
| Implementation risk | Low. |
| Verification | [V-STATIC]; [LIVE-L] for rendered output |

### AI-004 — Prompt sprawl without registry or versioning
| Field | Value |
|---|---|
| Pillars | P3, P1 |
| Severity | P2 |
| Type | Confirmed defect (maintainability, observability) |
| Evidence | §3.1 counts; no `prompt_version` on calls; `prompt_version_id` has no writer. |
| User impact | A prompt change cannot be tied to an answer-quality change or rolled back by id. |
| Remediation | `backend/prompts/` registry: one file per prompt, front-matter `{id, version, owner, layer, inputs, output_schema}`; calls log `prompt_id@version`; serving-policy fingerprint reads the registry. |
| Acceptance criteria | 100% of serve-time LLM calls log a prompt id and version; `rg` finds no inline system prompt in serve-time code. |
| Regression test | Test that enumerates LLM call sites and asserts registry ids. |
| Implementation risk | Medium (wide change; mechanical). |
| Verification | [V-STATIC] |

### AI-005 — Two provider stacks and misleading container names
| Field | Value |
|---|---|
| Pillars | P3 |
| Severity | P2 |
| Type | Confirmed defect (maintainability) |
| Evidence | §2.1. |
| Remediation | One provider interface behind the gateway; rename `container.ollama` → `container.llm`. S1 owns (`13`). |
| Acceptance criteria | Every call goes through the gateway; one class per provider. |
| Verification | [V-STATIC] |

### AI-006 — Dormant editorial prompt edits teacher words and calls them authentic
| Field | Value |
|---|---|
| Pillars | P4 |
| Severity | P2 (P0 if enabled) |
| Type | Architectural risk |
| Evidence | `services/quote_weaver.py:1100-1154`: "proofread… excise ephemeral retreat dates… replace 'him living with 10 heads' with 'Ravana living with ten heads'… 100%… MUST remain the Gurus' authentic spoken words". Gated by `first_person_mode=="hybrid"` and `first_person_editorial_rewrite_enabled` (`config.py:184`, `:189`). The `weave` docstring says "Weave verified clips into an authentic first-person teaching voice" (`quote_weaver.py:1380`). |
| Actual behaviour | Off by default. On the chat bridge the output would be discarded (exact-substring check). On any route that returns `answer_text` directly it would be served. |
| Expected behaviour | No LLM edits teacher text at serve time (invariants 1, 15). |
| Remediation | Delete the editorial prompt and the hybrid scaffolding path. Keep deterministic formatting. |
| Acceptance criteria | `rg "Elite Spiritual Manuscript Editor"` returns nothing in `backend/`. |
| Regression test | Test that `weave` never calls an LLM for any `first_person_mode`. |
| Implementation risk | Low. |
| Verification | [V-STATIC] |

### AI-007 — Relevance scorer model is an undeclared environment dependency
| Field | Value |
|---|---|
| Pillars | P1, P2 |
| Severity | P2 |
| Type | Confirmed defect (config drift) |
| Evidence | `first_person_relevance_model=""` (`config.py:478`); empty → provider default generation model (deepseek-chat); `backend/.env.example:195` `FIRST_PERSON_RELEVANCE_MODEL=` blank; root `CLAUDE.md` invariant 24 says the local scorer is Haiku 5.5 with `max_tokens=1024`. Code branches on model id (`first_person_pipeline.py:808-840`, `:1064-1092`). |
| User impact | A fresh deployment scores relevance with a different model, prompt path (comma vs JSON) and token budget than the one measured. |
| Remediation | Make the scorer model a required, validated setting when the relevance gate is on; record it in the release manifest. |
| Acceptance criteria | Startup fails if the gate is on and the scorer model is empty. |
| Regression test | Config validation test. |
| Implementation risk | Low. |
| Verification | [V-STATIC] |

### AI-008 — Static model routing; no intent/complexity routing on the live lane
| Field | Value |
|---|---|
| Pillars | P1 |
| Severity | P3 |
| Type | Product gap |
| Evidence | Fixed roles: fast for answerability, generation (or env) for relevance, provider default for rerank. |
| Remediation | See §6.3. |
| Verification | [V-STATIC] |

---

## 6. Target prompt, context and model-routing architecture

### 6.1 Principles

1. One decision per concern: route, plan, retrieve, judge, compose, verify.
2. Every prompt is a registry artefact with id, version, layer (L1–L6 from `10` §5) and output schema.
3. Teacher text is data inside a fenced block. It is never an instruction and never edited.
4. Deterministic code first. Use an LLM only where a measured gain exists.

### 6.2 Target pipeline (teaching lane)

| Step | Component | Deterministic or LLM | Prompt(s) |
|---|---|---|---|
| 1 | Safety pre-check | Deterministic + optional stage-2 classifier | `distress.classify@v` (topic-vs-state output) |
| 2 | Route | Regex fast path + embedding router | none (or `route.disambiguate@v` for low-confidence only) |
| 3 | Plan | LLM only for multi-facet questions | `plan.facets@v` (replaces 7 planners) |
| 4 | Retrieve | Deterministic (hybrid RRF; S2 `08`) | — |
| 5 | Gate | Deterministic integrity, rights, speaker, content-quality | — |
| 6 | Judge | One LLM call scores all candidates per facet (relevance + standalone + answers-facet) | `judge.evidence@v` (replaces rerank + relevance + batch grade) |
| 7 | Compose | Deterministic L1 assembly; optional LLM L3/L5 explanation constrained to cited evidence | `compose.explain@v` |
| 8 | Verify | Claim entailment against cited clips (LettuceDetect or NLI); deterministic quote-substring check | — |
| 9 | Render | Layer labels, citations, follow-up offers | — |

Expected LLM calls per teaching turn: 1 (judge) for short answers; 2–3 (plan, judge, compose) for deep answers. Today config B uses 3 for one clip.

### 6.3 Model routing

| Task | Default model class | Escalate when | Never |
|---|---|---|---|
| Distress stage 2 | Small classifier | — | Lower SEVERE/CRISIS without clinician-approved rule |
| Route disambiguation | Small | — | — |
| Facet planning | Small | >3 facets or cross-teacher | — |
| Evidence judge | Mid (measured choice; record id) | Disagreement with deterministic signals | Unversioned model swap |
| Explanation compose | Mid/large | Deep mode, cross-teacher | Any call without evidence ids |
| Translation of glue | Translation provider | — | Translating quotes |

Selection must be by measured quality per task on the `18` golden set, recorded per release. Prices must come from the provider's current price list at decision time; this audit quotes none.

### 6.4 Context budget per teaching turn (target)

| Block | Budget | Notes |
|---|---|---|
| System (registry) | ≤800 tokens | Cacheable stable prefix. |
| Plan + route metadata | ≤150 | — |
| Evidence (L1 clips) | ≤2,000 | Full clips, never truncated mid-clip (QBUG-7 lesson). |
| Memory (consented, relevant only) | ≤300 | Only for L4 application. |
| History | ≤400 | Summarised `answer_trace`, not raw turns. |
| Question | as is | Fenced. |

---

## 7. Cross-references

- Stage audit and latency: `05`, `15` (S1).
- Answer composition layers: `10` §5–§6.
- Evidence assembly across videos: `07` (S2).
- Distress classifier changes: `14b`.
- Evaluation of each prompt: `18`.
