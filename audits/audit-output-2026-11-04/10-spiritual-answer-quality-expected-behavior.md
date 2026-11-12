# 10 — Spiritual answer quality and expected behaviour

> **2026-11-06:** Superseded in part by `specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` (field-level wire schema, render rules per voice layer, release invariants). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: S3. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.

> **Erratum (lead, after the independent review in `26`).**
> 1. The anxiety trace (ANS-001) is **confirmed**. The independent review adds that the same question also matches the bridge's synthesis-shape regex ("the cause of", `first_person_bridge.py:81-89`). The bridge itself recognises that the question needs synthesis.
> 2. ANS-003 is **narrowed**. Grief, ego, attachment and happiness questions with no general-task word go to the **teaching lane**, not to a generic LLM (`off_topic_stage.py:591-607`). Only questions that mix a general-task word with an emotion word reach the general lane (`:625-669`). The taxonomy rows that say "→ general assistant" for those topics must be read as "→ teaching lane; served or abstained by the gates". ANS-003 is now P2.
> 3. ANS-002 is confirmed and stronger than stated: every MILD match becomes "gentle", so the MILD→MODERATE upgrade always runs (`serene_mind_engine.py:1698-1703`).
Line numbers were read at `main@46b808fb`. A range such as `:930-948` is approximate to about ±10 lines.
Related: `09` (harness and prompts), `14b` (safety), `18` (evaluation), `07`/`08` (S2, retrieval and multi-video), `03` (S4, FRs).

## 0. Summary

| # | Statement | Label |
|---|---|---|
| 1 | The live chat answer for a teaching question is one verbatim clip, a static abstain, or a static distress template. Nothing in between. | [V-STATIC] |
| 2 | "What is the cause of my anxiety?" is classified as personal distress (MODERATE) by one keyword. Under code defaults it receives a fixed distress template with helplines and no teaching. | [V-STATIC] |
| 3 | The bridge itself recognises that this question "needs synthesis, not one clip". In first-person-only mode it serves one clip anyway. | [V-STATIC] |
| 4 | Domain routing is a keyword regex. Grief, ego, jealousy, attachment, happiness, self-awareness and inner conflict do not match. Those questions go to a neutral general assistant (LLM prose, no teaching evidence). | [V-STATIC] regex simulation; [LIVE-L] to confirm end-to-end |
| 5 | Root `CLAUDE.md` tells agents that all guidance MUST be in the teachers' first-person "I" voice. The serving prompts forbid exactly that. The code is right. The agent guidance is dangerous. | [V-STATIC] |
| 6 | The mission's "complete answer" (understand → decompose → retrieve across videos → synthesise → relate → reflect → follow up) has no implementation on the live path. | [V-STATIC] |

Verdict for Pillar 2: the product today is a **verbatim clip retriever with safety lanes**, not an answer engine. That is a defensible integrity posture. It is not the product the mission describes.

---

## 1. Trace: "What is the cause of my anxiety?"

### 1.1 Configurations traced

| Config | Source | Key flags |
|---|---|---|
| A. Code defaults | `backend/app/config.py` | `first_person_chat_bridge_enabled=True` (l.416), `first_person_route_enabled=True` (l.222), `first_person_mode="retrieval_only"` (l.184), `first_person_llm_fallback_enabled=False` (l.437), `first_person_serve_weak_match=True` (l.444), `first_person_distress_serve_clip_enabled=False` (l.455), `first_person_relevance_model=""` (l.478), `distress_llm_escalation_enabled=False` (l.1650), `distress_llm_downgrade_enabled=False` (l.1637) |
| B. Owner's documented local config | Root `CLAUDE.md` invariants 21 and 24; `audits/evidence/public_release_phase4_phase5_state_2026-10-22.json:72` | Same as A, plus `FIRST_PERSON_DISTRESS_SERVE_CLIP_ENABLED=true` [DOC-CLAIM], `FIRST_PERSON_RELEVANCE_MODEL=anthropic/claude-haiku-5.5` [DOC-CLAIM] |

The real `backend/.env` is untracked. Config B is [LIVE-L].

### 1.2 Stage-by-stage (single-turn, signed-in, English)

