# Teacher knowledge model, knowledge graph status and future-teacher extensibility (implementation specification)

## 0. Header

| Field | Value |
|---|---|
| Purpose | Give an implementation agent everything needed to build the teacher (guru) registry v2, the registry-driven replacement of hardcoded teacher logic, the onboarding procedure for a new teacher, and the decision on the knowledge graph (brief Part 6.5), without re-investigating the code. |
| Status | **Partial.** Sections 3.1 to 3.6 and the hardcoded-literal replacement (3.8) are implementation-ready. Joint attribution (3.4), per-source rights vocabulary (3.3) and graph retirement (3.9) are decision-blocked. See section 9. |
| Date | 2026-11-05 |
| Code head | `c9b42d3e` on `feature/audit-strengthen-rag-qdrant` |
| Depends on decisions | Existing: D-05 (ADR-005 graph), D-12 (voice rights), D-13 (broadcaster content), D-20 (other-teacher seeds), D-03 (ADR-001). ADR-013 (teacher registry) is Accepted. Proposed here: D-PG1 to D-PG8 (section 9). |
| Finding IDs | GURU-010, GURU-011, GURU-012 (partial), GURU-013, GURU-014, IP-005, IP-006. Status source: `FINAL_PENDING_WORK_REGISTER.md`. |
| Evidence labels | As in `CONVENTIONS.md`. Every `path:line` was read at `c9b42d3e` in this session unless marked [DOC-CLAIM]. |

Rules that bind this specification (root `CLAUDE.md`, checked against code in section 2):

1. Teachers' words appear only as verbatim stored spans with the correct speaker. The assistant never speaks in a teacher's first person.
2. `speaker_verified` is copied from the stored clip. It is never inferred.
3. The serve-time integrity gate keeps a teacher allowlist. An unlisted speaker is quarantined.
4. OKF (`memory/okf/compiled.json`) is a summary. It is never rendered as a teacher's voice and never placed in `citations[]`.
5. Zero generated teaching text on the first-person route. An LLM may pick clip indices or score. Nothing more.
6. A comparison of two teachers shows both positions as separate clips. No text reconciles them in a teacher's voice.

If a requested capability conflicts with a rule, the section gives (a) a compliant variant buildable now and (b) a decision-gated variant that names the decision. (b) is never presented as decided.

---

## 1. Existing coverage and exactly what it lacks

| Existing document | What it covers | What it lacks (this specification adds it) |
|---|---|---|
| `11` §2 to §4 | Literal counts, seven parallel registries R1 to R7, corpus counts per teacher. | Counts were taken at `main@46b808fb`. Section 2.4 gives the path:line table at `c9b42d3e` and a replacement for each row. |
| `11` §5 (GURU-010 to GURU-014) | Findings and one-line remediation. | Acceptance tests by file and case; ordering; rollback. |
| `11` §6 | A YAML sketch of registry v2 and five rules. | Field-level validation, ID rules, attribution model, rights path, versioning, conflict contract, loader interface, failure behaviour. |
| `11` §7 | Nine-step onboarding table with gates. | A test for each step and the exact files each step touches. |
| `17` ADR-005, ADR-013 | Decisions: graph removal (Proposed), registry as single source (Accepted). | Evidence of what the graph does on the request path today; the exact change list. |
| `19` §6 N-05, N-13 | Do-not-build entries (graph on serving path; other-teacher personas). | None. This specification respects both. |
| `20` T8-01, T8-02, T3-07, T1-04, T3-11 | Task titles and exit criteria. | PR-sized split in section 8. |
| `14c` IP-005, IP-006 | Rights risks for broadcaster content and other-teacher seeds. | Where rights live in the registry and how serving checks them. |

---

## 2. Current state (verified at `c9b42d3e`)

### 2.1 The registry is version 1

| Fact | Evidence | Label |
|---|---|---|
| `gurus.yaml` holds 2 teachers (`preethaji`, `krishnaji`), 1 organisation (`ekam`), `shared_primary_teacher_id: preethaji_krishnaji`, `shared_attribution_ids`. It holds no sources, no rights, no attribution policy, no voice reference, no status. | `backend/config/gurus.yaml:1-30` | [V-STATIC] |
| The loader returns `{}` on any parse error. An empty registry gives an empty speaker allowlist, so every clip is quarantined (fail closed). The loader logs the error. Startup does not fail. | `backend/services/guru_registry.py:25-36`, `:75-76` | [V-STATIC] |
| The loader defines no schema validation. An invalid entry is skipped with a warning. | `backend/services/guru_registry.py:53-59` | [V-STATIC] |
| Public API: `allowed_speaker_labels`, `label_for`, `attribution_tag_for`, `voice_teacher_labels`, `neutral_voice_id`, `requested_gurus`, `resolve_guru_id`, `shared_attribution`, `match_organization`, `is_shared_guru_scope`. An unknown teacher filter returns `None`, so a caller cannot treat it as "no filter". | `backend/services/guru_registry.py:75-207`, docstring `:131-134` | [V-STATIC] |
| The literals `both`, `all`, `shared` are hardcoded in the registry module. | `backend/services/guru_registry.py:202` | [V-STATIC] |
| ADR-013 is **not** built. No `sources`, `attribution_policy`, `voice_profile_ref`, `status` or generated guardrail patterns exist. T8-01 and T8-02 are Open. | `FINAL_PENDING_WORK_REGISTER.md` (GURU-010 row); grep of `gurus.yaml` | [V-STATIC] |
| A test proves a new teacher resolves from a fixture registry with no code change. It covers `resolve_guru_id`, `requested_gurus` and `allowed_speaker_labels` only. | `backend/tests/test_guru_registry_and_modes.py:184-210` | [V-STATIC] |

