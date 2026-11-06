# 11 — Sri Krishnaji, Sri Preethaji and future-teacher extensibility

> **2026-11-06:** Superseded in part by `specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` (registry field rules, path:line table at `c9b42d3e`, per-step onboarding tests). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: S4. Audit target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.

Scope: teacher identity, attribution, hardcoded names, the teacher registry, corpus per teacher, shared versus distinct teachings, and the steps to add a future teacher. Speaker-verification internals (ECAPA, diarisation) belong to doc 07 (S2). Answer behaviour belongs to doc 10 (S3).

---

## 1. Summary

- A teacher registry already exists: `backend/config/gurus.yaml` + `backend/services/guru_registry.py`. Its header says: "Adding a teacher should not require routing-code edits." [V-STATIC]
- Adoption is partial. 13 backend modules import the registry. 128 runtime source files still contain 621 literal occurrences of "Krishnaji" or "Preethaji" [V-STATIC, counts below].
- At least six parallel teacher registries exist, and they disagree (§3).
- Seed data and prompts define other teachers (Sadhguru, ISKCON) and an unreleased "private teachings" persona that have no corpus and no rights basis (IP-006 in doc 14c).
- Quotations attributed to the teachers appear outside the verbatim clip path with no verifiable source (GURU-012).
- Conclusion: a new teacher cannot be added today by configuration alone. Safety guardrails, doctrine terms, entity linking, ontology and UI content all need code edits.

---

## 2. Hardcoded teacher names: counts

Method: `rg -i -c "krishnaji|preethaji"` over the snapshot. Tests, locale files and generated Supabase types are excluded. [V-STATIC]

| Scope | Files | Occurrences |
|---|---|---|
| All code and data under `backend/`, `src/`, `config/`, `scripts/` (`*.py, *.ts, *.tsx, *.json, *.yaml`) | 310 | 4,220 |
| Runtime code only (`backend/app`, `backend/rag`, `backend/services`, `backend/guardrails`, `backend/domain`, `backend/ingest`, `src/` non-locale) | 128 | 621 |

Largest runtime holders:

| File | Count | Role |
|---|---|---|
| `backend/services/doctrine_terms.py` | 38 | ASR corrections and doctrine vocabulary |
| `backend/app/db/seed_ontology.py` | 31 | Ontology seed (also seeds Sadhguru: 12 refs) |
| `backend/rag/nodes/entity_linking.py` | 24 | Entity linking |
| `backend/services/intelligent_metadata_extractor.py` | 23 | Ingestion metadata |
| `backend/guardrails/lightweight_handler.py` | 22 | Impersonation-refusal regexes (lines 267–274) |
| `backend/domain/spiritual_ontology.py` | 20 | Ontology |
| `backend/services/lightrag_service.py` | 19 | Graph |
| `backend/app/api/teachings.py` | 18 | Wisdom tips with attributed quotations |
| `backend/services/quote_fidelity.py` | 15 | Quote checks |
| `backend/services/guru_brain/tone_extractor.py` | 15 | Tone |
| `src/components/meditation/meditationSteps.ts` | 13 | Meditation script + voice |
| `backend/services/voice/register.py` | 12 | Voice register |
| `backend/services/guru_brain/persona_discriminator.py` | 11 | Speaker persona |
| `src/components/kg/KGConceptMap.tsx` | 10 | Concept map UI |

`teacher_id`/`guru_id` string literals in code (non-test): `krishnaji` 63, `preethaji` 58, `ekam` 34, `preethaji_krishnaji` 7, `both` 5 [V-STATIC, rg literal count].

Registry importers (13): `rag/prompts/system.py`, `rag/nodes/citation_extractor.py`, `rag/nodes/generation.py`, `app/pipeline/stages/first_person_bridge.py`, `app/pipeline/stages/off_topic_stage.py`, `services/first_person_store.py`, `services/first_person_pipeline.py`, `services/voice/register.py`, `services/guru_brain/guru_brain_service.py`, `services/qdrant/searcher.py`, `services/embedding_service.py`, and the registry itself [V-STATIC].

Interpretation: the first-person serving path (store, pipeline, bridge, searcher) uses the registry. The guardrails, ontology, graph, metadata extraction, wisdom tips and frontend do not.

---

## 3. Parallel teacher registries