| # | Stage / node | What happens | Evidence |
|---|---|---|---|
| 1 | `KillSwitchStage` | Passes. | `app/pipeline/stages/pipeline_builder.py` |
| 2 | `CacheCheckStage` | Exact `(language, message)` key. PR #76 bypasses shared caches on current or recent distress. | [V-GIT] PR #76 body |
| 3 | `RequestStateStage` | No translation. `prepare_user_memory` reads memory only with an active consent receipt. Healing-course assignment may run as a side effect (see `12`, MEM-003). | `app/orchestrator_utils.py:545-610`, `:861-930` |
| 4 | `InputGuardrailStage` | Topic rail. "anxiety" is not a blocked topic. Passes. | `guardrails/lightweight_handler.py` |
| 5 | `DistressStage` | `analyze_with_history` → `async_assess_distress` → `assess_distress`. The English MODERATE pattern `\b(stressed\|anxious\|anxiety\|panic\|...)\b` matches. Level = MODERATE (2). The LLM stage 2 runs only below MODERATE, so it is skipped. Not ≥ SEVERE, so no pre-emption. `_DISTRESS_KEYWORD_RE` also contains `anxiety`, so the proactive Serene Mind check runs. | `services/serene_mind_engine.py:368`, `:1890-1915`; `app/pipeline/stages/distress_stage.py:52-58`, `:283-300` |
| 6 | `CircuitBreaker`, `DoctrineCache`, `CasualShortCircuit` | Pass. | — |
| 7 | `OffTopicStage` | `anxi\w*` is in `_ON_TOPIC_RE`. First-person-only mode sets `domain_route="teaching"`. | `app/pipeline/stages/off_topic_stage.py:57-67`, `:640-655` |
| 8 | `BoundedComparison`, `Personalize` | Return None. | — |
| 9 | `GraphStage` → entry router | `first_person` module: enabled (A and B) and claims (`domain_route=="teaching"`). | `rag/pipeline_registry.py` `_first_person_enabled`, `_first_person_claims` |
| 10A | `first_person_node` → `_bridge` (config A) | `level_value (2) >= _DISTRESS_DECLINE_LEVEL (2)` and serve-clip flag False → `return None`. Node returns `{}`. Graph re-enters `parallel_start`. | `app/pipeline/stages/first_person_bridge.py:67`, `:682-684`; `rag/nodes/first_person.py`; `rag/graph_strategies.py:168-180` |
| 11A | General graph | `handle_distress_check` finds distress → `resolve_parallel` sets `intent="DISTRESS"`. Fast strategy → `handle_distress`. Standard strategy → `resolve_followup` → `navigate_and_hyde` (LLM) → retrieve → rerank → `grade_documents` (LLM batch) → `cross_teacher_reasoning` → `route_after_grading` returns `distress` → `handle_distress`. The retrieved documents are then discarded. | `rag/graph_strategies.py:95-141`, `:310-436`; `rag/nodes/intent.py:1865-1874` |
| 12A | `handle_distress` | Returns the Serene Mind template (`serene_mind.get_response` or `get_distress_response`): "I hear you, and I want you to know that your feelings are valid… Would you like me to guide you through a **Serene Mind meditation**…" plus a helpline block, plus a support line. `citations=[]`. | `rag/nodes/intent.py:1511-1680`; `rag/meditation.py:117-138` |
| 13A | `MeditationGenStage` | Needs citations. None exist. Skipped. | `app/pipeline/stages/meditation_gen_stage.py:60-75` |
| 10B | `_bridge` (config B) | `distress_compassion=True`. Continues. `_SYNTHESIS_SHAPE_RE` matches "the cause of". In first-person-only mode the bridge does not hand off. It serves a clip. | `first_person_bridge.py:81-89`, `:676-733` |
| 11B | `FirstPersonPipeline.execute` | Crisis pre-check → topic rail → serving-contract gate → exact cache → (v10 harness, if enabled) → hybrid retrieval → integrity gate → content-quality and standalone gates → LLM rerank (2.5 s, selection only) → answerability YES/NO (fast model, 16 tokens) → relevance score 0–3 on top 3 (min 3) → serve or abstain. HyDE is skipped for distress turns. | `services/first_person_pipeline.py:3546-5107`, `:1023-1103`, `:1450-1470` |
| 12B | Bridge assembly | On serve: answer = exact clip text only. Compassion framing goes into `safety_notices`. Hazardous-sentence and persona checks. Label "Related, not a direct answer" (no calibration profile). On abstain: the static compassion copy. | `first_person_bridge.py:960-1060` |

