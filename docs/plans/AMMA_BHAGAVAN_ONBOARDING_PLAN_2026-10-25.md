# Onboarding a third teacher (Sri Amma Bhagavan): plan, not started

Date: 2026-10-25. Status: plan only. No code, config, Qdrant or data was changed.
Source: a read-only static code audit (no tests run, no live Qdrant payloads inspected, no network). Frontend paths (such as `src/lib/firstPersonService.ts` and `src/components/...`) are relative to the repository root. Paths under `docs/` are also relative to the repository root (`docs/DEVELOPER_GUIDE.md` means the file at that path, not `docs/docs/...`). Other paths are relative to `backend/` unless noted. Line numbers are as of branch `claude/project-thread-q8n49x` and can drift.

## Why this is mostly a decision, then a checklist

The code already has a teacher registry. Most of the serve path reads it. A handful of places still assume exactly two teachers. None of the work below is started until the owner answers the two questions in the next section and the rights step is done.

## Two decisions for Harsha (blocking)

1. **Is Amma Bhagavan a third speaker in this corpus, or the same lineage?**
   `domain/spiritual_ontology.py:315-331` says she is the same lineage and one tenant, "not a third-party teacher". `services/teacher_attribution.py:26, 59, 69-70` treat `amma_bhagavan` as an external teacher who is mention-only unless registered. The onboarding model has to pick one. Recommended default: **third speaker with her own voice and own clips**, because voice verification and "who is speaking" attribution are per person; a shared-lineage tag would hide her clips behind the founders' labels.
2. **Which id and spelling?** The registry test uses a fake "Sri Amma Bhagwan" (`tests/test_guru_registry_and_modes.py:166`); the code elsewhere says `amma_bhagavan` and `amma`. Pick one id (recommended: `amma_bhagavan`) and one display spelling, then use it everywhere. Note `teacher_attribution.py:11-13` records a past bug where the substring "amma" inside "grammar" mis-tagged 3,121 points, so matching must be on whole words.

## Prerequisites that are not code (do these first)

- **Rights.** Written permission naming the content and the use (excerpts plus audio playback). Today's rights register is hardcoded to the founders, TEDx and MarieTV (`scripts/ops/build_fp_rights_register.py:106-150`; gate `config/first_person_public_release_gate.json:53, 62`).
- **Source list.** Which videos, who is on the recording (host, guest, Amma), and whether any are already in the archive.
- **Voice reference audio** for her, and a clean enrollment, before any clip is allowed to carry `speaker_verified`.

## Already generic (no change needed)

- `config/gurus.yaml` plus `services/guru_registry.py` (`get_gurus`, `allowed_speaker_labels`, `resolve_guru_id`, `shared_attribution` is n-ary). Adding a guru row is the intended path.
- First-person serve path: allowlist and requested teacher come from the registry (`services/first_person_pipeline.py:108-131, 356`; `services/first_person_store.py:61, 203`). `teacher_id` is a keyword index and the filter lowercases it (`first_person_store.py:289, 626-628`).
- `domain/first_person_context.py:36-40, 164`: speaker roles carry no per-teacher value; `guru_id` is a free string.
- `GURU_SYSTEM_PROMPT` is name-free (`rag/prompts/system.py:100`); voice labels come from the registry (`services/voice/register.py:71-84`).

## Hardcoded two-teacher assumptions, by blast radius