| # | Registry | Location | Teachers it defines | Read by |
|---|---|---|---|---|
| R1 | `gurus.yaml` | `backend/config/gurus.yaml` | `preethaji`, `krishnaji`; org `ekam`; `shared_primary_teacher_id: preethaji_krishnaji` | `guru_registry.py` and its 12 importers |
| R2 | Supabase `gurus` table | `supabase/migrations/20260703170000_gurus_and_configurations.sql:52–56` | `preethaji_krishnaji`, `sadhguru`, `iskcon`, each with a Qdrant `collection_name` (`spiritual_wisdom`, `sadhguru_wisdom`, `iskcon_wisdom`) | `assistant_configurations` seeds; reading code not traced [INF] |
| R3 | Supabase `assistants` table | `supabase/migrations/20260621033728_…sql:94–106` | `general`, `relationship`, `sky` ("SKY Teachings (Private) — Unreleased private teachings — invite only") | `GET /api/assistants`, `useAssistants.ts` |
| R4 | `ALLOWED_ASSISTANT_SLUGS` setting | `backend/app/config.py:1178` default `"guru,preethaji,krishnaji,serene_mind"` | 4 slugs | `backend/app/assistant_registry.py:31` |
| R5 | `ASSISTANT_CORPUS_REGISTRY` JSON setting | `backend/app/assistant_registry.py:38–80` | per-slug `corpus_id`, `teacher_id`, `rights_status`, `rollout_enabled` | assistant scope resolution |
| R6 | Teacher personalities | `backend/services/prompt_store.py:45` (`"sadhguru": "Speak with the direct, earthy, and pragmatic tone of a yogi."`); `config.py:781` example | sadhguru, preethaji | `get_teacher_personality`, `build_teacher_prompt` |
| R7 | External-teacher detection | `backend/services/teacher_attribution.py:59–68` | sadhguru, amma_bhagavan, iskcon (detection only) | ingestion attribution |

The frontend and backend disagree on assistant slugs:

- The UI default slug is `general` (`src/hooks/useAssistants.ts:27`), which the client omits from the request (`src/lib/chat/assistant.ts:10`).
- Any other DB slug (`relationship`, `sky`) is not in R4. The backend then raises `403 Assistant unavailable` (`backend/app/assistant_authorization.py:242`).
- So the switcher (`ChatComposer.tsx:462`) can only work if the catalog endpoint filters to approved scopes. It fails closed otherwise. [V-STATIC; live catalogue contents [LIVE-R]]

Payload field names also differ:

- The chat corpus uses `teacher_id`. Root `CLAUDE.md` states it is not uniform: 4,337 of 12,904 points are `ekam`; others are `preethaji_krishnaji` and `krishnaji` [DOC-CLAIM].
- The v10 first-person payload uses `guru_id` (`krishnaji`, `preethaji`) [V-STATIC, served-tier JSONL].

---

## 4. Corpus inventory per teacher (repository evidence)

| Source | Krishnaji | Preethaji | Total | Label |
|---|---|---|---|---|
| v10 served tier `local_review_candidate` (spans) | 691 | 838 | 1,529 | [V-STATIC] `audits/evidence/public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl` |
| v10 served tier distinct videos (a video can carry both) | 211 | 249 | 445 distinct | [V-STATIC] |
| v10 served-tier span duration | — | — | median 19.0 s, p90 71.2 s, max 178.8 s | [V-STATIC] `audio_end_ms − audio_start_ms` |
| Speaker-conflict rows held back | — | — | 45 | [V-STATIC] decision form |
| `first_person_v8` | 1,051 | 750 | 1,801 | [DOC-CLAIM] root `CLAUDE.md` invariant 23 |
| Rights manifest assets | — | — | 751 (702 channel-owner confirmed, 2 video-owner, 1 pending, 46 missing evidence) | [DOC-CLAIM] decision form |

Language: the served-tier records carry no language field [V-STATIC: no key matching `lang`]. Multilingual representation of the teachers' own speech cannot be measured from repository evidence. It needs the live payloads [LIVE-Q] or the audio manifest [LIVE-L].

---

## 5. Findings