### 1.3 What the seeker receives

| Config | Output | Teaching present | Answers "the cause" |
|---|---|---|---|
| A (defaults) | Static distress template + helplines + support line. Offer of a Serene Mind meditation. | No | No |
| B (local) | Compassion framing + one verbatim clip about anxiety or fear, **or** compassion framing only. | Sometimes | Only if one clip happens to explain causes in the teacher's words. |

Served share on answerable questions under config B is [DOC-CLAIM] 24–31% (root `CLAUDE.md` invariant 24) and the owner-approved floor is 30% (`evals/first_person/grading_pass_bar.json` `min_served_share`).

### 1.4 Earliest failure point

| Order | Failure | File:line | Root cause |
|---|---|---|---|
| **1 (earliest)** | An inquiry *about* anxiety is treated as a seeker *in* distress. | `backend/services/serene_mind_engine.py:368` (MODERATE pattern list `:366-379`) | Lexical classifier. No question-form or topic-versus-state discrimination. The only LLM correction (`_maybe_llm_downgrade_severe`) can only lower SEVERE→MODERATE and is off by default. |
| 2 | The bridge declines MODERATE turns (config A). | `backend/app/pipeline/stages/first_person_bridge.py:682-684` | Safety-first decline added after the 2026-10-05 "my mother died" incident. Correct for grief disclosures. Wrong for topic questions. |
| 3 | The general lane is a template. It never uses the retrieved teachings (and in Standard it pays for retrieval and LLM grading first). | `backend/rag/nodes/intent.py:1511-1680`; `backend/rag/graph_strategies.py:95-99`, `:401` | Zero-synthesis invariant on the distress lane plus a Standard-strategy route that still runs the retrieval chain. |
| 4 | Even with a clip, the product cannot explain a cause. | `first_person_bridge.py:727-733` (synthesis shape detected, single clip served) | Answer architecture is "one exact clip or nothing". |

This confirms the task-list claim (`docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` §0, 2026-10-19 note) that a single emotion keyword makes a benign question MODERATE and makes the bridge decline. [V-STATIC]

---

## 2. Findings (answer behaviour)

### ANS-001 — A question about anxiety gets a crisis-style template, not a teaching
| Field | Value |
|---|---|
| Pillars | P2, P4 |
| Category | Answer intelligence / routing |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High (code path); Medium (exact output wording depends on `serene_mind.get_response`) |
| Evidence | §1.2 rows 5, 10A–12A |
| Actual behaviour | Config A: template + helplines, `citations=[]`. Config B: compassion framing + at most one clip. |
| Expected behaviour | A seeker asking *why* anxiety arises gets a grounded explanation of the teachers' view, with sources, and an optional practice. Helplines appear only when risk signals exist. |
| Root cause | Keyword distress classification (`serene_mind_engine.py:366-379`) plus MODERATE decline (`first_person_bridge.py:682`). |
| User impact | The most common seeker question class returns no teaching. The template presumes distress the user did not express. Trust erodes. |
| Downstream impact | Cache, memory and analytics record the turn as distress. Distress history inflates later turns (see SAFE-002). |
| Dependencies | Clinician review (the boundary is under an owner-recorded clinician decision, `audits/evidence/public_release_owner_packet_clinician_2026-10-22.md`). |
| Remediation | Add a topic-versus-state discriminator before the MODERATE decision: question form ("what/why/how … anxiety") without first-person state markers ("I feel", "I am", "I can't") → NONE or MILD-topic. Keep SEVERE/CRISIS untouched. Clinician signs off the rule and its test set. |
| Acceptance criteria | On a labelled set of ≥200 benign topic questions and ≥200 state disclosures (built under `18`), benign→MODERATE rate ≤5% and state-disclosure recall at MODERATE+ unchanged (no regression on any SEVERE/CRISIS item). |
| Regression test | Parametrised test over the labelled set; existing crisis suites (`evals/scenarios/tier3_crisis`) must stay green. |
| Implementation risk | High (safety code). Clinician-gated. |
| Verification | [V-STATIC]; [LIVE-L] for exact rendered text; [HUMAN] clinician |