### 2.2 Who reads the registry

Importers (12 modules besides the registry): `services/first_person_store.py`, `services/first_person_pipeline.py`, `services/voice/register.py`, `services/qdrant/searcher.py`, `services/embedding_service.py`, `services/guru_brain/guru_brain_service.py`, `services/teacher_attribution.py`, `rag/nodes/generation.py`, `rag/nodes/citation_extractor.py`, `rag/prompts/system.py`, `app/pipeline/stages/off_topic_stage.py`, `app/pipeline/stages/first_person_bridge.py` [V-STATIC, `grep -rl guru_registry`].

Serving behaviour that already follows the registry:

| Behaviour | Evidence |
|---|---|
| Speaker allowlist captured at import time from registry labels. | `backend/services/first_person_store.py:63`, `backend/services/first_person_pipeline.py:178-184` |
| Integrity gate rejects an unlisted speaker (hash, speaker, artefact, dangling conjunction). | `backend/services/first_person_pipeline.py:436-447` |
| A seeker who names exactly one teacher gets that teacher's clips only. Naming both, or none, searches all. | `backend/services/first_person_pipeline.py:158-174` (`_BOTH_RE`, `requested_teacher`) |
| Qdrant teacher filter resolves ids through the registry. An unregistered id becomes an exact `teacher_id` match. A registered id matches `teacher_ids` or `teacher_id`, including legacy ids. | `backend/services/qdrant/searcher.py:161-185` |
| v10 span filter uses `guru_id`. `both`, `all` and empty mean no filter. | `backend/services/first_person_context_store.py:467-469` |
| Citation label is the registry label only when `speaker_verified is True`. Otherwise the label is "unverified clip". | `backend/services/first_person_pipeline.py:2575-2577`; speaker copy rule `:1681-1735`, `:1837-1848` |
| Registry-derived labels for joint and organisation scopes. | `backend/services/guru_registry.py:89-113` |

Verified gap: `first_person_require_speaker_verified` defaults to `False`. Unverified clips can serve, labelled "unverified clip" [V-STATIC, `backend/app/config.py:266`].

### 2.3 Identifier vocabularies still disagree (GURU-013)

| Vocabulary | Where | Label |
|---|---|---|
| `teacher_id` (chat corpus). Values `ekam`, `preethaji_krishnaji`, `krishnaji`, `preethaji`. | `backend/services/qdrant/searcher.py:163-185`; counts [DOC-CLAIM] root `CLAUDE.md` ("4,337 of 12,904") | [V-STATIC] / [DOC-CLAIM] |
| `teacher_ids` (list) beside `teacher_id`. | `backend/services/qdrant/searcher.py:172-185` | [V-STATIC] |
| `guru_id` (v10 payload). | `backend/services/first_person_context_store.py:72`, `:141`, `:467-469` | [V-STATIC] |
| `preethaji_krishnaji` as a joint id; `ekam` as an organisation id and also a `teacher_id` value. | `backend/config/gurus.yaml:5,16`; `backend/services/intelligent_metadata_extractor.py:69,171,184,237` | [V-STATIC] |
| Assistant slug scopes carry `teacher_id`. | `backend/app/config.py:1194-1199`, `backend/app/assistant_registry.py:20-80` | [V-STATIC] |

### 2.4 Every hardcoded teacher-specific place, with its replacement

Method: `grep -rniE "krishnaji|preethaji"` over `backend/{app,rag,services,guardrails,domain,ingest}` and `src/`, excluding tests and locale files. 591 matching lines at `c9b42d3e` (doc 11 §2 reported 621 at `46b808fb`; T1-03 removed some) [V-STATIC]. The table lists logic-bearing places only. Self-test fixtures and docstrings are omitted.