| # | Where | What it assumes |
|---|---|---|
| 1 | `app/api/first_person.py:434` | `teacher_id` is `Literal["preethaji","krishnaji","both"]`; a third id is rejected at ingest. |
| 2 | `src/lib/firstPersonService.ts:82` | Same union in TypeScript. |
| 3 | `ingest/verbatim/speaker_verify.py:75-76, 119, 177, 187, 403-404, 433` | Closed two-speaker label space (`P`, `K`). The error bound recorded for speaker checks (0/262, about 1.14% upper bound) is for a closed two-guru set; a third speaker changes it and needs its own measurement. |
| 4 | `services/teacher_attribution.py:26, 59, 60, 69-70` | `amma_bhagavan` is an external id; the external registry is empty. |
| 5 | `scripts/ops/backfill_qdrant_teacher_id.py:78-100` | Regex returns only `preethaji`, `krishnaji`, `preethaji_krishnaji`. This script writes the Qdrant `teacher_id`. |
| 6 | `rag/nodes/cross_teacher_reasoning.py:133-149` | One hand-coded boolean per teacher. |
| 7 | `rag/nodes/entity_linking.py:40-41, 53-71, 314` | Fixed two-name licensed alias set. |
| 8 | `rag/nodes/keyword_injection.py`, `rag/nodes/intent.py:645-646, 1361-1362`, `rag/query_patterns.py:48-49, 148-149` | Teacher-name patterns. |
| 9 | `services/lightrag_service.py:39-71` | Hand-written `TEACHER_CANONICAL_MAP`. |
| 10 | `app/config.py:1054, 1058-1059`; `app/assistant_registry.py:31, 38` | `allowed_assistant_slugs` and the corpus map live outside `gurus.yaml`. |
| 11 | `services/guru_voice_langhanam.py:58-67`; `services/guru_brain/persona_discriminator.py:41-46, 62, 69-70, 95, 178` | Prompt block and "once said" bans name both founders. |
| 12 | `rag/prompts/guardrails.py:56, 61, 111`; `guardrails/lightweight_handler.py:267-276` | Few-shot examples and impersonation regexes name both (the handler already lists amma at 272-273). |
| 13 | `domain/spiritual_ontology.py:208-212, 315-331, 341`; `scripts/ops/canonicalize_teacher_aliases.py:6-13, 57-71` | Display names and alias table. |
| 14 | `supabase/migrations/20260703170000_gurus_and_configurations.sql:20, 53, 60-76` | Seeded guru rows and doctrine seed keyed to `preethaji_krishnaji`. |
| 15 | Copy: `app/gradio_ui.py:36`, `app/main.py:996`; frontend: 35 files mention Preethaji, 32 mention Krishnaji; `src/locales/en.json` has 57 matching lines; `src/components/chat/ChatMessage.tsx:645`; `src/admin/pages/SpeakerAttributionPage.tsx:333, 431` (per-teacher colours). Other locales were not counted. |

`tests/test_guru_registry_and_modes.py` covers config-driven loading, new-teacher resolution without code change, single-guru scoping and the system-prompt registry rule. It does **not** cover `speaker_verify`, the API `Literal`, `assistant_registry`, the frontend, the rights register or `lightrag`.

## Proposed order (when the decisions and rights are in)

> **Authority note**: `docs/DEVELOPER_GUIDE.md` is the authoritative document for repository onboarding and developer instructions; contributors can find this plan referenced there. When work on onboarding a third teacher begins, follow this sequence:

1. Add her row to `config/gurus.yaml` and a registry test with the chosen id and spelling (fix the "Bhagwan" mismatch in the existing test).
2. Replace the API `Literal` and the TypeScript union with values read from the registry (items 1, 2).
3. Generalise `speaker_verify` from a fixed `P`/`K` pair to the registry's speaker labels; re-measure the error bound with her enrollment before any `speaker_verified=true`.
4. Move alias and canonical maps (items 4, 7, 9, 13) to registry data; whole-word matching only.
5. Update the rights register builder, the public-release gate and the owner decision packets with her entry, and keep her clips out of the serving collection until the rights message exists.
6. Build her clips offline into a **new** first-person collection version (never edit the serving one), run the integrity gate, and compare before and after on the gold questions.
7. Frontend copy and colours last.

## Not decided here

Whether she gets her own chat mode or only appears when a question names her; the voice-register wording for her; and whether the `both` value becomes "any of the registered teachers". These need the owner.