### ANS-002 — Mild words become MODERATE in chat
| Field | Value |
|---|---|
| Pillars | P2, P4 |
| Severity | P1 |
| Type | Confirmed defect |
| Evidence | `serene_mind_engine.py:1700-1704` upgrades `MILD`+`gentle` to `MODERATE`. MILD list `:381-384` covers `tired, exhausted, drained, burnout, confused, lost, uncertain, stuck, struggling, uneasy, uncomfortable, restless, unsettled`. |
| Actual behaviour | "I am uncertain about my future" and "I feel lost and confused" route like distress (simulation in §4). |
| Expected behaviour | Uncertainty and confusion are central spiritual-inquiry themes. They should reach the teaching lane. |
| Root cause | Escalate-by-default design of `analyze_with_history`. |
| Remediation | Remove the unconditional MILD→MODERATE upgrade, or require a state marker. Clinician sign-off. |
| Acceptance criteria | Same labelled set as ANS-001; MILD-only messages never decline the bridge. |
| Regression test | Unit test on `analyze_with_history` with MILD-only inputs. |
| Implementation risk | Medium. |
| Verification | [V-STATIC] |

### ANS-003 — Keyword domain routing sends core teaching topics to a generic assistant
| Field | Value |
|---|---|
| Pillars | P2, P3 |
| Severity | P1 |
| Type | Probable defect |
| Confidence | Medium-High |
| Evidence | `_ON_TOPIC_RE` (`off_topic_stage.py:57-67`) has no `grief, ego, jealous, attach, happ, self-aware, conflict, guilt, shame`. Simulation (§4) shows these questions as non-teaching. Non-teaching, non-off-topic questions set `general_knowledge_mode=True` (`off_topic_stage.py:656-665`). The answerability prompt lists grief and fear as in scope (`first_person_pipeline.py:1329-1360`), so the two scope definitions disagree. |
| Actual behaviour | "How do I deal with grief after losing my father?", "What is ego?", "Why am I so attached to my children?", "How can I be truly happy?" get a neutral LLM answer from `GENERAL_ASSISTANT_SYSTEM_PROMPT`, with no teaching evidence. |
| Expected behaviour | These are teaching-domain questions. They reach the teaching lane. |
| Root cause | Hand-maintained regex as the domain classifier; a second, separate scope list inside the answerability prompt. |
| User impact | The product answers central spiritual questions like a general chatbot, which is the experience the mission rejects. |
| Remediation | One domain classifier with one scope definition shared by routing and answerability. Use an embedding-similarity router against the corpus topic map (OKF is allowed for routing, invariant 12) with the regex as a fast pre-filter, and fail toward the teaching lane for inner-life questions. |
| Acceptance criteria | On the taxonomy set in `18` (≥300 questions), teaching-domain recall ≥95%, and general-task precision ≥95%. |
| Regression test | Routing table test over the taxonomy set. |
| Implementation risk | Medium. Wrong routing toward teaching is safe (clip or abstain). Wrong routing toward general produces ungrounded prose. |
| Verification | [V-STATIC] (regex simulation); [LIVE-L] end-to-end |

### ANS-004 — The live architecture cannot produce a complete answer
| Field | Value |
|---|---|
| Pillars | P2 |
| Severity | P1 |
| Type | Product gap |
| Evidence | Bridge rebuilds the answer as exact quotes only (`first_person_bridge.py:943-948`). Synthesis-shaped questions are detected (`:81-89`) and served one clip anyway in first-person-only mode (`:727-747`). `first_person_second_quote_enabled=False` (`config.py:496`). Reflection questions moved to metadata (`first_person_pipeline.py:779-790` comment, `_ANSWER_BODY_SCHEMA_VERSION="evidence_only_v2"`). |
| Actual behaviour | One clip, a label, safety notices. No explanation, no multi-source synthesis, no personal connection, no follow-up. |
| Expected behaviour | Mission §2.2: depth chosen per question; direct answer, supporting teaching, explanation, sources, practice, reflection, follow-up. |
| Root cause | Owner decision 2026-10-11 (invariant 21) to forbid any generated text after a live incident where generation improvised a teaching. The decision closed the integrity hole by removing the capability instead of constraining it. |
| User impact | About 7 in 10 answerable questions abstain [DOC-CLAIM]. The rest get a clip that may not address the specific question. |
| Remediation | Introduce a **layered answer** (see §6): verbatim evidence layer (unchanged gates) + an explicitly labelled assistant-voice explanation layer that may only cite served evidence, with claim-level entailment checks. This needs an owner decision because it reverses invariant 21 for one layer. |
| Acceptance criteria | Defined in `18` §6 (blind human rubric: usefulness ≥4/5 on ≥70% of answerable items; 0 fabricated quotes; 0 misattributions; ≥95% of explanation claims entailed by cited clips). |
| Regression test | Golden set in `18`; quote-integrity tests (`tests/test_citation_contract.py`) remain. |
| Implementation risk | High (integrity). Gate it behind a default-off flag. |
| Verification | [V-STATIC]; [HUMAN] owner decision |