| # | Place (path:line) | What is hardcoded | Registry-driven replacement | Task |
|---|---|---|---|---|
| H1 | `backend/guardrails/lightweight_handler.py:267-280` (`persona_escape`) | Impersonation patterns name `krishnaji`, `preethaji`, `krishna`, `amma`, `god`, plus Hindi forms. | Generate the English teacher-name alternation from `teachers[].aliases`. Keep God/Divine/Bhagavan and Indic patterns as a static list (native-speaker review applies). | T8-02 |
| H2 | `backend/guardrails/lightweight_handler.py:~370-380` (`_BLOCK_RESPONSES["persona_escape"]` and siblings) | Refusal text names "Sri Preethaji and Sri Krishnaji". | Template from `organizations[].display_names_joined`. | T8-02 |
| H3 | `backend/services/first_person_pipeline.py:1346-1349` (`_ANSWERABILITY_SYSTEM_PROMPT`) | Prompt text names both teachers. | Format the names from the registry at module load. The prompt hash at `:2949-2951` re-keys the exact cache, so the change is safe. | NEW-GURU-4 |
| H4 | `backend/services/first_person_pipeline.py:~1236-1241` (`_llm_rerank_clips` system prompt) | Names both teachers. | Same as H3. | NEW-GURU-4 |
| H5 | `backend/services/first_person_pipeline.py:3895-3896` | Map `"sri krishnaji"` to `"krishnaji"`. | `resolve_guru_id()` already does this (`guru_registry.py:130-166`). Delete the map. | NEW-GURU-4 |
| H6 | `backend/services/first_person_local_review.py:238`, `:1570-1580` | Name list and per-name `if` for "which teacher the question names". | `requested_gurus()` (`guru_registry.py:124-127`). | NEW-GURU-4 |
| H7 | `backend/rag/nodes/cross_teacher_reasoning.py:132-149` | Regexes for sadhguru, preethaji, ekam, krishnaji, amma, bhagavan, iskcon, krishna. Naming only Preethaji or Ekam also adds Krishnaji (line 145). | Use `requested_gurus()`. Organisation alias must not expand to teachers here (see D-PG4). Remove external-teacher branches (D-20). | T8-02, T1-04 |
| H8 | `backend/rag/nodes/keyword_injection.py:30-38`, `:114-122`, `:70`, `:284`, `:326` | Keyword rules name both teachers and Ekam. | Move trigger terms to registry `aliases` plus a doctrine-terms file. | T8-02 |
| H9 | `backend/rag/nodes/entity_linking.py:210-242` (24 matches) | Entity table includes Sadhguru, ISKCON, both teachers, Ekam. Flag `rag_entity_linking_enabled` is `False` (`config.py:1385`). | Generate teacher entities from the registry. Delete external entries. | T8-02, T1-04 |
| H10 | `backend/services/doctrine_terms.py:6,54-56` (38 matches) | ASR correction table keyed by teacher name. | Generate teacher-name rows from `aliases` plus `asr_variants` (new registry field). | T8-02 |
| H11 | `backend/services/teacher_attribution.py:59-75` | `EXTERNAL_TEACHER_SOURCE_REGISTRY` (empty) and mention patterns for sadhguru, amma_bhagavan, iskcon. | Keep mention tagging as a registry list `external_mentions:` (detection only, never identity). | T8-01 |
| H12 | `backend/services/intelligent_metadata_extractor.py:69,171,184,237` | Prompt and code enumerate `krishnaji`, `preethaji`, `preethaji_krishnaji`, `ekam`, `amma_bhagavan`. | Validate extractor output against `teachers[].id` and the attribution mode enum. | T3-07 |
| H13 | `backend/app/db/seed_ontology.py:107,119,574,584,641` | Seeds Sadhguru and ISKCON concepts and teacher nodes. | Delete other-teacher seeds (D-20). Seed teacher nodes from the registry. | T1-04 |
| H14 | `backend/app/config.py:1194` (`allowed_assistant_slugs`), `:1198-1199` (`assistant_corpus_registry`) | Slugs `guru,preethaji,krishnaji,serene_mind` with `teacher_id` values. | Derive slugs and teacher scope from the registry. | T1-04, T8-01 |
| H15 | `backend/services/prompt_store.py:45` (`"sadhguru"` personality), `:374-376` | A persona that speaks "with the tone of a yogi" for a teacher with no corpus. `app/config.py:789` repeats it as an example. | Remove (D-20). Teacher personas are not configurable (11 §6 rule 4). | T1-04 |
| H16 | `supabase/migrations/20260703170000_gurus_and_configurations.sql:54-55,66,71` | Rows for `sadhguru`, `iskcon` with collection names. | New migration deletes the rows after a usage check. The owner applies it. | T1-04, T3-07 |
| H17 | `backend/rag/retrieval/rights_gate.py:36-45`, used at `:79` | `LICENSED_SOURCES` set in code: "ekam", "o&o academy", "times now", "tedx", "marietv", "marie forleo", and others. Rights live in code, not in a rights record (IP-005). | Move to `sources[].allowed_uses` in the registry with a `rights_grant_ref`. | T3-06, NEW-GURU-3 |
| H18 | `backend/services/voice/register.py:72` (loader), `:951-967` (self-test), plus 12 matches | Reads registry labels (good). Self-test fixtures name teachers. | Keep. Fixtures are exempt from the literal guard. | none |
| H19 | `backend/ingest/verbatim/speaker_verify.py:119` | `_TEACHER_WINDOW_LABELS = {"preethaji": "P", "krishnaji": "K"}`. | Derive from `teachers[].window_label` (new field) or registry order. | NEW-GURU-4 |
| H20 | `backend/app/api/kg.py:379` | Loop over `("preethaji","krishnaji","ekam","buddha","osho")`. | Registry ids only. Remove `buddha`, `osho` (no corpus). | T1-04 |
| H21 | `backend/app/orchestrator_utils.py:440-445` | Keyword expansion for `"ekam"`. | Organisation `aliases` plus `keywords:` registry field. | T8-02 |
| H22 | `backend/services/guru_brain/persona_discriminator.py:41-46` | Forbidden-phrase list names both teachers. | See 2.5: module is a persona judge, not an attribution check. Template names from the registry or retire it. | T7-06 (dormant) |
| H23 | `src/components/meditation/meditationSteps.ts:2,4,14` | Script header names Sri Preethaji as source and voice. | Static content with a rights record. Out of registry scope. Tag in `sources[]`. | NEW-GURU-3 |
| H24 | `src/components/kg/KGConceptMap.tsx:136,260` | `KNOWN_TEACHERS` set and `'sri krishnaji'` entry. | Generated constant `src/generated/teachers.ts` from the registry. | T8-02 |
| H25 | `src/components/landing/SampleWisdomSection.tsx:20,29` | Teacher names in sample cards. | Sample cards must carry a span locator (GURU-012) or be unattributed. Names from the generated constant. | T8-02 |
| H26 | `src/components/chat/DeepenAndTuneBar.tsx:~62-102` (flag off: `src/lib/featureFlags.ts:17`) | Hand-written per-teacher concepts. | Delete (GURU-012). | T1-03 remainder |
| H27 | `src/admin/pages/TeachingTipsPage.tsx`, `src/admin/lib/seed.ts` (7 matches each) and `backend/app/api/teachings.py` `DEFAULT_TEACHER` | Default teacher name on admin-curated tips (register: GURU-012 Partial). | Require a span id or render the tip with no teacher credit. | T1-03 remainder |
| H28 | `src/` total | 42 non-locale files contain a teacher name [V-STATIC, `grep -rli`]. | Generated constant plus the literal guard (3.8). | T8-02 |

