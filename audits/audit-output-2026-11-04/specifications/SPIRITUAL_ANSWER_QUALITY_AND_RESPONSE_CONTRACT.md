# Spiritual answer quality and the response contract (implementation specification)

## 0. Header

| Field | Value |
|---|---|
| Purpose | Define the complete response contract (schema, modes, labels, voice layers, reflection content, follow-ups, uncertainty wording, safety ordering, multilingual rules) and what "100% quality" means and how each part is tested. Covers brief Parts 6.2, 6.7, Part 9 and Final Addition H. |
| Status | **Partial.** The additive wire fields (3.1), the abstain cause (3.6), the parity fixes, the static reflection and follow-up contracts (3.4, 3.5), the release invariants and their tests (3.10, section 7) are implementation-ready. Generated explanation, generated reflection and "say it simpler" are **decision-blocked on D-03**. The distress interface is stated only; its change is reserved for a clinician (D-06, T4-04). Language review is a human gate (D-22). |
| Date | 2026-11-05 |
| Code head | `c9b42d3e` on `feature/audit-strengthen-rag-qdrant` |
| Depends on decisions | Existing: D-03, D-06, D-22, D-25, D-09, D-14. Proposed here: PROPOSED D-PQ3, D-PQ7, D-PQ8, D-PQ9 (section 9). |
| Finding IDs | Existing: ANS-001 to ANS-008, ADV-05, UX-007, UX-008. New findings below are **proposals**: ANS-009 to ANS-013. The lead confirms them in `findings-index.md`. |
| Evidence labels | As in `CONVENTIONS.md`. Every `path:line` below was read at `c9b42d3e` in this session. |
| Sibling specifications | `RETRIEVAL_AND_RAG_SPEC.md` (pool, plan, dedup), `MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` (sets, Variant B), `PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` (saved clips need a clip id on the wire: see 3.1 and PROPOSED D-PQ7). |

Rules that bind this specification (root `CLAUDE.md`, checked against code in section 2):