### ANS-005 — Agent guidance mandates teacher-voice impersonation; the code forbids it
| Field | Value |
|---|---|
| Pillars | P4, P3 |
| Severity | P1 |
| Type | Confirmed defect (governance / instruction conflict) |
| Evidence | Root `CLAUDE.md` "First-Person Voice Architecture & Invariants": "All teaching and guidance responses MUST be delivered directly in the first person ('I invite you to see...')… Detached 3rd-person… phrasing ('According to Sri Krishnaji...') is strictly prohibited." Against: `rag/prompts/system.py:122-184` `GURU_SYSTEM_PROMPT` ("Refer to a teacher in the third person, never as the founders themselves"), `GURU_VOICE_RULE` (`:199-212`), `domain/spiritual_ontology.py:303` `voice_policy="third_person_attribution_only"`, `rag/nodes/verification.py:372` (impersonation check). The same `CLAUDE.md` invariant 15 says zero generation. |
| Actual behaviour | Code enforces third person outside verified quotes. Guidance tells every coding agent the opposite. |
| Expected behaviour | One rule: teacher first person exists only inside verified verbatim quotation; the assistant speaks in its own voice. |
| Root cause | Stale guidance section never reconciled after the 2026-09-24 verbatim pivot. |
| User impact | None today. High regression risk: an agent "fixing" prompts per `CLAUDE.md` would create AI impersonation of living teachers. |
| Remediation | Rewrite that `CLAUDE.md` section to the voice-layer contract in §5. Add a lesson guard that fails on "MUST be delivered … in the first person" in agent docs. |
| Acceptance criteria | `rg -n "Direct Sacred Presence" CLAUDE.md AGENTS.md` returns nothing; a guard test exists. |
| Regression test | Guard in `scripts/guards/lesson_guards.py`; `tests/test_guru_voice_langhanam.py` stays. |
| Implementation risk | Low. |
| Verification | [V-STATIC] |

### ANS-006 — No depth control and no response modes on the live path
| Field | Value |
|---|---|
| Pillars | P2, P5 |
| Severity | P2 |
| Type | Product gap |
| Evidence | `response_length_instruction` exists only on the generating path (`rag/nodes/generation.py` prompt branches). The bridge has no depth parameter. |
| Remediation | Depth and mode fields in the answer plan (§6.2). "Tell me more" maps to the next evidence tier, not to longer prose. |
| Acceptance criteria | "Go deeper" on a served answer returns a second distinct clip or the explanation layer in ≥80% of cases where evidence exists. |
| Verification | [V-STATIC] |

### ANS-007 — Follow-up continuity is a string concatenation
| Field | Value |
|---|---|
| Pillars | P2, P5 |
| Severity | P2 |
| Type | Product gap |
| Evidence | `first_person_bridge.py:752-768`: if `_is_heuristic_followup` and no new topic, `retrieval_query = f"{last_user} — {retrieval_query}"`. No record of which clip was served, which facets were covered, or what the seeker asked to explore. |
| Remediation | Store a per-conversation `answer_trace` (served clip ids, facets, unanswered facets) server-side; resolve follow-ups against it; offer "another teaching on this", "a practice", "what does the other teacher say". |
| Acceptance criteria | Multi-turn golden items (`18` §5 M-items) pass ≥80%. |
| Verification | [V-STATIC] |