The CI literal guard in 3.8 does not exist at this head. `scripts/guards/lesson_guards.py` contains no teacher-name check [V-STATIC, grep].

### 2.5 CLAUDE.md names the wrong module for attribution

Root `CLAUDE.md` says speaker attribution is "grounded by `persona_discriminator.py`". The module is a Reflexion persona-quality judge. It scores intimacy, OKF grounding and cliche use (`backend/services/guru_brain/persona_discriminator.py:1-9`). Its only importer is `rag/nodes/guru_tone_adapter.py:23-28`, which is not in the default stage chain; `ToneAdapterStage` is a no-op (`app/pipeline/stages/pipeline_builder.py:88`). Speaker attribution is in fact enforced by the integrity gate and `speaker_verified` copy (section 2.2). Fix the CLAUDE.md sentence in NEW-GURU-1 [V-STATIC].

### 2.6 Other registries still present (R2 to R7 of doc 11)

R2 Supabase `gurus` table (H16). R4 `allowed_assistant_slugs` and R5 `assistant_corpus_registry` (H14). R6 teacher personalities (H15). R7 external-teacher detection (H11). R3 (`assistants` table with `sky`) is unchanged; T1-04 is Open and needs D-20 [V-STATIC, `FINAL_PENDING_WORK_REGISTER.md` GURU-011].

### 2.7 Conflicting perspectives today

| Fact | Evidence |
|---|---|
| In the first-person lane, when no single teacher is named, the pipeline balances the candidate list between teachers. Each clip keeps its own speaker label. | `backend/services/first_person_pipeline.py:5131` (`_rerank_and_balance_candidates`), `:5245` (Step 4d) |
| A graph node detects multi-teacher questions and builds graph context for generation. It runs on the general graph only. | `backend/rag/nodes/cross_teacher_reasoning.py:120-160` |
| Nothing detects that two clips disagree. Nothing labels a pair as "two perspectives". | grep of `backend/` for conflict or contradiction in the FP lane returns no serving use. `rag/nodes/contradiction_resolver.py` exists in the general graph [INF: not on the FP lane] |

### 2.8 Knowledge graph: real status

| Question | Answer | Evidence |
|---|---|---|
| Does the first-person lane use Memgraph or LightRAG? | Only through two flags, both default `False`: `first_person_graph_expansion_enabled`, `first_person_teaching_unit_graph_enabled`. When on, the code reads `container.neo4j_driver` and adds neighbour concept terms. It never writes text. | `backend/app/config.py:364,374`; `backend/services/first_person_graph_expansion.py:110-122,175-188`; `backend/services/first_person_pipeline.py:68,2168` |
| Does the general graph use them? | Yes, by default. `retrieve_documents` injects a Neo4j subgraph for relational and deep lanes or multi-concept queries (`rag_graph_context_injection_enabled=True`, `knowledge_graph_query_enabled=True`) and LightRAG context (`rag_lightrag_context_injection_enabled=True`). The hot path passes `lightrag=None` to `retrieve_for_single_query`. | `backend/app/config.py:1383,1404,1742`; `backend/rag/nodes/retrieval.py:2312-2330,2371-2420,1793,1939` |
| Does a teaching question reach that code on the default configuration? | No [INF]. With `first_person_llm_fallback_enabled=False` and `fp_fail_closed_enabled=True`, `generate_answer` returns the static abstain for a teaching-lane turn. General-knowledge mode returns early from `retrieve_documents` with web results only. DISTRESS no longer reaches retrieval (T4-05). Personalise turns: not traced. | `backend/app/config.py:430,435`; `backend/services/fp_fail_closed.py:24-31`; `backend/rag/nodes/generation.py:2668-2690`; `backend/rag/nodes/retrieval.py:1555-1580`; AI-002 Closed in register |
| Is the graph deployed? | Yes. `memgraph/memgraph-mage:latest` (unpinned tag) is a default compose service and a Railway deploy service. | `backend/docker-compose.yml:44-45`; `scripts/deploy/deploy_railway.sh:122-131` |
| Does ingestion write to it? | Yes by default: `write_ontology_to_neo4j=True`, `ontology_write_required=False`. | `backend/app/config.py:1559-1562` |
| Is the agentic traversal live? | No: `agentic_graph_traversal_enabled=False`. | `backend/app/config.py:2104` |
| Does graph text carry span provenance? | No [DOC-CLAIM `08` RET-05; 41.4% LightRAG contamination]. | `08` |

Conclusion (code-supported): the graph is off the teaching-answer path by default and on the general-lane path by default. It costs a deployed service and ingestion writes. ADR-005 (Proposed) says freeze writes and remove from the deploy stack. The evidence here supports ADR-005. The decision is D-05 and is not made. Section 3.9 gives the compliant variant (freeze, no removal) and the decision-gated variant (remove).

---

## 3. Target contracts

### 3.1 Teacher identity model