### GURU-010 — The registry exists but most teacher-specific logic bypasses it
| Field | Value |
|---|---|
| Pillars | P4, P3 |
| Category | Extensibility |
| Severity | P2 |
| Type | Architectural risk |
| Confidence | High |
| Evidence | §2 counts; §3 R1–R7; `backend/guardrails/lightweight_handler.py:267–274` hardcodes impersonation patterns for the two names only. |
| Actual behaviour | Adding a teacher to `gurus.yaml` changes serving filters and labels. It does not extend impersonation refusal, doctrine vocabulary, entity linking, ontology, tips or UI copy. |
| Expected behaviour | One source of truth drives every teacher-specific behaviour, including safety. |
| Root cause | The registry was introduced after the other modules. No guard prevents new literals. |
| User impact | For a future teacher, "pretend you are <new teacher>" would not be refused by the lightweight guardrail. |
| Remediation | Generate guardrail patterns, doctrine aliases and UI labels from the registry. Add a lesson guard that rejects new teacher-name literals outside `gurus.yaml`, fixtures and locale files. |
| Acceptance criteria | Adding a test teacher in a fixture registry makes the impersonation guardrail refuse "speak as <test teacher>" with no code edit. |
| Regression test | Parametrised guardrail test over all registry teachers. |
| Implementation risk | Medium: many modules. Do it module by module. |
| Verification | [V-STATIC] |

### GURU-011 — Data and prompts define other teachers and a private-teachings persona
See IP-006 in doc 14c for evidence and remediation. Severity P2. Type: confirmed defect (dormant data). This finding is listed here because it also violates the attribution rule: a "speak from the perspective of Sadhguru" prompt is teacher impersonation by design. [V-STATIC]