1. The teachers' words appear only as verbatim spans from the store, with the correct speaker and source (invariants 1, 2, 12, 13, 14). The assistant speaks in its own labelled voice and never in a teacher's first person (Voice Governance).
2. No calibration profile exists. Every served clip is labelled "Related, not a direct answer". Never add a hand-picked threshold (invariant 3).
3. Quotes are never translated by the system as if they were the teacher's words. Any translation is labelled (invariant 16, ADV-05).
4. OKF text is never rendered as guru voice and never appears in `citations[]` (invariant 12).
5. Crisis pre-check and the topic rail run first. Safety text rides beside the answer, never inside a quote (invariant 8, `safety_notices`).
6. An answer that personalised with `memory_context` is never cached under the shared key (cache rule).
7. Do not change the distress regex or thresholds. T4-04 is reserved for a clinician.
8. Do not build what `19` §6 lists (N-09 multi-agent answers, N-10 semantic cache for teaching, N-22 machine translation presented as the teacher's words).

---

## 1. Existing coverage and exactly what it lacks

| Existing document | What it covers | What it lacks (this specification adds it) |
|---|---|---|
| `10` §1 to §6 | Anxiety-question trace. ANS-001 to ANS-008. Six voice layers L1 to L6. Answer plan. Default composition per intent. Clarifying questions. | A field-by-field wire schema. What the live wire actually carries. Rendering rules per layer. Reflection catalogue contract. Follow-up chip contract. |
| `10` §5.2 | Paths that could put generated text in a teacher's voice. | Release invariants that fail the build if one appears. |
| `14b` §3, §4 | Fabricated quotation and misattribution risks. Target safety design. | Tests for attribution on the wire. Ordering of safety notices around multi-block answers. |
| `17` ADR-001, ADR-006 | Layered answer. Distress topic-versus-state. | Interface between the answer path and distress routing (section 4.2). |
| `18` §6 | Blind human protocol. Pass bars (proposals). | Sample sizes per claim, interval method, what must stay human. |
| `22a` §3 | Metric definitions. | Rules that stop metrics being redefined to look better (3.10.4). |
| `docs/FIRST_PERSON_FOLLOWUPS_SPEC.md` (its own doc ID: A28) | Measured follow-up behaviour and options A to D. | A contract for chips and a request field that carries clip identity. |
| `FINAL_PENDING_WORK_REGISTER.md` | Status of ANS-001 to ANS-008. ANS-005 closed. ANS-001, 002 need a human. ANS-003, 004, 006, 007 need a decision. ANS-008 needs a human. | Tasks for everything that does not need a decision (section 8). |

### 1.1 New findings (proposed IDs)

| ID | Finding | Sev | Type | Evidence |
|---|---|---|---|---|
| ANS-009 | The client sends `response_preferences` (mode `concise`, `teaching_explanation`, and so on; `include_practice`; `include_reflection`; `action_depth`). The first-person route never reads them. They reach only the general graph state. A seeker who picks "concise" or "reflective" on the teaching lane gets no change. | P2 | Confirmed defect (product gap) | Schema `schemas/__init__.py:79-96`; request field `:177`; readers `pipeline/stages/glue_stages.py:143, 340-344`, `pipeline/pipeline_coordinator.py:227-247`. `first_person_bridge.py` has no reference. [V-STATIC] |
| ANS-010 | The chat wire hides why an answer abstained. The bridge passes only `status` (`"abstained"` or `"error"`) to `_abstain`. The pipeline's `abstain_reason` and `answerability` verdict are dropped. Static copy is the same for "no teaching found" and "the check could not run" (scorer or gate timeout). A store error gives a different line, but still `verification.passed=True`. | P1 | Confirmed defect | `first_person_bridge.py:906-922` (call with `status`), `:1252-1254, 1337`; reason lives only in `first_person_pipeline.py:5550-5580` and the result object. See also `RETRIEVAL_AND_RAG_SPEC.md` RET-17. [V-STATIC] |
| ANS-011 | The grounding state of a served "Related" clip is not pinned by any test. By reading: the bridge writes `verification.passed = is_direct and evidence_set_supported`. With no profile `is_direct` is false, so `passed` is false. `grounding_state_for` returns `grounded` only when `verification.passed is True`. So the served clip would be reported as `abstained`, and `classify_outcome` would count it as `abstained`, not `served`, so `useful_answer` could never fire. The A28 document (2026-10-19) records `grounding_state = grounded` for a served clip. The two disagree. No test composes the real path: `test_answer_outcome_telemetry.py` builds `grounding_state="grounded"` by hand. | P1 (if confirmed) | Unverified assumption. Needs a runtime test | `first_person_bridge.py:1149`; `grounding.py:98`; `answer_outcome.py:44-54`; `tests/test_answer_outcome_telemetry.py:12-27`; `docs/FIRST_PERSON_FOLLOWUPS_SPEC.md` section 2. [V-STATIC] + [LIVE-L] |
| ANS-012 | The three response writers disagree. The live sync and job writer omits `follow_up_suggestions`, `confidence_score`, `relevancy_score` and `ai_provenance`. It passes `live_logistics_events`, which is not a `ChatResponse` field, so it is dropped. The SSE `done` event omits `blocked`, `block_reason`, `audio_url`, `personalization_provenance`, `node_timings` and the retrieval fields. The client reads `live_logistics_events` and `follow_up_suggestions` on the sync path, so they are always empty there. `route_metadata` (audio strips, related clips, practice pointer, inquiry, second-quote note) is not a response field at all. | P2 | Confirmed defect | `orchestrator.py:142-193` (writer), `:693-728` (SSE), `chat.py:1025-1070` (v2 writer); `schemas/__init__.py:342-467`; client reads `src/lib/chat/transport.ts:244, 365`, `src/lib/chat/streaming.ts:343`. [V-STATIC] |
| ANS-013 | Reflection prompts and the practice pointer exist for `/api/first-person/query` and not for chat. `atma_vichara_inquiry`, `practice_recommendation`, `related_clips` and `audio_playback_clips` ride only `route_metadata` on chat, which is not in the response. The reflection catalogue is product-written English text matched by English keywords. Its authorship and review are not recorded. | P3 | Product gap | `quote_weaver.py:675-696, 699-721`; `first_person_bridge.py:1196-1210`; `api/first_person.py:56-76`. [V-STATIC] |

### 1.2 Corrections to existing text (code wins)

| Document | Statement | Code at `c9b42d3e` |
|---|---|---|
| `10` §5.2 | Translation of quotes: blocked, glue only. | True for the bridge, but the glue is now only safety notices. The bridge rebuilds the answer as the quotes joined by a blank line (`first_person_bridge.py:962`), so no framing text remains for the glue translator (`:322-380`). |
| Root `CLAUDE.md` inv. 21 | `/api/chat` "serves a clip". | The bridge may serve up to 3 citations (`first_person_bridge.py:861-862`). The default path serves one, plus an optional second quote when its flag is on (`config.py:494`). |
| `docs/FIRST_PERSON_FOLLOWUPS_SPEC.md` | "`first_person_bridge.py:725-738, 241-299`". | Lines moved. The follow-up rewrite is now at `first_person_bridge.py:754-768`. |
| `08` §5 | "No hash re-check on [cache] hit." | A cache hit re-runs `_passes_integrity_gate` on the cached citation fields (`first_person_pipeline.py:3245, 3331`) and, for v10 contexts, rebuilds citations from fresh spans (`:3322-3345`). The legacy re-check compares cached text with the cached hash. It does not re-read store text. The exact-cache key includes a corpus manifest digest (`:2857`) that invalidates entries on a data rebuild. |

---

## 2. Current state (verified at `c9b42d3e`)

### 2.1 The response schema as built

`ChatResponse` is `schemas/__init__.py:342-467`. Three writers build it. Column "Sync" is `orchestrator.py:142-193` (the live queue and sync writer; the code comment at `:148-153` says so). "SSE" is `_stream_done_metadata` (`orchestrator.py:693-728`). "UI" is the consumer in `src/`.

| Field | Type | Meaning | Set by first-person bridge? | Sync | SSE | UI consumer |
|---|---|---|---|---|---|---|
| `response` | str | Answer text. For a clip: quotes joined by a blank line (`first_person_bridge.py:962`). | Yes | Yes | streamed text | `ChatMessage.tsx` |
| `intent` | str | Intent label. Bridge sets `QUERY`. | Yes | Yes | Yes | admin pages |
| `meditation_step` | int | Next meditation step. | No (0) | Yes | Yes | `ChatInterface.tsx` |
| `citations` | list of `Citation` (9 fields) | Sources. | Yes | Yes | Yes | `ChatMessage.tsx` |
| `blocked`, `block_reason` | bool, str | Guardrail block. | No | Yes | **No** | `ChatInterface.tsx`, `streaming.ts` |
| `proactive_serene_mind` | dict | Serene Mind trigger. | No | Yes | Yes | `ChatInterface.tsx` |
| `faithfulness_score` | float | Verifier score. Bridge sets `None`. | None | Yes | Yes | `ChatMessage.tsx` |
| `relevancy_score` | float | Answer relevancy. | No | **No** | **No** | `ChatMessage.tsx` reads it |
| `confidence_score` | float | Verifier confidence. | No | **No** | Yes | `ChatMessage.tsx` |
| `verification` | dict | Verification result. Bridge: `passed, method, citations_verified, citation_integrity_verified, evidence_set_supported, direct, editorial_set`. | Yes | Yes | Yes | `ChatMessage.tsx` (`direct`, `editorial_set`, `method`) |
| `hallucination_flag` | bool | Bridge sets `False`. | Yes | Yes | Yes | `transport.ts:250` |
| `cache_hit` | bool | | No (pipeline cache is inside) | Yes | Yes | types only |
| `trace_id`, `latency_ms` | str, int | | Yes | Yes | Yes | `transport.ts:257-258` |
| `node_timings` | dict | Graph timings. | No | Yes | **No** | none in `src/` |
| `evaluation_trace`, `retrieval_metadata` | dict | Trace. | No | Yes | **No** | none in chat UI |
| `citations_verified`, `orphan_citations_stripped` | bool | | Yes / No | Yes | Yes | `ChatMessage.tsx` |
| `model_used`, `model_provider` | str | Bridge sets `None` (zero generation). | None | Yes | Yes | `ChatMessage.tsx` |
| `route_decision` | str | Bridge: `first_person_bridge` or `first_person_abstain`. | Yes | Yes | Yes | `ChatMessage.tsx` |
| `query_tier` | str | Bridge: `fast`. | Yes | Yes | Yes | `ChatMessage.tsx` |
| `follow_up_suggestions` | list of str | Bridge sets none. | No | **No** | Yes | `ChatMessage.tsx` renders chips if present |
| `audio_url` | str | Meditation audio. | No | Yes | **No** | `ChatMessage.tsx` |
| `kg_concept_nodes`, `daily_practice_card` | list, dict | | No | Yes | **No** | none in `src/` |
| `guidance_plan`, `answer_evidence` | dict | Presentation plan; evidence provenance. Bridge sets neither. | No | Yes | Yes | `ChatMessage.tsx` |
| `safety_notices` | list of str | Platform copy beside the answer. Bridge fills it: compassion framing, boundaries, support line, related-clips heading, second-quote note. | Yes | Yes | Yes | `transport.ts:268, 390` |
| `personalization_provenance` | dict | Public-safe summary of personal context classes. | No | Yes | **No** | `ChatMessage.tsx` |
| `grounding_state` | literal of 9 values | `grounded, abstained, safety_redirect, system_error, bounded_hypothetical, capability_answer, provenance_boundary, response_format_capability, unverified`. | Derived | Yes | Yes | `ChatMessage.tsx` |
| `release_manifest` | `ReleaseManifestPublic` | Public release projection. | Yes | Yes | Yes | `ChatMessage.tsx` |
| `provenance_manifest`, `ai_provenance` | model, dict | EU AI Act provenance. | Derived | Yes / **No** | Yes / No | `ChatMessage.tsx` |
| `live_logistics_events` | list | Passed by the writers but **not a field of `ChatResponse`**. Dropped on the sync path. | No | dropped | Yes | `transport.ts:244, 365` |

`Citation` is `schemas/__init__.py:285-339` with nine fields: `url, title, chunk_provenance, speaker, speaker_verified, timestamp_seconds, text_snippet, transcript_status, asr_artifacts`. `_coerce_citations` (`orchestrator.py:512-600`) builds them and de-duplicates by URL. `tests/test_citation_contract.py:169-205` pins that `verbatim_text` and `point_id` do not reach the wire. The client mapper (`src/lib/chat/types.ts:215-262`) accepts many more keys (`video_id`, `guru_id`, `start_ms`, `end_ms`, `playback_*`, `source_span_id`, `quote_segments`). On the sync and SSE paths those keys never arrive.

`ChatRequest` is `schemas/__init__.py:136-210`, `extra="forbid"`. Any new request field needs a schema change.

The richer surface is `POST /api/first-person/query` (`api/first_person.py:56-76`): `answer_text, citations (full dicts), status, is_direct_answer, latency_ms, cached, answerability, audio_playback_clip(s), detected_concepts, atma_vichara_inquiry, related_clips_heading, practice_recommendation, stage_timings, editorial_set`.

### 2.2 Labels and rendering (as built)

| Item | Behaviour | Evidence |
|---|---|---|
| "Related, not a direct answer" | The client derives it from `verification.direct === false`. The badge says "Related teaching — not a direct answer". A related clip never wears the "Verified" badge. | `ChatMessage.tsx:236-244, 304-306, 1423` |
| Speaker on the wire | `clean_wire_speaker` returns a verified teacher name, a downgrade label ("shared in <channel>", "unverified clip"), or nothing. A bare teacher name for an unverified clip is never shipped. | `services/attribution.py:70-100` |
| Unverified teacher attribution in prose | A guru message that has no citations and contains a "Sri X ... "quote"" pattern is replaced by the string `chat.unverifiedTeaching`. | `ChatMessage.tsx:880-890` |
| Multi-clip UI | One `GuruTeachingCard` per citation. Editorial set summary and conflict note exist. The summary line "Teaching evidence set: ..." is hard-coded English. | `ChatMessage.tsx:1396-1430, 536-545` |
| Machine translation | The client labels a quote translation "Machine translation — not the teacher's words". | `ChatMessage.tsx:2126-2128` |
| Abstain detection | The client detects an abstain by matching English strings ("I don't have a verified verbatim teaching that directly answers this", "No verified verbatim teaching"). | `ChatMessage.tsx:176-193` |
| Personalised note | A note "In our own words — not a direct quote from the teachers." exists for a personalised reflection. | `ChatMessage.tsx:545-551, 784` |

Note: the client abstain detector depends on English copy. A reworded or localised abstain would not be recognised. The `abstain` object of 3.6 removes this dependency.

### 2.3 Modes today

1. There is one mode on the teaching lane: one clip, or abstain, or (flag on) two clips.
2. `response_preferences.mode` is ignored on this lane (ANS-009).
3. Depth is a constant (`RETRIEVAL_AND_RAG_SPEC.md` RET-14).
4. Direct versus related: `is_direct` is always false (`first_person_pipeline.py:5527`). Every serve is "Related".

### 2.4 Safety and carve-out ordering (as built)

Order in the stage chain (`pipeline_builder.py:50-94`): `KillSwitch`, `CacheCheck`, `RequestState`, `InputGuardrail`, `Distress`, `CircuitBreaker`, `DoctrineCache`, `CasualShortCircuit`, `OffTopic`, `BoundedComparisonShortCircuit`, `Personalize`, `Graph`, `MeditationGen`, `Translation`, `ToneAdapter`, `OutputGuardrail`, `Memory`, `CacheUpdate`, `ResultAssembly`. The first-person module runs inside `Graph`. Inside the bridge: MODERATE+ distress decline, guided-practice decline, boundary notices, retrieval, clip rewrite and output rail (`first_person_bridge.py:682-990`). Inside the pipeline: crisis pre-emption and topic rail before retrieval (`first_person_pipeline.py:5638-5649`).

### 2.5 Multilingual today

1. The question is translated to English by `RequestStateStage` (`user_msg_en`) and retrieval uses that (`first_person_bridge.py:755`). The translation service and its budget were not read (Unknown).
2. Quotes stay in the stored language (English clips). Glue and notices are translated with a fail-open service call, never the quote (`first_person_bridge.py:322-380`).
3. The static abstain has hand-written copies for `hi, ta, te, kn, mr` (`first_person_bridge.py:270-276`). Their authorship and native review are not recorded. UX-008 and ANS-008 cover this.
4. The client labels any quote translation (ADV-05, landed).

---

## 3. Target contracts

### 3.1 Additive wire contract (`ans-v1`)

Principle: add fields. Keep every existing field and its meaning. The client keeps working when new fields are absent.

New response fields (on the sync response, the SSE `done` event and `/api/first-person/query`):

```json
{
  "answer_contract_version": "ans-v1",
  "answer_mode": "related_clip",
  "label_key": "answer.label.related",
  "answer_blocks": [ <AnswerBlock>, ... ],
  "evidence_set": { "status": "supported", "facet_coverage": {}, "teacher_scope": "unspecified",
                    "candidate_contexts": 5, "selected_contexts": 2,
                    "planner_version": "...", "selector_version": "..." },
  "abstain": null,
  "notices": [ { "kind": "separate_recordings", "copy_key": "synthesis.separate_recordings", "params": {} } ],
  "follow_ups": [ { "kind": "another_recording", "copy_key": "followup.another_recording", "params": {} } ]
}
```

`answer_mode` values (closed set):

| Value | Meaning | Today |
|---|---|---|
| `direct_clip` | A clip with a fitted calibration profile and `is_direct` true. | Never (no profile). Reserve the value. |
| `related_clip` | One verbatim clip, labelled related. | Yes (`weak_match`). |
| `multi_clip` | 2 or 3 verbatim blocks. | Variant A, when enabled. |
| `abstain` | Static abstain. | Yes. |
| `safety` | Crisis or distress template, helpline. | Yes. |
| `meditation` | Templated guided practice. | Yes. |
| `general` | General lane prose, not corpus-grounded (D-04). | Yes. |
| `template` | Other static product copy (greeting, boundary). | Yes. |

`AnswerBlock` (closed set of kinds; unknown kinds are ignored by clients):

| Field | `teaching_clip` | `assistant_explanation` (D-03) | `reflection_prompt` | `practice_pointer` | `not_covered` | `static_notice` |
|---|---|---|---|---|---|---|
| `block_id` | `b1..bn` | yes | yes | yes | yes | yes |
| `kind` | yes | yes | yes | yes | yes | yes |
| `section` | `primary`, `additional`, `guru:<id>` | n/a | n/a | n/a | n/a | n/a |
| `clip_ref` | **point id** | n/a | n/a | n/a | n/a | n/a |
| `text` | exact stored `verbatim_text` | assistant sentences | catalogue text | none | none | none |
| `guru_id`, `speaker_label` | copied from the clip | none | none | none | for a teacher | none |
| `speaker_verified`, `voice_verification_method` | copied | none | none | none | none | none |
| `video_id`, `video_title`, `video_url` | yes | none | none | none | none | none |
| `start_ms`, `end_ms`, `playback_start_s`, `playback_end_s` | yes | none | none | none | none | none |
| `transcript_status`, `asr_artifacts` | yes | none | none | none | none | none |
| `copy_key`, `params` | none | label key | theme key | practice id | `synthesis.not_covered.*` | key |
| `voice` | `teacher_verbatim` | `assistant` | `assistant_product` | `product` | `product` | `product` |
| `provenance` | `{source_text_hash_field, hash_ok}` | `{support, verifier}` | `{catalogue_id, reviewed_on}` | `{practice_id}` | none | none |

Rules:

1. `answer_blocks[].text` for `teaching_clip` equals `Citation.text_snippet` for the same clip. It is the same public text. It is not a new leak.
2. `clip_ref` equals the Qdrant `point_id` (`uuid5(FIRST_PERSON_NAMESPACE, transcript_hash:start_ms:end_ms)`, invariant 4). It carries no secret. It is required by saved clips, "report this clip" and follow-up exclusion (sibling specification). The existing test that forbids `point_id` on the wire (`tests/test_citation_contract.py:169-205`) must change in the same PR and says why. This is PROPOSED D-PQ7 (default: yes).

> **Update 2026-11-06 (batch 13, a33d6b8d):** D-PQ7 is still open. No clip id reaches the client. `Citation` has no point id or span id (`backend/app/schemas/__init__.py`), and `backend/tests/test_citation_contract.py` still asserts `point_id` is absent. The new "Report clip issue" control (`src/components/chat/CitationCard.tsx:221`) falls back to the YouTube video id, so a report names a video, not a clip.

3. `voice` is a closed set. A client must render `teacher_verbatim` only inside the quote component. A block with `voice != teacher_verbatim` never uses the quote component, a teacher avatar or a teacher name as speaker.
4. `label_key` is `answer.label.related` whenever any `teaching_clip` is present and `answer_mode != direct_clip`.
5. `answer_blocks` and `response` carry the same quotes. The server builds both from the same list. A test asserts equality (AC-ANS-05).
6. The legacy `citations[]`, `safety_notices` and `verification` stay. `safety_notices` keeps its meaning. `notices` is the typed form. During migration the server fills both.
7. SSE: the `done` event carries the same new fields. Partial text streamed before `done` is never saved as a full answer by the client (T1-18).

Parity (closes ANS-012):

| Writer | Change |
|---|---|
| Sync and job (`orchestrator.py:142-193`) | Add `follow_up_suggestions`, `confidence_score`, `relevancy_score`, `ai_provenance`, the new fields. Remove the dead `live_logistics_events` argument, or add the field to `ChatResponse`. Decision: add the field (the client reads it). |
| v2 (`chat.py:1025-1070`) | Same set. |
| SSE (`orchestrator.py:693-728`) | Add `blocked`, `block_reason`, `audio_url`, `personalization_provenance`, the new fields. |
| First-person route (`api/first_person.py`) | Add the same typed fields next to its existing ones. |

One shared builder `build_public_answer_fields(result)` in `backend/app/answer_contract.py` produces all new fields. All writers call it. A parity test iterates the fields (AC-ANS-04).

### 3.2 Modes

| Seeker control | Maps to | Teaching-lane behaviour now (compliant) | Decision-gated variant |
|---|---|---|---|
| `response_preferences.mode = concise` | plan depth `direct` | One block. No reflection prompt. No practice pointer. | none |
| `balanced_guidance` (default) | plan depth `standard` | One block. One static reflection prompt if `include_reflection`. | none |
| `reflective_guidance` | plan depth `standard` | One block, one static reflection prompt, one practice pointer if `include_practice` and one exists. | Personalised reflection needs D-03 and the memory decisions. |
| `teaching_explanation` | plan depth `multi_aspect` | Up to 3 verbatim blocks when Variant A is enabled; otherwise one block. | Assistant explanation (Variant B) needs D-03. |
| `include_practice=false`, `include_reflection=false`, `action_depth="none"` | | Omit the matching block. | none |

Rules:

1. A mode never removes a safety notice, a boundary or the "Related" label.
2. A mode never raises the number of LLM calls on the teaching lane unless it is Variant B (decision-gated).
3. The mode value is read in `FirstPersonBridgeStage._bridge` and passed to the retrieval plan (`RETRIEVAL_AND_RAG_SPEC.md` section 3.2). With `first_person_retrieval_plan_mode="off"`, only the block selection (reflection, practice) changes. The retrieval path is untouched.
4. "Direct" versus "related": the label follows `answer_mode`. `direct_clip` stays unreachable until the 299-item human gold set and a fitted profile exist. No document or UI may call the LLM relevance score a confidence.

### 3.3 Voice separation (rendering contract)

| Layer (`10` §5.1) | Block kind | Voice value | Label shown | Allowed today |
|---|---|---|---|---|
| L1 verbatim quote | `teaching_clip` | `teacher_verbatim` | Teacher name only when `speaker_verified`; else "unverified clip" or "shared in <channel>" | Yes |
| L2 faithful paraphrase | none | none | none | **Not built.** Forbidden by invariant 21 until D-03. |
| L3 explanation | `assistant_explanation` | `assistant` | "In our own words. Not the teachers' words." | **D-03** |
| L4 personal connection | none | none | none | Needs D-03 and memory decisions |
| L5 reflection or practice | `reflection_prompt`, `practice_pointer` | `assistant_product`, `product` | "A question to sit with. Written for this app, not by the teachers." | Static catalogue only (3.4) |
| L6 system notice | `static_notice`, `not_covered`, `notices[]` | `product` | none (own style) | Yes |

Hard rules (tested in section 7):

1. No block whose `voice` is not `teacher_verbatim` contains a quotation mark pair that attributes words to a teacher.
2. No assistant or product text uses a first-person pronoun in a teacher's name ("I invite you", "When I speak of"). Reuse `evals/pr_suite/voice_lint.py`.
3. A teacher name never appears as the speaker of an assistant block.

### 3.4 Introspection, retrospection and practical reflection (static now)

Three prompt classes, one catalogue per class:

| Class | Purpose | Shape |
|---|---|---|
| `introspection` | Look inward at the present state | One open question, no instruction, no claim about doctrine |
| `retrospection` | Look back at a recent situation | One open question about a past moment |
| `practical` | One small step | A pointer to a product-owned practice (`practice_id`) from the existing templated flows (`rag/meditation.py`), never a teacher's words |

Catalogue record (`backend/config/reflection_catalogue.yaml`, new, loaded at startup, validated by a test):

```yaml
- id: refl-intro-peace-01
  class: introspection
  theme: peace            # closed set: peace, suffering, relationships, general (today's four themes)
  lang: en
  text: "<question text, product-written>"
  source: product         # never "teacher"
  authored_by: <person id>
  reviewed_by: <person id>   # faculty or owner; required before release
  reviewed_on: 2026-MM-DD
```

Rules:

1. The first catalogue is the existing `_THEMATIC_INQUIRIES` (`quote_weaver.py:675-696`), moved to the file. It is product-written text. Its authorship and review are unknown today (ANS-013). Record them before release.
2. Selection is deterministic: theme by the same keyword rules as today, then `index = int(sha256(clip_ref + class).hexdigest(), 16) % len(options)`. The same clip gives the same prompt. A returning-user variation (avoid repeats) is the memory spec's job.
3. At most one prompt per answer. None on safety, abstain, boundary or distress turns.
4. A prompt is not a teaching claim. It must not state doctrine as fact (the existing catalogue comment says so, `quote_weaver.py:671-674`). A lint test fails on declarative sentences ("All suffering is ...").
5. The label key `answer.layer.reflection.label` is required in the block.
6. Other languages: a catalogue entry per language, written and reviewed by a native speaker `[HUMAN]` (D-22). No machine translation of the catalogue.
7. **Generated** reflection (personalised or free) is decision-gated on D-03. Do not build it.

### 3.5 Follow-up dialogue

Compliant now (verbatim only). Follows the recommendation of `docs/FIRST_PERSON_FOLLOWUPS_SPEC.md` section 6 (a recommendation, not a decision). The owner decides options in that document; this section specifies the parts that need no generation.

New optional request field on `ChatRequest` (additive; `extra="forbid"` means the schema must add it): `continue_from: list[str]` (clip refs of the previous answer, at most 3, each a UUID string). The client sends it with a follow-up chip.

Chip kinds (`follow_ups[].kind`; all deterministic; none is model text):

| Kind | Condition to offer | Server behaviour on tap |
|---|---|---|
| `another_recording` | At least one more eligible clip exists in the last pool (the server need not hold it; it re-runs retrieval with `exclude_clip_refs=continue_from`) | Run the pipeline with the same question and the served clips excluded after the gates. Serve the next eligible clip or the static abstain "no further recording found". |
| `other_teacher` | The question was not teacher-scoped and the other teacher has an eligible clip | Re-run with `teacher_id` set. |
| `practice_for_this` | A product practice pointer exists for the theme | Offer the pointer. No retrieval. |

Typed `follow_ups` replaces the string list `follow_up_suggestions` for the teaching lane. The old list stays empty there.

Behaviours:

| Seeker follow-up | Compliant handling | Evidence for current state |
|---|---|---|
| "Tell me more" | `another_recording` | Today: history concatenation `f"{last_user} — {retrieval_query}"` (`first_person_bridge.py:766`), which can re-serve the same clip (A28 section 2.1). |
| "Say it simpler" / "explain" | Static reply: "I can only share the teachers' recordings as they are. I cannot rephrase them." plus `another_recording`. | A28 option A. |
| "Say it simpler", labelled rewrite | **D-03** (`docs/FIRST_PERSON_FOLLOWUPS_SPEC.md` option C). | n/a |
| "In Hindi" / language change | Static reply that quotes stay in their recorded language and a labelled translation is available on request. | ADV-05 label exists. |
| A new topic | New question. No `continue_from`. | `names_new_topic` (`first_person_bridge.py:760`) |

Server-side `answer_trace` (T5-05) is the durable form. Until it exists, the client carries `continue_from`.

### 3.6 Uncertainty and abstain wording

New field `abstain` (null unless the answer is an abstain):

```json
{ "cause": "no_evidence", "reason_code": "relevance_below_min", "copy_key": "abstain.no_evidence", "retry_useful": false }
```

| `cause` | Meaning | Source (reason or status) | Static copy key | `retry_useful` |
|---|---|---|---|---|
| `no_evidence` | The corpus has no verified clip that answers | `no_verified_clips`, `relevance_below_min`, `answerability_withheld` with verdict `no` | `abstain.no_evidence` ("I don't have a verified recording that answers this directly. You can rephrase, or ask about a specific teaching or practice.") | Rephrase |
| `system_unavailable` | The check could not run | `error`, `relevance_indeterminate`, `answerability_withheld` with verdict `indeterminate`, `serving_contract_violation` | `abstain.system_unavailable` ("I could not check the teachings just now. Please try again in a moment.") | Yes |
| `topic_boundary` | Outside the teaching domain or blocked by the topic rail | `topic_blocked`, domain boundary | `abstain.topic_boundary` | No |
| `safety` | Crisis or distress route | crisis route | The safety template | n/a |

Rules:

1. The bridge passes the reason and the answerability verdict from the pipeline result to `_abstain` (today it passes only `status`, ANS-010).
2. Copy keys, not free text, ship. The client renders reviewed strings. Replace the client's English-string abstain detector with `abstain != null` (`ChatMessage.tsx:176-193`).
3. An abstain never says "this teaching does not exist". It says "I did not find a verified recording".
4. `verification.passed` is **false** for `system_unavailable`. It is `true` only for a truthful `no_evidence`, `topic_boundary` or `safety` abstain (see AC-ANS-08).
5. The abstain carries the support-line notice whenever the question matched a self-harm cue (existing behaviour, `first_person_bridge.py:742-754`).
6. Copy for `abstain.system_unavailable` and for each new key needs native-speaker review per served language before release `[HUMAN]`.
7. The five existing Indic static abstain strings stay until review replaces them (`first_person_bridge.py:270-276`).

Uncertainty about attribution:

| State | Wire | Display |
|---|---|---|
| `speaker_verified` true | Teacher name | Name |
| `speaker_verified` false or absent | Downgrade label or nothing (`clean_wire_speaker`) | "unverified clip" or "shared in <channel>" |
| Two clips from different teachers | Per-block `guru_id` | Two labelled sections |

### 3.7 Safety carve-out ordering (contract)

The order of authority for a turn, highest first. A higher level pre-empts every lower level.

| Level | Rule | Owner of the rule |
|---|---|---|
| 1 | Crisis text: distress lane, helplines, no clip, no reflection prompt, no chips except safety follow-ups | `InputGuardrail`, `Distress`, `first_person_pipeline._crisis_preemption` |
| 2 | SEVERE distress: same | `first_person_bridge.py:682-686` |
| 3 | MODERATE distress: default decline to the distress handler. With `first_person_distress_serve_clip_enabled` the clip may ship under the compassion framing, one block at most, hazardous clips omitted entirely | `first_person_bridge.py:682-690, 997-1008`; `config.py:453` |
| 4 | Self-harm cue in the question or in the clip: the support line ships with the answer, including an abstain | `first_person_bridge.py:742-754, 1047-1053` |
| 5 | Relationship or addiction boundary: boundary notice with a clip or an abstain | `first_person_bridge.py:719-735` |
| 6 | Topic rail and blocked-topic abstain | `first_person_pipeline.py:5638-5649` |
| 7 | Output rail on the quote text | `first_person_bridge.py:976` |
| 8 | Reflection prompt, practice pointer, chips: only when levels 1 to 6 are clear | this specification |

Interface to distress routing (interface only; no change to detection): the answer path reads `ctx.assessment.level` (int 0 to 4) and the `detected_signals` list for `LLM_STAGE2_UNAVAILABLE_SIGNAL`. When T4-04 adds a topic-versus-state field, the bridge may read it. Do not add that field here. Do not edit `serene_mind_engine.py`.

Effect on the anxiety question (ANS-001, RC-5): a MODERATE regex (`serene_mind_engine.py:368`) matches the topic word. With the default flag the turn goes to the distress handler and the seeker gets a template and no teaching. The fix belongs to the clinician-reviewed T4-04 (D-06). This specification must not work around it.

### 3.8 Multilingual rules

1. **Quotes are never translated by the system as the answer.** The block text is the stored text in its recorded language.
2. **Machine translation is a seeker action and is always labelled.** The label "Machine translation — not the teacher's words" is required (ADV-05, landed). It must be present in every locale. A test fails if a locale lacks the key (T1-20 guard).
3. **Static copy** (labels, notes, abstains, reflection prompts, chips) is written per language, not machine-translated, and reviewed by a native speaker before release `[HUMAN]`. A language without a review record shows English copy plus the language-neutral safety line, never an unreviewed machine translation of a safety string.
4. **Attribution is the same in every language.** `guru_id`, `speaker_verified` and the downgrade rule do not depend on the seeker's language. The teacher's display name comes from the guru registry for that language if present, else the English registry label. No language path may add or remove a teacher name.
5. **Meaning preservation** (what must be checked, section 7.3): the English question translation used for retrieval, the static copy per language, and any labelled quote translation.
6. **Language field on spans.** T5-06 adds a `language` field on spans. Until then the system assumes English clips.
7. Priority Indic languages are D-22. The first release language set is English plus the languages with a signed review.

### 3.9 Guru-specific attribution

1. Each `teaching_clip` block carries its own `guru_id` and `speaker_label` copied from the stored clip (`first_person_pipeline.py:1707-1760`).
2. A question that names one teacher scopes retrieval to that teacher (`requested_teacher`, `first_person_pipeline.py:161-174`). No clip of the other teacher is served in its place.
3. A question that names both, or none, may return clips of both teachers. They appear in separate labelled sections (`MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` 3.1.3).
4. A teacher whose clip is not eligible gets a `not_covered` block ("I did not find a verified recording of {teacher}"). The system never fills the gap with the other teacher's words under the first teacher's name.
5. Teacher names and aliases come from `config/gurus.yaml` through `services/guru_registry.py`. Adding a teacher is a registry change (T8-01), not a code change.

### 3.10 "100% quality": what it means and how it is measured

This subsection is a definition. Section 7 lists the tests.

#### 3.10.1 Absolute release invariants (tested at 100% on every release)

An invariant is a mechanism that must hold for every served answer. A test proves the mechanism on the full fixture and on a staging replay. A release is blocked on any failure. No sample-based claim can prove "100%". The claim is about the check that runs at serve time, plus the tests that prove the check.

| ID | Invariant | Serve-time mechanism | Existing evidence | Gap |
|---|---|---|---|---|
| I-1 | No fabricated teacher quote. Every served teacher quote is an exact substring of a stored `verbatim_text` whose hash field matches. | Integrity gate (`first_person_pipeline.py:370-440`; v10 `first_person_context_harness.py:320`); bridge substring check (`first_person_bridge.py:951`); answer rebuilt from quotes (`:962`) | PR suite `evals/pr_suite/quote_integrity.py`; `test_citation_contract.py` | A counter for a substring-check decline does not exist (add `guru_quote_check_decline_total`). |
| I-2 | No misattribution served as fact. A named teacher appears only when the clip's `speaker_verified` is true and the label equals the stored speaker. | `clean_wire_speaker` (`attribution.py:70-100`); copied citation fields | `test_citation_contract.py:95-160, 269+` | The wire does not carry `guru_id`; add (3.1). |
| I-3 | No cross-user leakage. A response never contains another user's text. | Cache key `(language, message)`; a personalised answer is never cached; the first-person exact cache holds only non-personalised answers | `tests/test_cache_personalization_leak.py` | None for the first-person route. New personalisation (memory spec) must extend the test (AC-PM-09). |
| I-4 | No success-shaped response after a failed pipeline. A turn in which a required step failed never reports `verification.passed=true`, `grounding_state="grounded"` or outcome `served`. | Fail-closed guards; static abstains | `fp_fail_closed.py`; `tests/test_fp_fail_closed.py` | RET-17 and ANS-010: the store-error abstain reports `passed=True`; the cause is hidden. Fix in NEW-ANS-2. |
| I-5 | Integrity gate on every served clip, including cache hits. | Gate on cached citations (`first_person_pipeline.py:3245, 3331`); `points_servable` re-check (`:3426`) | `tests/test_first_person_cache*.py` (confirm names) | Legacy replay re-checks cached text, not store text. The corpus-digest key covers rebuilds. Document the limit. |
| I-6 | No generated text in a teacher's voice. Every block that is not `teacher_verbatim` carries `voice != teacher_verbatim` and passes the voice lint. | Zero generation on the route; `model_used=None`; `guru_integrity_breach_total` | `answer_outcome.py:is_integrity_breach`; `evals/pr_suite/voice_lint.py` | None. Variant B must keep it. |
| I-7 | Crisis and SEVERE distress never receive a clip. | Pre-emption before retrieval | `first_person_pipeline.py:3562`; `test_lv1_distress_no_generated_teachings.py` | Distress detection quality is a separate, human-reviewed gate (D-06). |
| I-8 | No system translation of a quote presented as the teacher's words. | Quotes bypass the translator (`first_person_bridge.py:322-380`); label on client translation | `ChatMessage.tsx:2126` | Add a test that a Hindi turn returns the same `text` as the English turn. |
| I-9 | No seeker text in logs or metric labels. | Hash-only logging | `tests/test_no_seeker_text_in_logs.py` | None. |

#### 3.10.2 Statistical quality metrics and the sample each needs

A claim "error rate at most p with 95% confidence" with k errors in n independent items needs the one-sided Clopper-Pearson bound (`clopper_pearson_upper`, `backend/evaluation/gold/metrics.py:90`) at or below p. Computed values:

| Bound p | 0 errors: n | 1 error: n | 2 errors: n |
|---|---|---|---|
| 5% | 59 | 93 | 124 |
| 1% | 299 | 473 | 628 |

(Zero-error n = `ceil(ln(0.05) / ln(1 - p))`: 29, 59, 99, 149, 299 for p = 10%, 5%, 3%, 2%, 1%.)

| Metric | Definition (unchanged from `22a` §3) | Claim type | Sample needed | Unit |
|---|---|---|---|---|
| False-serve rate on out-of-corpus questions | Served answers ÷ `null` items | Upper bound | 299 `null` items and 0 serves for 1%; 59 for 5% | Question |
| Misattributed served clip (speaker label differs from verified speaker) | Count ÷ served clips in the held-out set | Upper bound | 299 served clips and 0 errors for 1% | Clip |
| Unsupported assistant sentence (Variant B) | Answers with at least one unsupported sentence ÷ answers | Upper bound | 59 / 149 / 299 answers by stage (AC-SYN-B8 to B10) | Answer |
| Direct-answer label error | Wrong "direct" labels ÷ confident answers | Upper bound at 1% | 299 confident items with 0 errors; requires a fitted profile | Item |
| Teaching-domain routing recall | Correctly routed teaching questions ÷ teaching questions | Lower bound 95% | 59 items with 0 misses, or 93 with 1 | Question |
| Usefulness at 4 or more of 5 | Answers rated 4 or more ÷ answerable items | Estimate with interval | About 81 items for ±0.10 half-width, about 323 for ±0.05 at p = 0.7 | Item, 2 raters |
| Retrieval metrics | `RETRIEVAL_AND_RAG_SPEC.md` section 3.5 | Estimate with interval | Stage 1 at least 150; stage 2 at least 299 + 299 | Question |

**Per-category claims.** A 1% bound per category needs 299 items in each of the 23 categories of `18` §4 (6,877 items). That is not a realistic target. Do not claim it. Report per-category estimates with their intervals, and make the 1% claims on the pooled, category-stratified held-out set. A per-category bound of 5% needs 59 items each (1,357 items) and is a choice for the owner (PROPOSED D-PQ3).

#### 3.10.3 What stays under ongoing human review

| Review | Who | Cadence | Sample | Why a human |
|---|---|---|---|---|
| Blind usefulness and appropriateness of answers | 2 independent raters, one with faculty knowledge | Every release, held-out set | 60 answers per release (bound 5% on severe harm at 0 errors) | A model cannot judge spiritual fit. |
| Conflicted sets (`status=conflicted`) | Faculty or owner (PROPOSED D-PQ6) | Weekly | All of them | Only a human can tell a real contradiction. |
| Static copy and reflection catalogue per language | Native speaker | Per new string | All | Meaning and tone. |
| Distress sets | Clinician | Per release of the regex (T4-04) | Per clinician plan | Reserved. |
| Helplines | Owner | Per `config/helplines.yaml` rules | Each entry | Phone verification. |
| New video rights and speaker verification | Owner | Per ingest batch | Per batch (T3-06 reserved) | Legal and identity. |
| Synthetic probe set against staging | Rater | Weekly | 60 probes | Drift detection without real user text. |

#### 3.10.4 Rules against redefining metrics

1. A metric keeps the definition in `22a` §3. Changing a definition needs a decision-log entry and a re-run of the baseline.
2. Served share is measured over **answerable** held-out items only. Abstaining on a `null` item counts as success in the `null` stratum and nowhere else.
3. The repository's `useful_answer` signal (`answer_outcome.compute_useful_answer`: helpful, or 20 s played, or saved, and not reported) is an engagement proxy. It is not the human "usefulness at 4 or more of 5" metric. Never report one under the other's name.
4. AI-authored labels never enter a gate (N-24, invariant 3).
5. Release gates compare the lower bound of an interval to a floor fixed before the run (`RETRIEVAL_AND_RAG_SPEC.md` section 3.5). No floor is chosen by an agent.

---

## 4. Behaviour per component, with failure handling

### 4.1 Answer assembly (`build_public_answer_fields`)

1. Input: the `PipelineResult` (final answer, citations, verification, route metadata, grounding state).
2. Output: `answer_contract_version`, `answer_mode`, `label_key`, `answer_blocks`, `evidence_set`, `abstain`, `notices`, `follow_ups`.
3. Pure function. No network. No model.
4. On any exception: log (ids only), return the legacy fields unchanged and set `answer_contract_version` to `null`. A failure here never fails the chat request.
5. For a teaching clip, copy fields from the cached or fresh citation dict. Never compute a speaker, hash or label.

### 4.2 Bridge changes

1. Pass `result.abstain_reason` and `result.answerability` to `_abstain` (ANS-010).
2. Set `verification.passed=False` and `method="first_person_store_unavailable"` for `status=="error"`.
3. Read `response_preferences.mode` and the include flags (ANS-009). Select blocks only. Do not change retrieval until the plan flag is on.
4. Read `continue_from` and pass `exclude_clip_refs` to the pipeline after the gates (3.5).

### 4.3 Frontend

1. Render `answer_blocks` when present. Fall back to the current rendering when absent.
2. Use `voice` to choose the component. `teacher_verbatim` uses `GuruTeachingCard`. Other voices use a plain card with the label.
3. Replace the English-string abstain detector with `abstain`.
4. Move every literal ("Teaching evidence set: ...", labels) to locale files.
5. Show the machine-translation label on any translated quote.

### 4.4 Failure behaviour summary

| Failure | Response | `answer_mode` | `verification.passed` | Outcome label |
|---|---|---|---|---|
| Library or encoder down | `abstain.system_unavailable` | `abstain` | false | `error` |
| Scorer or gate timeout | `abstain.system_unavailable` | `abstain` | false | `error` |
| No evidence | `abstain.no_evidence` | `abstain` | true | `abstained` |
| Serving contract broken | `abstain.system_unavailable` | `abstain` | false | `error` |
| Output rail blocks | Decline to abstain | `abstain` | true | `abstained` |
| Composer or verifier fails (Variant B) | Variant A answer | `related_clip` or `multi_clip` | unchanged | `served` |
| `build_public_answer_fields` fails | Legacy fields | unchanged | unchanged | unchanged |

`classify_outcome` maps the abstain cause to the outcome (NEW-ANS-2): `system_unavailable` to `error`, others to `abstained`. A served clip is `served` regardless of its "Related" label (resolves ANS-011 if the test confirms the problem).

---

## 5. Deterministic versus LLM steps

| Step | Type | Budget | Failure |
|---|---|---|---|
| `build_public_answer_fields` | Deterministic | microseconds | Legacy fields |
| Reflection prompt choice | Deterministic (hash) | none | Omit the block |
| Chip choice | Deterministic | none | Omit |
| Abstain cause mapping | Deterministic | none | `system_unavailable` |
| Static copy | Reviewed strings | none | English copy plus safety line |
| Retrieval and gates | See `RETRIEVAL_AND_RAG_SPEC.md` section 2.4 | | |
| Variant B composer and verifier | See `MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` section 5 | D-03 | Variant A |

This specification adds **no** LLM call on the teaching lane.

---

## 6. Observability

Reuse names that exist. Never put question or answer text in a label.

| Metric | Exists? | Labels | Use here |
|---|---|---|---|
| `guru_answer_outcome_total` | Yes (`metrics.py:161`) | `lane`, `outcome` | Census. Must show `error` for `system_unavailable` after NEW-ANS-2. |
| `guru_answer_latency_seconds` | Yes (`metrics.py:166`) | `lane`, `outcome` | Latency. |
| `guru_integrity_breach_total` | Yes (`metrics.py:172`) | `lane` | I-6. Must stay 0. |
| `guru_useful_answer_total` | Yes (`metrics.py:177`) | `lane`, `signal` | Engagement proxy only (3.10.4). |
| `guru_fp_fail_closed_total` | Yes (`metrics.py:55`) | `reason` | Fail-closed events. |
| `first_person_requests_total` | Yes (`metrics.py:755`) | `status`, `reason` | Abstain reasons. |
| `guru_answer_mode_total` | **New** | `mode` (8 values) | Mode mix. |
| `guru_abstain_cause_total` | **New** | `cause` (4 values) | Separates "no evidence" from "system unavailable". |
| `guru_quote_check_decline_total` | **New** | `check` (`substring`, `output_rail`, `hash`) | I-1 mechanism health. |
| `guru_contract_parity_failures_total` | **New** | `writer` | Parity test in staging. |
| `guru_followup_total` | **New** | `kind` (3 values) | Chip use. |

Verify before adding: `grep -n '^ANSWER_\|^INTEGRITY\|^USEFUL\|^FP_' backend/app/metrics.py`. Add `answer_mode`, `abstain_cause`, `block_count` to the `answer_outcome` record (`answer_outcome.py:build_answer_outcome`). They are labels and counts only.

---

## 7. Acceptance criteria

Legend: **S** CI with mocks or fixtures. **Q** real Qdrant fixture. **L** live or local stack. **H** human.

### 7.1 Release invariants (every release; 100% pass required)

| # | Criterion | Test (file, case) | Pass / fail | Type |
|---|---|---|---|---|
| AC-ANS-01 | I-1: every `teaching_clip` block text is an exact substring of one stored span text and its hash field matches. | `backend/tests/test_release_invariants.py::test_every_served_quote_is_exact_and_hashed` (new; property test over the golden fixture set plus 200 generated spans) | Pass: 0 failures. Fail: any. | S |
| AC-ANS-02 | I-2: the speaker label of every block equals the stored speaker; an unverified clip never carries a bare teacher name. | `...::test_attribution_matches_store_and_downgrades_unverified` (extends `test_citation_contract.py`) | Pass: 0 failures. | S |
| AC-ANS-03 | I-3: two users, the same question; B never receives A's text; a personalised answer is not written to any shared tier. | `backend/tests/test_cache_personalization_leak.py` (existing) plus `...::test_answer_blocks_have_no_user_text` | Pass. | S |
| AC-ANS-04 | I-4 and parity: for each injected fault (Qdrant down, encoder down, scorer timeout, answerability timeout, output rail missing, contract violation), the response has `answer_mode="abstain"`, `abstain.cause` as in 4.4, `verification.passed` as in 4.4, outcome as in 4.4, and **no** `teaching_clip` block. | `...::test_fault_injection_never_success_shaped[fault]` (new; 6 parametrised cases) | Pass: all 6. Fail: any success-shaped field. | S |
| AC-ANS-05 | I-5: a cached replay re-runs the integrity gate and drops a tampered cached citation. | `backend/tests/test_first_person_cache_integrity.py::test_tampered_cache_entry_is_a_miss` (new) | Pass: miss, no serve. | S |
| AC-ANS-06 | I-6: no non-teacher block uses the quote component or a teacher speaker; voice lint passes on all product text. | `...::test_voice_separation`; `evals/pr_suite/voice_lint.py` | Pass. | S |
| AC-ANS-07 | I-7: crisis and SEVERE inputs never produce a `teaching_clip` block. | `backend/tests/test_lv1_distress_no_generated_teachings.py` (existing) plus `...::test_crisis_has_no_clip_block` | Pass. | S |
| AC-ANS-08 | I-8: the same English question asked in `en` and `hi` returns identical `text` for the same `clip_ref`. | `...::test_quote_text_is_language_independent` (fixture translator) | Pass. | S |
| AC-ANS-09 | I-9: seeker text never reaches logs or metric labels in any new code. | `backend/tests/test_no_seeker_text_in_logs.py` (extend to the new module) | Pass. | S |

### 7.2 Contract and parity

| # | Criterion | Test (file, case) | Pass / fail | Type |
|---|---|---|---|---|
| AC-ANS-10 | Sync, v2, SSE and `/api/first-person/query` carry the same `answer_*` fields for the same result. | `backend/tests/test_answer_contract_parity.py::test_four_writers_same_fields` (new) | Pass: field sets equal. Fail: any difference. | S |
| AC-ANS-11 | `live_logistics_events`, `follow_up_suggestions`, `confidence_score`, `relevancy_score`, `ai_provenance` reach the sync response. | `...::test_sync_writer_forwards_all_result_fields` | Pass. | S |
| AC-ANS-12 | `answer_blocks` text equals `response` quote text and `Citation.text_snippet`. | `...::test_blocks_equal_response_and_snippet` | Pass. | S |
| AC-ANS-13 | `clip_ref` equals `uuid5(FIRST_PERSON_NAMESPACE, transcript_hash:start_ms:end_ms)` for the clip. | `...::test_clip_ref_is_point_id` | Pass. | S |
| AC-ANS-14 | Unknown block kinds are ignored by the client; absent `answer_blocks` falls back to legacy rendering. | `src/test/components/ChatMessage.test.tsx::renders_legacy_without_answer_blocks`, `::ignores_unknown_block_kind` | Pass. | S |
| AC-ANS-15 | Grounding state of a served related clip (ANS-011): the real path from bridge result to `grounding_state_for` to `classify_outcome` is pinned. | `backend/tests/test_answer_outcome_telemetry.py::test_served_related_clip_counts_as_served` (new; builds the result through `FirstPersonBridgeStage` with a fake pipeline) | Pass: outcome `served`. If it fails today, the failure is the finding. | S |
| AC-ANS-16 | `ChatResponse` literal covers every `grounding_state` any node emits. | Existing `tests/test_grounding_state_contract.py` (confirm) | Pass. | S |

### 7.3 Modes, reflection, follow-ups, abstain

| # | Criterion | Test (file, case) | Pass / fail | Type |
|---|---|---|---|---|
| AC-ANS-17 | `concise` yields one block and no reflection or practice block; `reflective_guidance` yields one reflection block at most; safety notices never removed by any mode. | `backend/tests/test_response_modes_first_person.py::test_mode_matrix` (new) (4 modes × 3 include flags) | Pass: matrix as in 3.2. | S |
| AC-ANS-18 | Reflection selection is deterministic and stable for the same `clip_ref`. | `backend/tests/test_reflection_catalogue.py::test_selection_is_stable` (new) | Pass. | S |
| AC-ANS-19 | Catalogue lint: every entry has `source: product`, `authored_by`, `reviewed_by`, `reviewed_on`; no declarative doctrine sentence; no first-person teacher voice. | `...::test_catalogue_records_and_lint` | Pass. | S |
| AC-ANS-20 | No reflection, practice pointer or chip on safety, abstain, boundary or distress turns. | `...::test_no_extras_on_safety_paths` | Pass. | S |
| AC-ANS-21 | `another_recording` never re-serves a clip in `continue_from`. | `backend/tests/test_followup_continue_from.py::test_excluded_clip_not_reserved` (new) | Pass. | S |
| AC-ANS-22 | "Say it simpler" returns the static reply and never calls an LLM. | `...::test_simplify_request_static_no_llm` (fake provider counts 0) | Pass: 0 calls. | S |
| AC-ANS-23 | Abstain cause mapping per 3.6 for each reason code. | `backend/tests/test_abstain_cause.py::test_reason_to_cause[reason]` (7 cases) | Pass. | S |
| AC-ANS-24 | The client shows the same abstain state without matching English strings. | `src/test/components/ChatMessage.test.tsx::abstain_from_field_not_text` | Pass. | S |

### 7.4 Multilingual and human gates

| # | Criterion | Test (file, case) | Pass / fail | Type |
|---|---|---|---|---|
| AC-ANS-25 | Every locale has the machine-translation label and all `answer.*`, `synthesis.*`, `abstain.*`, `followup.*` keys. | `src/test/locale-keys.test.ts::test_required_answer_keys` | Pass: 0 missing in every shipped locale. | S |
| AC-ANS-26 | Native review of every static string and catalogue entry per served language. | Review record in `docs/` | Signed record per language. | H |
| AC-ANS-27 | Meaning preservation of the question translation used for retrieval: 100 questions per language, two bilingual raters, 5-point meaning score, back-translation reported. | Review sheet | Report mean, share at 4 or more with a Wilson interval, rater agreement. Floor set by the owner (PROPOSED D-PQ3). | H + L |
| AC-ANS-28 | Retrieval parity across languages (shared with the retrieval spec, AC-RET-19). | Paired run | Floor by PROPOSED D-PQ3. | L + H |
| AC-ANS-29 | Statistical gate at release: false-serve rate on `null` has an upper bound at or below the owner floor on at least 299 items; misattribution bound likewise on 299 served clips. | `evals/` run on the held-out set | Pass when the Clopper-Pearson bound is at or below the floor. No floor chosen by an agent. | L + H |
| AC-ANS-30 | Blind human review of 60 answers per release with two raters; zero "severe" harm and zero fabricated-quote findings. | Review sheet | 0 of 60 (bound 5%). | H |
| AC-ANS-31 | Probe drift: weekly synthetic probe set (60 probes, no real user text) against staging shows the same invariants. | Staging job | 0 invariant failures. | L |

---

## 8. Ordered implementation tasks (PR-sized)

| Order | Task ID | Title | Scope and files | Depends on | Non-goals | Rollback |
|---|---|---|---|---|---|---|
| 1 | NEW-ANS-1 | Pin the real grounding and outcome composition | Tests AC-ANS-15, AC-ANS-04 (grounding part). If AC-ANS-15 fails, fix `answer_outcome.classify_outcome` or the bridge `verification` so a served related clip is `served`. | T2-03 (done) | No change to `ChatResponse.grounding_state` literal. | Revert the fix; keep the test as xfail with a link. |
| 2 | NEW-ANS-2 | Abstain cause and honest verification | Pass `abstain_reason` and `answerability` to `_abstain`; `verification.passed=False` for errors; `classify_outcome` maps `system_unavailable` to `error`; new reason `store_unavailable`; metrics `guru_abstain_cause_total`. AC-ANS-04, 23; RET AC-RET-17. Closes ANS-010 and RET-17. | NEW-ANS-1 | No new copy yet (keys only). | Revert; static copy unchanged. |
| 3 | NEW-ANS-3 | `build_public_answer_fields` and wire parity | `backend/app/answer_contract.py`; update the four writers; schemas; TS types; update `test_citation_contract.py` deliberately for `clip_ref` (PROPOSED D-PQ7). AC-ANS-10 to 14. Closes ANS-012. | NEW-ANS-2 | No UI change. Additive only. | Fields are additive; ignore them. |
| 4 | NEW-ANS-4 | Static copy keys and locale guard | Keys `answer.*`, `abstain.*`, `followup.*`; English copy; CI guard for missing keys; replace client English-string abstain detector. AC-ANS-24, 25. Overlaps T1-17, T1-20. | 3 | No translation by machine. | Revert keys. |
| 5 | NEW-ANS-5 | Modes on the teaching lane | Read `response_preferences` in the bridge; block selection only. AC-ANS-17. Closes ANS-009. | 3, 4 | No retrieval change. No new LLM call. | Setting `first_person_modes_enabled` (new, default off). |
| 6 | NEW-ANS-6 | Reflection and practice catalogue | `config/reflection_catalogue.yaml`, loader, selection, lint tests; move `_THEMATIC_INQUIRIES`; block rendering. AC-ANS-18 to 20. **Owner or faculty review of authorship (PROPOSED D-PQ8).** Closes ANS-013 (chat part). | 3, 4 | No generated reflection. | Setting off. |
| 7 | NEW-ANS-7 | Follow-up chips and `continue_from` | `ChatRequest.continue_from`; `exclude_clip_refs` after gates; chips; static "simpler" reply. AC-ANS-21, 22. Implements A28 options A and B only. | 3, 4; T5-05 later | No option C. | Setting off. |
| 8 | NEW-ANS-8 | Release invariants suite | `backend/tests/test_release_invariants.py`; CI job `release-invariants` required on `main`; `guru_quote_check_decline_total`. AC-ANS-01 to 09. | 3 | No statistical claim. | Remove the required status. |
| 9 | NEW-ANS-9 | Statistical gate tooling | Script that computes the bounds of 3.10.2 from a result file and fails below a floor given in `evals/release_floors.json` (owner-signed). AC-ANS-29. | NEW-RET-1, T2-04 | No floor chosen by an agent. | Remove the script call. |
| 10 | T4-04 | Distress topic versus state | **Reserved for a clinician.** Not started. | D-06 | | n/a |
| 11 | T1-20 + NEW-ANS-10 | Language review | Native review of static copy for the served languages. Human. AC-ANS-26, 27. | D-22 | | n/a |
| 12 | T5-03 / T5-04 | Assistant explanation layer | Per `MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` section 3.2. Block kind `assistant_explanation` is already in the schema. | **D-03** | | Flag off. |
| 13 | T5-06 | Language field on spans and labelled translation | After native review. | D-22 | | n/a |

Migration rules: no database migration. Settings added by these tasks each have a reader at the call site, tests for both states, and a line in the exact-cache fingerprint when they change served output.

---

## 9. Open questions

| ID | Question | Why it matters | Owner | Default if undecided |
|---|---|---|---|---|
| D-03 (existing) | Allow a labelled assistant explanation, generated reflection and labelled "simpler" rewrite? | Gates L3 to L5 and A28 option C. | Owner, then the teachers' organisation | No generated text. Static content only. |
| D-06 (existing) | Clinician engagement for topic-versus-state. | ANS-001, ANS-002. | Owner | Default distress behaviour stays. |
| D-22 (existing) | Priority Indic languages. | Review scope. | Owner | English only for new copy. |
| D-25 (existing) | Usefulness target and served-share floor. | Gates for section 3.10.2. | Owner | Report only. |
| PROPOSED D-PQ3 | Floors for quality metrics and meaning-preservation scores. | No baseline exists. | Owner | Report only. |
| PROPOSED D-PQ7 | Put the Qdrant point id on the wire as `clip_ref`? The sibling memory specification needs a clip id on the client. The current test forbids `point_id` on the wire. | Saved clips, reports, follow-up exclusion. | Owner | Yes. The id is a uuid5 over hash and offsets and holds no secret. |
| PROPOSED D-PQ8 | Who authored and who approves the reflection catalogue (the first four themes)? | A product-written spiritual question set needs an accountable author. | Owner and faculty | Owner approves; faculty reviews before public use. |
| PROPOSED D-PQ9 | For a system failure that blocks the check (scorer timeout), show "try again" copy instead of "no recording found"? | Honest state. It changes visible behaviour. | Owner | Yes. |

> **Update 2026-11-06 (batch 13, a33d6b8d):** Still PROPOSED. The report control shipped without it. See the update note under item 2 of the wire-field rules.

---

## 10. Verified, assumptions, unknowns

### Verified (read at `c9b42d3e`)

1. `ChatResponse` fields (`schemas/__init__.py:342-467`) and `Citation` (`:285-339`).
2. The three writers and their field differences (`orchestrator.py:142-193, 693-728`; `chat.py:1025-1070`).
3. The wire citation narrowing and the test that pins it (`orchestrator.py:512-600`; `tests/test_citation_contract.py:169-205`).
4. The bridge sets `verification.passed = is_direct and evidence_set_supported` (`first_person_bridge.py:1149`) and sets no `follow_up_suggestions`, `guidance_plan` or `answer_evidence`.
5. `response_preferences` is accepted and not read by the first-person route.
6. `clean_wire_speaker` rules (`attribution.py:70-100`).
7. The client derives "Related" from `verification.direct === false` and detects abstains by English strings (`ChatMessage.tsx:176-193, 236-244`).
8. The reflection catalogue is static English text (`quote_weaver.py:675-696`).
9. A cache hit re-runs the integrity gate on cached citation fields (`first_person_pipeline.py:3245, 3331`).

### Assumptions

1. A served related clip is reported as `abstained` by `grounding_state_for` (ANS-011). Unconfirmed until AC-ANS-15 runs.
2. Clients ignore unknown response fields and unknown block kinds. The TS mapper was read for citations only. Confirm in AC-ANS-14.
3. The point id is not a secret (a uuid5 over stored hash and offsets).

### Unknowns

1. The query-translation service and its budget.
2. Which model the answerability and rerank calls use (no dedicated setting).
3. Authorship and review of the reflection catalogue and of the five Indic static abstains.
4. Whether `ChatMessage.tsx` reads `relevancy_score` and `confidence_score` as visible UI or only into state.
5. Live behaviour of every `[LIVE-Q]` and `[LIVE-L]` item. No live system was contacted. No test was run in this session.