| Field | Rule |
|---|---|
| `id` | Lowercase `[a-z][a-z0-9_]{1,31}`. Immutable. Never reused after retirement. Never contains another id (`preethaji_krishnaji` is not a teacher id). |
| `display_label` | The only string shown as a speaker name after `speaker_verified is True`. |
| `aliases` | List of case-insensitive regexes for recognising a request. Each must compile and must not match the empty string. Tested against a negative list (for example `krishna` must not match `krishnaji`). |
| `asr_variants` | Optional list of mis-transcriptions for doctrine correction (H10). |
| `window_label` | One uppercase letter for speaker windows (H19). Unique. |
| `voice_profile_ref` | `ecapa/<id>/<sha256>`. Owned by the data team (doc 07). `null` allowed only while `status: onboarding`. |
| `status` | `onboarding`, `active`, `retired`. Only `active` may serve. `retired` keeps its clips non-servable and its id reserved. |
| `attribution_tag` | `teacher:<slug>`. |
| `external_mentions` | Optional detection-only list (H11). Never confers identity. |

### 3.2 Registry v2 file

File: `backend/config/gurus.yaml`, header `schema: teacher-registry-v2`. Add `registry_version` (integer, bump per change). Keep the v1 keys (`gurus`, `organizations`, `shared_*`) until migration ends so existing importers keep working.

```yaml
schema: teacher-registry-v2
registry_version: 2
gurus:                       # v1 key kept; extended
  - id: krishnaji
    label: Sri Krishnaji
    attribution_tag: teacher:sri_krishnaji
    aliases: ['(?:sri\s+)?krishnaji']
    window_label: K
    status: active
    voice_profile_ref: null  # data team supplies; see 3.7 step 4
organizations:
  - id: ekam
    label: Ekam / O&O Academy
    aliases: ['\bekam\b']
    attributed_teacher_ids: [preethaji, krishnaji]
    is_teacher: false        # NEW. Organisation ids never serve as a speaker.
sources:                     # NEW; one row per channel, publication or media set
  - id: yt:ekam-official
    kind: youtube_channel
    organization_id: ekam
    teacher_ids: [preethaji, krishnaji]
    rights_grant_ref: null   # private-store hash; null means non-servable
    allowed_uses: []         # subset of the vocabulary in 3.3
attribution_policy:          # NEW; see 3.4
  joint_attribution_allowed_for: []
  unknown_speaker_label: "unverified clip"
corpora:                     # NEW
  - id: fp-context-v10
    collection: first_person_v10
    teacher_ids: [preethaji, krishnaji]
    status: serving          # serving | candidate | retired
```

Rules: `sources[].allowed_uses` empty or `rights_grant_ref` null means the source is non-servable (fail closed). The registry holds no rights text and no personal data. The `rights_grant_ref` is a hash into the private evidence store (ADR-008, D-08).

### 3.3 Rights and permissions per teacher and source

Allowed-use vocabulary (proposal, decision-gated by D-PG2): `serve_clip`, `show_transcript`, `play_audio`, `show_translation_gloss`, `use_in_eval`, `use_in_embedding`. A teacher's `status: active` does not grant any use. Each source grants uses. Serving checks the source of the span's `source_id` against `allowed_uses` before the span enters any response.

Compliant variant buildable now: add the fields, load them, and enforce `serve_clip` only for sources that declare `rights_grant_ref`, with the current 2-teacher corpus mapped through one source row per existing channel and `rights_grant_ref: null` plus a registry-level flag `legacy_rights_assumed: true` that keeps today's behaviour and emits a warning metric. Decision-gated variant: remove `legacy_rights_assumed` so null grants block serving. That step depends on the owner filing grants (D-10, D-13).

### 3.4 Attribution model and joint attribution

Payload field set (replaces `teacher_id`/`teacher_ids`/`guru_id`, closes GURU-013):

| Field | Values |
|---|---|
| `guru_id` | One registry teacher id, or `null`. |
| `attribution_mode` | `single` (one verified speaker), `joint` (jointly authored published work), `unknown`. |
| `source_id` | A registry `sources[].id`. |
| `organization_id` | Optional registry organisation id. Never used as a speaker. |

Rules: a spoken clip is `single` and carries the verified speaker's `guru_id`. `joint` is allowed only for a source kind listed in `attribution_policy.joint_attribution_allowed_for`. The list ships empty. `unknown` renders "unverified clip". Existing legacy values map as: `preethaji`/`krishnaji` to `single`; `preethaji_krishnaji` to `joint` only if D-PG1 allows, else `unknown`; `ekam` to `organization_id`, with `guru_id` null.

Compliant variant now: empty allow list (no joint credit). Decision-gated: the guru review (GURU-014, D-PG1) fills the list.

### 3.5 Versioning

| Item | Rule |
|---|---|
| Registry | `registry_version` integer plus `sha256` of the canonical file. Add both to `ReleaseManifest` (`app/release_manifest.py:36-45`). The public projection stays three fields (`:70-76`); do not add them there. |
| Teacher ids | Never renamed. A rename is a new id plus an alias map in the migration. |
| Corpora | A new corpus version is a new collection (root `CLAUDE.md` invariant 4). `corpora[].status` records which serves. |
| Citations | A stored span keeps `source_id` and `corpus_version`. A retired source does not delete old audit rows. |
| Exact cache | The serving-policy fingerprint already hashes the answerability and relevance prompts (`first_person_pipeline.py:2949-2970`). Add `registry_sha256` to the fingerprint so a registry change cannot replay an old answer. |

### 3.6 Topics, concepts and OKF