### ANS-008 — Multilingual seekers get English clips with translated glue
| Field | Value |
|---|---|
| Pillars | P2, P6 |
| Severity | P2 |
| Type | Product gap (by design) |
| Evidence | `_translate_glue_only` (`first_person_bridge.py:322-380`); invariant 16 "quotes never translated". |
| Actual behaviour | Correct for integrity. A Telugu seeker reads an English quote. |
| Remediation | Keep the quote untranslated. Add a clearly labelled "assistant translation (not the teacher's words)" toggle below the quote, reviewed by native speakers per language before enabling. |
| Acceptance criteria | Native-speaker review per language (human gate in `evals/native_speaker_review_packet.md`). |
| Verification | [V-STATIC]; [HUMAN] |

---

## 3. Question taxonomy: current versus specified behaviour

Legend for "Current": FP = first-person lane (clip or abstain); DT = distress template (config A); CF = compassion framing + clip or copy (config B); GA = general assistant LLM prose; CP = crisis pre-emption.

| Category | Example (synthetic) | Current (config A / B) | Specified behaviour |
|---|---|---|---|
| Anxiety | "What is the cause of my anxiety?" | DT / CF | Explanation of the teachers' view of the cause, 1–2 cited clips, optional short practice, no helplines unless risk markers. |
| Fear | "Why do I keep experiencing fear even when I know things will be fine?" | DT / CF | Synthesis across ≥2 sources if available (thought–fear relation), cited; reflection question optional. |
| Anger | "Why do I get angry so quickly with my family?" | DT / CF | Direct teaching + practice; relationship boundary only if abuse cues. |
| Loneliness | "I feel lonely even with people. Why?" | DT / CF (not teaching-routed: `_ON_TOPIC_RE` misses `lonely`; distress lane wins) | Acknowledge, teaching, practice; check-in line if state markers. |
| Relationships | "How do I heal my relationship with my mother?" | FP + relationship boundary | FP evidence + explanation; boundary when abuse cues; never advise reconciliation in abuse. |
| Attachment | "Why am I so attached to my children?" | **GA** (routing miss) | Teaching lane. |
| Happiness | "How can I be truly happy?" | **GA** (routing miss) | Teaching lane; direct answer first. |
| Failure | "I failed my exam and feel like a failure." | FP (`teachings` cue) or GA without the cue | Teaching lane; MILD acknowledgement; practical step. |
| Uncertainty | "I am uncertain about my future." | DT / CF (MILD→MODERATE) | Teaching lane; clarifying question if the decision is concrete. |
| Purpose | "What is the purpose of my life?" | FP | Synthesis; depth offer. |
| Inner conflict | "I want to quit but want security…" | **GA** | Teaching lane; never a decision on the seeker's behalf (answerability prompt already excludes "whether to quit"). |
| Self-awareness | "How do I become more self-aware?" | **GA** | Teaching lane + practice. |
| Spiritual practices | "How do I practice Soul Sync?" | FP or templated meditation path | Ordered steps from approved script; clip for context. |
| Guru-specific | "What does Sri Krishnaji say about the beautiful state?" | FP with teacher filter `both` (`first_person_bridge.py:861`) | Filter by named teacher; never attribute the other teacher's clip. |
| Cross-teacher | "How do Preethaji and Krishnaji differ on suffering?" | FP single clip (synthesis shape detected, one clip served) | Side-by-side, each attributed; state when sources do not support a contrast. |
| Grief | "How do I deal with grief after losing my father?" | **GA** if no distress keyword hit; DT if `grief` keyword route (pre-screen regex contains `grief`) | Compassion first; teaching; support line. Clinician-reviewed. |
| Multilingual | Telugu "నా ఆందోళనకు కారణం ఏమిటి?" | Indic regex distress scan; English clip, translated glue | Same as English; labelled assistant translation option. |
| Ambiguous | "Why is this happening to me?" | Depends on keywords; often GA | One clarifying question, then answer. |
| Multi-turn | "Tell me more" / "What about at work?" | Concatenated query; repeated keyword turns escalate to SEVERE (SAFE-002) | Resolve against `answer_trace`; never escalate on topic repetition. |
| Multi-video | "Why do I fear even when I know intellectually…?" | One clip | Evidence set across videos (S2 `07`), explanation layer citing each clip. |