### GURU-012 — Quotations attributed to the teachers appear without a verifiable source
| Field | Value |
|---|---|
| Pillars | P4, P2 |
| Category | Attribution integrity |
| Severity | P1 |
| Type | Confirmed defect |
| Confidence | High that no video id or timestamp is attached. Unknown whether the wording is exact. |
| Evidence | `backend/app/api/teachings.py:60–141` `CURATED_FALLBACK_TIPS`: quoted sentences with `teacher: "Sri Preethaji & Sri Krishnaji"` or `"Sri Preethaji"` and sources such as "Ekam Discourses", "Inner Truth Discourse", "World Tour Teachings" (no video id, no timestamp). `src/lib/healingCourses.ts:59`: "Sri Krishnaji says all lingering suffering is self-centric thinking…" (a prompt string that puts a claim in the teacher's mouth). `src/components/chat/DeepenAndTuneBar.tsx:62–102`: hand-written concepts with per-teacher attribution (behind `VITE_ENABLE_DEEPEN_BAR`, default off; `src/lib/featureFlags.ts` comment admits "per-teacher attributions that no source backs"). |
| Actual behaviour | Wisdom tips are shown while an answer generates (`/api/teachings/tips`, `useWisdomTips.ts`) and carry teacher names. |
| Expected behaviour | Root `src/CLAUDE.md`: "Never present host or AI text as the teacher's." Every attributed quotation carries a video id and time window and passes the exact-substring check, or it is labelled as a paraphrase without quotation marks. |
| Root cause | Static content was written before the verbatim rules. |
| User impact | A seeker may repeat a sentence as the teacher's words when its source cannot be checked. Reviewers from the teachers' team would see this first. |
| Remediation | Replace curated tips with clips from the verbatim store, or label them "paraphrase" and remove quotation styling. Remove "Sri Krishnaji says" from prompt strings. Delete the Deepen bar's hand-written attributions. |
| Acceptance criteria | `rg -n "teacher\":" backend/app/api/teachings.py` shows only entries with `video_id` and `start_ms`. A test asserts that every attributed tip resolves to a stored verbatim span. |
| Regression test | Unit test over the tip library. |
| Implementation risk | Low. |
| Verification | [V-STATIC] |

### GURU-013 — Two identifier vocabularies for the same teachers
| Field | Value |
|---|---|
| Pillars | P3, P4 |
| Category | Data consistency |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `teacher_id` (chat corpus; values `ekam`, `preethaji_krishnaji`, `krishnaji`, `preethaji`) versus `guru_id` (v10); `shared_primary_teacher_id: preethaji_krishnaji` in `gurus.yaml`; `both` literal in code |
| Actual behaviour | Filters must translate between `ekam`, `preethaji_krishnaji`, `both` and individual ids. |
| Expected behaviour | One canonical teacher id per person, a separate organisation id, and a separate attribution mode (`single`, `joint`, `unknown`). |
| Remediation | Define the canonical model in §6. Migrate payloads with a dry-run → snapshot → apply sequence (S2 owns the migration). |
| Acceptance criteria | A Qdrant facet count shows only registry ids in the teacher field [LIVE-Q]. |
| Verification | [V-STATIC]; live distribution [LIVE-Q] |

### GURU-014 — Shared and distinct teachings have no attribution rule
| Field | Value |
|---|---|
| Pillars | P4, P2 |
| Category | Attribution policy |
| Severity | P2 |
| Type | Product gap |
| Confidence | Medium |
| Evidence | `gurus.yaml` defines `shared_attribution_ids` but no rule for when joint attribution is allowed. Wisdom tips use "Sri Preethaji & Sri Krishnaji" for single sentences. 45 speaker-conflict rows exist. |
| Expected behaviour | A sentence is attributed to the person whose voice says it. Joint attribution is allowed only for jointly authored published works (for example a co-authored book), and is labelled as such. Comparisons between the two teachers are shown as separate clips, never merged into one statement. |
| Remediation | Write the rule in the registry (`attribution_mode`) and enforce it in citation construction. Ask the teachers' team to confirm it (doc 23 D7). |
| Verification | [V-STATIC]; policy [HUMAN] |

---

## 6. Minimal teacher and content registry (target design)

Principle: one file is the source of truth. Code generates everything else from it. Do not add a new database for this.

Location: keep `backend/config/gurus.yaml`. Extend it. Generate a typed TypeScript constant for the frontend at build time. Remove R2, R3 seeds, R4, R5 and R6 after migration.

```yaml
schema: teacher-registry-v2
teachers:
  - id: krishnaji                 # canonical, immutable
    display_label: Sri Krishnaji  # only label shown after speaker verification
    aliases: ['(?:sri\s+)?krishnaji']
    voice_profile_ref: ecapa/krishnaji/<sha256>   # S2 owns
    status: active                # active | onboarding | retired
organizations:
  - id: ekam
    label: Ekam / O&O Academy
    teacher_ids: [krishnaji, preethaji]
sources:                          # one row per channel or publication
  - id: yt:ekam-official
    kind: youtube_channel
    organization_id: ekam
    rights_grant_ref: grants/ekam-2026-xx   # private evidence store, sha256
    allowed_uses: [serve_clip, show_transcript]
attribution_policy:
  joint_attribution_allowed_for: [published_coauthored_work]
  unknown_speaker_label: "unverified clip"
corpora:
  - id: fp-context-v10
    collection: first_person_v10
    teacher_ids: [krishnaji, preethaji]
    status: serving
```

Rules the code must enforce from this file:

1. Speaker allowlist, serve filters, display labels and attribution tags come from `teachers`.
2. Impersonation-refusal patterns are generated from `teachers[].aliases`.
3. Serving requires `sources[].rights_grant_ref` with `allowed_uses` containing the use.
4. Assistant personas are not configurable per teacher. The assistant always speaks in its own voice (doc 10).
5. A CI guard fails on teacher-name literals outside the registry, fixtures and locale files.

---

## 7. Onboarding a future teacher (target procedure)

| Step | Action | Gate |
|---|---|---|
| 1 | Record a rights grant from the teacher's organisation: content, uses, term, contact for corrections. | Written grant stored privately; hash in registry. [HUMAN] |
| 2 | Add the teacher with `status: onboarding`. | CI guard passes; nothing serves. |
| 3 | Obtain source media from the rights holder. Do not scrape. | `permission_ref` on every archived file (doc 14c IP-004). |
| 4 | Build a voice profile from clean reference audio supplied by the organisation. | S2 procedure; human spot check of 50 spans. |
| 5 | Ingest into a new collection. Run the integrity, content-quality and speaker gates. | Data gate (`scripts/ops/data_quality_audit.py`) passes. |
| 6 | Run the review question set (doc 23 §3) adapted to this teacher. | Two independent raters; agreement recorded. |
| 7 | Teacher's team reviews 30–50 answers. | Written approval. [HUMAN] |
| 8 | Set `status: active`. Enable the corpus. | Release gate (doc 23) passes on a clean checkout. |
| 9 | Monitor correction reports for 30 days. | Correction response time agreed (doc 23 D6). |

Steps 2, 5 and 8 need no routing-code edits once GURU-010 is fixed.

## Cross-references

- Rights: `14c-content-permissions-and-ip-register.md`
- Speaker verification and lineage: `06-data-ingestion-quality-lineage.md`, `07-video-audio-multisource-synthesis.md` (S2)
- Voice-layer separation and assistant voice: `10-spiritual-answer-quality-expected-behavior.md` (S3)
- Review package: `23-guru-review-and-release-readiness-package.md`