OKF entries are routing and reflection aids only. Rules enforced by code and kept: doctrine types only, mandatory `source`, `_excluded_parts={"staging","_scripts"}` is the review gate (`backend/services/memory/okf_store.py:206-208`). The registry adds `concept_scope` per corpus: a list of OKF `type` values allowed to route. OKF entries never carry `guru_id` as speaker. A concept tag on a span comes from the concept vocabulary table (T5-02) and never from an LLM at serve time. [HUMAN: guru review of the vocabulary.]

### 3.7 Cross-teacher retrieval and filters

```
TeacherScope = { mode: "any" | "single" | "multi", guru_ids: list[str] }
```

| Input | Result |
|---|---|
| No teacher named | `any`. Search all active teachers. Label each clip by its own speaker. |
| Exactly one named | `single`. Filter at the store. Never substitute another teacher's clip (existing rule, `first_person_pipeline.py:158-174`). |
| Two or more named, or "both" | `multi`. Return clips per named teacher. |
| Unregistered id | Resolver returns `None`. Caller abstains. It never means "no filter" (`guru_registry.py:131-134`). |
| `status != active` | Excluded from `any`. A named retired teacher gets the static abstain. |

### 3.8 Generated outputs and the literal guard

Create `backend/services/guru_registry_exports.py` (pure functions, no I/O beyond the registry):

| Function | Output | Consumers |
|---|---|---|
| `impersonation_alternation()` | Regex group of all `aliases`, used inside the H1 patterns | `lightweight_handler.py` |
| `joined_display_names()` | "Sri Preethaji and Sri Krishnaji" | H2, H3, H4 |
| `doctrine_alias_rows()` | ASR rows | `doctrine_terms.py` |
| `write_frontend_constant(path)` | `src/generated/teachers.ts` (id, label, tag) | H24, H25, other `src/` consumers |

Literal guard: add a check to `scripts/guards/lesson_guards.py` that fails when `krishnaji` or `preethaji` (case-insensitive) appears in `backend/{app,rag,services,guardrails,domain,ingest}` or non-locale `src/` files, except: `backend/config/gurus.yaml`, files under `tests/`, `__tests__`, `*.test.*`, `src/locales/`, `src/generated/`, a committed allowlist file `scripts/guards/teacher_literal_allowlist.txt` listing each remaining file with a reason and a count ceiling (ratchet). The guard starts in ratchet mode (current counts as ceilings) and the ceiling only goes down.

### 3.9 Graph decision variants

(a) Compliant, buildable now, no decision needed: freeze. Set `write_ontology_to_neo4j=False` as the documented default for new ingestion; pin the compose image tag; add a flag-state line in the release manifest; keep data snapshot. Keep general-lane injection as is. This does not delete code.
(b) Decision-gated by D-05: remove Memgraph from deploy stack and the general-lane injection, per ADR-005 and T3-11. Needs T0-05.
Re-entry rule: a graph returns only after an ablation on the held-out set shows lift (`19` §6 N-05).

### 3.10 Conflicting perspectives

Contract (compliant variant, buildable now):

```
PerspectiveSet = { topic_label: str|null, positions: [ { guru_id, span_id, label } ], note: "Two teachers, two clips. Not reconciled." }
```

Rules: each position is one stored span with its own verified speaker. The assistant adds no sentence that merges, ranks or reconciles the positions. A static, non-generated note may state that the clips come from different teachers. Detection is deterministic: both teachers named, or `TeacherScope.mode == multi`, and each has a clip passing the existing gates. If one teacher has no passing clip, the response says so with the static abstain text for that teacher; it never fills the gap with the other teacher's clip.

Decision-gated variant (D-03, ADR-001): a labelled assistant comparison (layer L3) explaining the difference. It needs the verifier of T5-04 and the voice lint of T2-01. Not buildable now.

---

## 4. Behaviour per component, with failure handling

| Component | Behaviour | Failure handling |
|---|---|---|
| Registry loader | Parse, validate against `backend/config/gurus.schema.json` (new), compile every alias, check id rules, check cross-references (corpus teacher ids exist, source teacher ids exist). | Today: log and return `{}` (`guru_registry.py:31-36`). Target: in production, an invalid file stops startup. In other environments, load `{}` and log, as today. An empty registry still quarantines all clips (fail closed). |
| Speaker gate | Unchanged. Allowlist from `status: active` labels. | Unlisted speaker is quarantined and counted (`first_person_quarantined_total`, `app/metrics.py:788`). |
| Source gate | Before serving a span, check `sources[source_id].allowed_uses` contains `serve_clip`. | Missing source row, null grant or missing use: non-servable. Count with `reason=source_not_permitted`. |
| Impersonation guardrail | Patterns built from registry. | Build error: use the previous static patterns and log. Never ship an empty pattern list. |
| Frontend constant | Generated at build. | Missing file fails the frontend build. |
| Ingestion attribution | `resolve_teacher_attribution` reads registry. Output validated against ids. | Unknown id from the extractor (H12) becomes `unknown`, never a new teacher. |
| Conflict display | 3.10. | One side empty: static abstain for that teacher. |
| Takedown | `sources[].allowed_uses: []` plus cache flush by registry sha. | Depends on T3-06 `takedown()`. |

## 5. Deterministic steps versus LLM steps

| Step | Kind | Owner |
|---|---|---|
| Identity, alias match, allowlist, source gate, attribution mode, scope resolution, conflict detection, guard | Deterministic code only | Registry module |
| Offline alias or ASR-variant suggestions for a new teacher | LLM allowed offline, output is a proposal file reviewed by a human before it enters the registry | Data team. No serve-time use. |
| Voice profile | Model-based (speaker embedding), offline, human spot check (doc 07) | Data team |
| Serve-time LLM prompts that name teachers (H3, H4) | Formatted from the registry. No identity decision. | Harness spec `AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` |