---

## 4. Routing simulation (static)

Method: extracted `_ON_TOPIC_RE`, `_INNER_HELP_RE`, `_EXPLICIT_TEACHING_CUE_RE` from `off_topic_stage.py` and the English MODERATE/MILD lists from `serene_mind_engine.py:366-384` with an AST script; ran 20 synthetic questions. Script: scratchpad `s3/route_sim.py` (scratchpad, not committed). This simulates only these regexes, not every stage. [V-STATIC]

| Question (synthetic) | Distress level (chat) | Teaching cue | Inner-help cue |
|---|---|---|---|
| What is the cause of my anxiety? | MODERATE | yes | yes |
| Why do I keep experiencing fear… | MODERATE | yes | yes |
| Why do I get angry so quickly… | MODERATE | yes | yes |
| I feel lonely even when I am with people. Why? | MODERATE | no | yes |
| How do I heal my relationship with my mother? | NONE | yes | no |
| Why am I so attached to my children? | NONE | **no** | no |
| How can I be truly happy? | NONE | **no** | no |
| I failed my exam… What do the teachings say? | NONE | yes (cue "teachings") | no |
| I am uncertain about my future… | MILD→MODERATE | no | no |
| What is the purpose of my life? | NONE | yes | no |
| …resolve this inner conflict? | NONE | **no** | no |
| How do I become more self-aware? | NONE | **no** | no |
| How do I practice Soul Sync? | NONE | yes | no |
| What does Sri Krishnaji say about the beautiful state? | NONE | yes | no |
| Difference between Preethaji and Krishnaji on suffering | NONE | yes | no |
| I feel lost and confused about everything. | MILD→MODERATE | no | no |
| Why do I feel jealous of my friend's success? | NONE | **no** | no |
| How do I deal with grief after losing my father? | NONE | **no** | no |
| What is ego? | NONE | **no** | no |
| Why do I overthink at night? | NONE | no | yes |

---

## 5. Voice-layer separation (contract)

### 5.1 Six layers

| Layer | Who speaks | Allowed source | Rendering rule | Today |
|---|---|---|---|---|
| L1 Verbatim quote | Teacher | Exact clip text that passed integrity, speaker and rights gates | Quote block, speaker label only from stored metadata, playback link, "unverified clip" when `speaker_verified` absent | Live (bridge) |
| L2 Faithful paraphrase | Assistant, about the teacher | One cited clip | Third person, "In this talk, Sri X describes…", citation required | Not built (forbidden by invariant 21) |
| L3 Explanation | Assistant | Cited clips | Assistant voice, no teacher "I", claims entailment-checked | Generating path only (dormant for teaching topics) |
| L4 Interpretation / application | Assistant | Cited clips + user's stated situation | Labelled "How this may apply to you (assistant's reflection)" | Not built |
| L5 Cross-source synthesis | Assistant | ≥2 cited clips, each attributed | Per-claim citations; contradiction or context-difference note | Not built |
| L6 System suggestion | Product | Approved practice scripts, helplines | Labelled as product guidance | Live (templates, boundaries) |

### 5.2 Paths that could put generated text in a teacher's voice or present it as a quote

| Path | Status | Risk | Evidence |
|---|---|---|---|
| Bridge answer | Live | **Low**. Answer is rebuilt from exact clip text; a clip that is not a substring of the answer is refused. | `first_person_bridge.py:930-948` |
| Quote weaver scaffolding (OPENING/CONNECTIVE/QUESTIONS) | Live inside the pipeline, stripped by the bridge | Low on chat. LLM writes "Sri Krishnaji observes:" pointers; on any route that serves `answer_text` directly they reach the user. | `services/quote_weaver.py:1046-1087` |
| Quote weaver editorial rewrite ("Elite Spiritual Manuscript Editor") | Dormant: `first_person_editorial_rewrite_enabled=False` (`config.py:189`) | **High if enabled**. The LLM is told to proofread, excise and replace pronouns in the teachers' words ("replace 'him living with 10 heads' with 'Ravana living with ten heads'") while calling the output "the Gurus' authentic spoken words". | `services/quote_weaver.py:1090-1154` (see AI-006 in `09`) |
| Generating path + voice register | Live for general-mode answers (default `langhanam_voice_enabled=True`, `config.py:1888`) | Medium. "THE TEACHER'S VOICE — {display}. Match this register" makes model prose imitate the teachers' cadence and second-person address. Rules forbid invented "I". | `services/voice/register.py:276-334`; `rag/nodes/generation.py:1285-1335`, `:3250` (see AI-003) |
| `handle_distress` with first-person text | Live, gated | Low. Only pipeline-gated text; persona adherence check; unverifiable quotes unquoted. | `rag/nodes/intent.py:1560-1660` |
| Meditation generation | Live when proactive Serene Mind + citations | Low-Medium. Rewrites step instructions "grounded in approved source material, not an imitation of a named person"; output is AI text under a meditation structure. Not labelled as AI-written in the response contract. | `app/pipeline/stages/meditation_gen_stage.py:60-110`; `rag/prompts/system.py:390-440` |
| Translation of quotes | Blocked | Low. Glue only. | `first_person_bridge.py:322-380` |
| Frontend | Renders "Related teaching — not a direct answer"; "unverified clip" when not voice-verified | Low. | `src/components/chat/ChatMessage.tsx:304`, `:415-432`; `src/lib/chat/types.ts:289-300` |
| `REFERENCE_VOICE` constant | Dead (benchmarks only) | Low. A "cleaned" paraphrase of a discourse, with health claims, stored in a serving module. Remove. | `services/guru_voice_langhanam.py:15-35` |

Conclusion: on the live chat path, impersonation risk is controlled. The risk sits in dormant capability (editorial rewrite) and in agent guidance (ANS-005).

---

## 6. Target answer architecture

### 6.1 Answer plan (one structured object per turn)

```
AnswerPlan {
  intent: teaching | practice | personal_inquiry | cross_teacher | factual_about_teachers | general | safety
  state_signal: none | mild | moderate | severe | crisis      # from the distress engine, state-vs-topic aware
  depth: short | medium | deep                                # default by intent; user can change
  facets: [ {facet_id, question_part} ]                       # decomposition only when the question has parts
  teacher_scope: krishnaji | preethaji | both | unspecified
  evidence: [ {clip_id, video_id, speaker, start_ms, end_ms, facet_id, gate_status} ]
  layers: [L1..L6]                                            # which layers this answer may use
  follow_ups: [ {kind: deeper|practice|other_teacher|related, evidence_available: bool} ]
}
```

### 6.2 Default composition per intent

| Intent | Short | Medium (default) | Deep |
|---|---|---|---|
| Teaching ("what is X") | L1 one clip | L1 + L3 two-sentence explanation | L1 ×2–3 + L5 synthesis + follow-ups |
| Personal inquiry ("why do I…") | L3 direct answer + L1 | L3 + L1 + L4 one reflection | + L5 + practice (L6) |
| Practice | L6 steps | L6 + L1 context clip | + L3 rationale |
| Cross-teacher | L1 per teacher | L1 per teacher + L5 contrast | + context-difference notes |
| Safety (MODERATE state) | L6 compassion + L1 if gated | same | never deep |
| Safety (SEVERE/CRISIS) | L6 helplines first | same | same |

Rules:
1. Direct answer first. Reflection is optional and at most one question.
2. Every L3–L5 sentence that states a teaching carries a citation to an L1 clip shown in the same answer.
3. A claim that fails entailment against its cited clip is removed, not reworded.
4. No L2–L5 text may contain a first-person sentence attributed to a teacher.
5. If no L1 evidence passes gates, the answer abstains on teaching content. It may still offer L6.

### 6.3 Clarifying questions

Ask one clarifying question only when (a) the question has two or more incompatible readings that retrieve disjoint evidence sets, or (b) the seeker asks for a decision only they can make. Never ask when a direct answer is possible.

---

## 7. Cross-references

- Harness, prompts, model routing: `09`.
- Safety classifier changes and clinician gates: `14b`.
- Multi-video evidence assembly and retrieval: `07`, `08` (S2).
- Memory-driven continuity: `12`.
- Golden items for every taxonomy row: `18`.
- FRs for depth, modes, follow-ups: `03` (S4).