No LLM decides who a speaker is. No LLM writes in a teacher's voice.

## 6. Observability

Reuse (verified by grep in `backend/app/metrics.py`): `first_person_quarantined_total` (`:788`), `first_person_requests_total{status,reason}` (`:756`), `guardrails_blocked_total{rail}` (`:205`), `guru_fp_fail_closed_total{reason}` (`:56`).

Proposed new (NEW; not in code): `guru_registry_load_total{outcome}` (ok, invalid, missing), `guru_registry_info{registry_version}` gauge, `first_person_source_blocked_total{reason}`, `guru_perspective_set_total{outcome}` (two_sided, one_sided). Labels are bounded closed sets. No query text, no user id.

Log line at startup: `registry_version`, `registry_sha256`, active teacher ids, serving corpora. No file contents.

## 7. Acceptance criteria

| # | Criterion | Test (file::case) | Pass / fail | Needs |
|---|---|---|---|---|
| 1 | Schema rejects: duplicate id, bad regex, empty-matching alias, unknown teacher in a corpus row, joint id used as teacher id. | `backend/tests/test_guru_registry_schema.py` (new) one case per rule | Each invalid fixture raises `RegistryValidationError`; valid fixture loads | none |
| 2 | Production startup fails on an invalid registry. | `backend/tests/test_guru_registry_schema.py::test_production_startup_fails_on_invalid` (new) | Process init raises | none |
| 3 | A fixture teacher is refused by the impersonation guardrail with no code edit. | `backend/tests/test_guardrail_registry_patterns.py::test_fixture_teacher_impersonation_blocked` (new) | "speak as <fixture>" blocked; baseline phrases still blocked | none |
| 4 | Prompts H3 and H4 contain registry labels, not literals. | `backend/tests/test_prompts_use_registry_labels.py` | Prompt text equals template output for the fixture registry | none |
| 5 | Literal guard fails on a new literal and passes on current counts. | `backend/tests/test_teacher_literal_guard.py` | New literal in a temp runtime file fails; ratchet file passes | none |
| 6 | Existing resolver behaviour holds. | `backend/tests/test_guru_registry_and_modes.py` (existing, all cases) | All pass | none |
| 7 | Source without grant is non-servable once the legacy flag is off. | `backend/tests/test_source_gate.py::test_null_grant_blocks_serving` (new) | Span not in response; counter increments | none |
| 8 | A retired teacher never serves and a named retired teacher gets the static abstain. | `backend/tests/test_teacher_scope.py::test_retired_teacher_abstains` (new) | Abstain text, no other teacher's clip | none |
| 9 | Conflict set: two teachers named gives two labelled clips, no merged sentence. | `backend/tests/test_perspective_set.py::test_two_sided_no_merge` (new) | Each position's speaker equals its stored speaker; answer body has no generated text | none |
| 10 | One side empty gives an abstain for that teacher, not a substitute. | `backend/tests/test_perspective_set.py::test_one_sided_abstains` (new) | No cross-teacher clip | none |
| 11 | `speaker_verified` is copied, not inferred, after the registry change. | existing `backend/tests/test_first_person_bridge.py` and `test_citation_contract.py` | Unchanged | none |
| 12 | Qdrant payloads use registry ids only. | Facet count over `guru_id` | Only registry ids | [LIVE-Q] |
| 13 | Rights grants exist for every serving source. | Registry check against private store hashes | No null grant on a serving source | [HUMAN] D-10 |
| 14 | Guru review approves the joint-attribution list and the conflict note wording. | Written approval filed by hash | Present | [HUMAN] D-PG1 |
| 15 | A new-teacher dry run passes every onboarding step (3.11) with a synthetic teacher on fixture data. | `backend/tests/test_onboarding_dry_run.py` | Steps 2, 5, 8 need no code edit | none |
| 16 | Stack starts with graph writes off. | `backend/tests/test_config_validation.py::test_graph_write_off_boots` (new) | App boots; no graph call at ingestion | none |

### 3.11 Onboarding a new teacher (checklist with a test per step)

| Step | Action | Files touched | Acceptance test | Gate |
|---|---|---|---|---|
| 1 | Record a written rights grant from the teacher's organisation (content, uses, term, correction contact). File it in the private store. | none in repo | Hash of the grant is non-empty in the draft registry row | [HUMAN] |
| 2 | Add the teacher with `status: onboarding` and `voice_profile_ref: null`. Add a `sources[]` row. | `backend/config/gurus.yaml` | Criterion 1 passes; teacher is absent from `allowed_speaker_labels()` (test asserts) | CI |
| 3 | Obtain media from the rights holder. Do not scrape. Record `permission_ref` per archived file. | private store | Archive check lists `permission_ref` for every file (doc 14c IP-004) | [HUMAN] |
| 4 | Build a voice profile from clean reference audio supplied by the organisation. Set `voice_profile_ref`. | registry, data team tools | Spot check of 50 spans by a human; script reports match rate | [HUMAN] |
| 5 | Ingest into a new collection. Run integrity, content-quality, speaker gates. Update `corpora[]` with `status: candidate`. | `backend/config/gurus.yaml` | `scripts/ops/data_quality_audit.py` passes; no code edit (criterion 15) | CI + [LIVE-Q] |
| 6 | Extend the eval sets with this teacher: routing, abstain, quote integrity, attribution. | `evals/pr_suite/*` | PR eval suite passes; offline suite includes the teacher's cases | CI |
| 7 | Guru review of 30 to 50 answers by the teacher's team. | review package (doc 23) | Written approval filed by hash | [HUMAN] |
| 8 | Set `status: active` and `corpora[].status: serving`. | `backend/config/gurus.yaml` | Criterion 8 inverse: teacher serves; criterion 3: guardrail covers the alias | CI |
| 9 | Monitor correction reports for 30 days. | metrics | `first_person_quarantined_total` and report counts reviewed; response time agreed (doc 23 D6) | [HUMAN] |

---

## 8. Ordered implementation tasks (PR-sized)

| Order | Task | Maps to | Depends on | Non-goals | Rollback |
|---|---|---|---|---|---|
| 1 | NEW-GURU-1: fix the CLAUDE.md `persona_discriminator.py` sentence; document the registry as the attribution source | T1-01 follow-up | none | no code | revert the doc edit |
| 2 | NEW-GURU-2: registry v2 loader, JSON schema, `RegistryValidationError`, startup check in production, `registry_sha256` in `ReleaseManifest` and cache fingerprint | T8-01 | none | no payload migration | keep v1 keys; flag `GURU_REGISTRY_STRICT=false` |
| 3 | NEW-GURU-3: add `sources[]`, `corpora[]`, `attribution_policy`, source gate with `legacy_rights_assumed: true` | T8-01, T3-06 | 2 | do not remove legacy assumption | set gate flag off |
| 4 | T8-02a (= NEW-GURU-4): export module; replace H3 to H6, H19; add prompt-label tests | T8-02 | 2 | no guardrail change yet | revert to literals |
| 5 | T8-02b: generate H1, H2, H8, H10, H21 from the registry; frontend generated constant (H24, H25) | T8-02 | 4 | Indic patterns stay static | revert to literals |
| 6 | NEW-GURU-5: literal guard in ratchet mode | T8-02 | 5 | no hard fail on legacy files | disable guard step |
| 7 | T1-04: remove other-teacher seeds and personas (H7 external branches, H9, H13, H14, H15, H16, H20) | T1-04 | D-20 | no registry change | revert PR |
| 8 | T3-07: canonical payload fields (3.4); dry-run, snapshot, apply per T3-04 | T3-07 | 2, 3; owner applies | no live write by an agent | restore snapshot |
| 9 | NEW-GURU-6: `PerspectiveSet` for multi-teacher scope (compliant variant) | NEW | 2, 4 | no generated comparison | flag `PERSPECTIVE_SET_ENABLED=false` |
| 10 | NEW-GURU-7: graph freeze (3.9a): write flag off, pin compose tag, manifest line | T3-11 part | none | no removal | revert flags |
| 11 | T3-11 full removal | T3-11 | D-05 | none | restore from snapshot |
| 12 | GURU-012 remainder: locator check for admin-curated tips (H27) | T1-03 remainder | none | none | revert |
| 13 | NEW-GURU-8: onboarding dry-run test with a synthetic teacher | NEW | 2 to 5 | none | delete test |

## 9. Open questions

| ID | Question | Why it blocks |
|---|---|---|
| D-05 | ADR-005: remove the graph from serving and deploy? | Task 11 |
| D-20 | Were other-teacher seeds intended? | Task 7 |
| D-12, D-13 | Voice rights; broadcaster clearance. | Task 3 gate tightening |
| D-10 | Where do grants live; filed by hash? | Criterion 13 |
| PROPOSED D-PG1 | Joint attribution: which source kinds may carry both names? Guru review. | 3.4, GURU-014 |
| PROPOSED D-PG2 | Allowed-use vocabulary in 3.3. Which uses does each grant cover? | 3.3 |
| PROPOSED D-PG3 | Does production start with an invalid registry? Proposed answer: no. | 4 |
| PROPOSED D-PG4 | May an organisation alias (for example "Ekam") expand to both teachers in retrieval, or only in labels? Proposed: labels only. | H7, `cross_teacher_reasoning.py:143-145` |
| PROPOSED D-PG5 | Is `first_person_require_speaker_verified` meant to be `True` for the faculty review? | `config.py:266` |
| PROPOSED D-PG6 | Who may approve a new teacher (`status: active`)? | 3.11 step 8 |
| PROPOSED D-PG7 | Is the Supabase `gurus` table read by any live code? Needs a usage check before removal. | H16 |
| PROPOSED D-PG8 | Keep a concept vocabulary table or the graph for facet tagging? Proposed: vocabulary table (T5-02). | 3.6, 3.9 |

## 10. Verified, assumptions, unknowns

**Verified (read at `c9b42d3e`).** Registry v1 content and API; fail-closed empty allowlist; importers; integrity gate speaker check; single-teacher request scoping; searcher and context-store filters; speaker label copy rule; the 28 hardcoded places in 2.4; `persona_discriminator.py` role; graph flags, defaults and call sites; compose and Railway graph deployment; `write_ontology_to_neo4j` default; fail-closed generation guard; existing registry fixture test.

**Assumptions.** [INF] A teaching turn does not reach graph injection under default flags (traced through four files, not run). [INF] `contradiction_resolver.py` is not on the FP lane. The 591-line count is a grep count, not a runtime measure.

**Unknowns.** Live Qdrant `teacher_id`/`guru_id` distribution [LIVE-Q]. Whether any live code reads the Supabase `gurus` table [LIVE-R]. The owner's local `.env` flag values [LIVE-L]. Whether personalise turns reach graph injection. Whether the 2 existing teachers' grants exist outside the repo [HUMAN, D-10]. Whether the guru review accepts the conflict note wording [HUMAN].
