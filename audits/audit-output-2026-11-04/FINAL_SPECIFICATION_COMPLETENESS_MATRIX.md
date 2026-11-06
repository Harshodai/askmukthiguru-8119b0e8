# Final specification completeness matrix (2026-11-05)

Head `c9b42d3e`. This file rates each of the 11 requested specifications, plus the historical ADR record, for one question: can an independent coding agent implement it without re-investigating? Ratings come from each spec's own header and from the lead's reading of its sections 3, 7 and 8. Evidence labels: `CONVENTIONS.md` §3.

## 1. Rating scale

- **Implementation-ready**: contracts, files, tests with pass conditions, ordered tasks with rollback. An agent can start.
- **Partial**: some sections are implementation-ready; others need a decision, a human or a live system.
- **Decision-blocked**: the core needs an owner decision first.
- **Live-dependent**: it can be specified but not proven without the owner's Qdrant, Railway, Supabase or provider account.

A spec that is implementation-ready is still unimplemented. Readiness of a document is not readiness of the product.

## 2. Matrix

| # | Requested spec | File (lines) | Status | Implementation-ready now | Blocked by decision | Needs live system or human | Earlier audit coverage it builds on |
|---|---|---|---|---|---|---|---|
| 6.1 | Ingestion and content processing | `specifications/INGESTION_AND_CONTENT_PROCESSING_SPEC.md` (339) | Partial | Stage contracts S4-S12 (input, output, ID, idempotency key, partial-failure detection, resume, reprocess); NEW-ING-1 rights stamping, NEW-ING-2 snapshot-abort and upsert-then-delete, NEW-ING-6 text-and-hash check | Governance §6: takedown redaction (D-PI2), withdrawal scope (D-PI3), in-place replace (D-PI1); source registry (ADR-007, D-08) | Live v10 rights stamp origin (D-PI4, owner build log) | `06`, `07`, `17` ADR-007/008, `22` |
| 6.2 | Retrieval and RAG | `specifications/RETRIEVAL_AND_RAG_SPEC.md` (565) | Partial | Retrieval plan in shadow mode, containment-aware dedup, bank schema v2 with correct intervals, budget table | Judge model and price (D-16); floors (D-PQ3); one scorer timeout (D-PG13 = D-PQ4); shadow run approval (D-PQ1) | Bank labels (human); live bank run | `05`, `08`, `17` ADR-003/009, `18`, `22a` |
| 6.3 | Multi-video teaching synthesis | `specifications/MULTI_VIDEO_TEACHING_SYNTHESIS_SPEC.md` (479) | Variant A implementation-ready **in shadow mode**; Variant B decision-blocked | Variant A: `EvidenceCandidate`, `build_evidence_set`, wire shape, static copy, tests, shadow logging | Serving Variant A: D-PQ2. Variant B (labelled assistant layer): D-03 | Human review of conflicted sets (D-PQ6); faithfulness review | `07` multi-video design, `10`, `17` ADR-001, `26` §7.3 |
| 6.4 | Data quality and cross-store consistency | `specifications/DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md` (398) | Partial | Static checks C-S1 to C-S8 on fixtures; live audit script NEW-DQ-1 (read-only) | D-DQ1, D-DQ2, D-14, D-15 | All live checks (`FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md`) | `06`, `22` |
| 6.5 | Guru knowledge and knowledge graph | `specifications/GURU_KNOWLEDGE_AND_KNOWLEDGE_GRAPH_SPEC.md` (402) | Partial | Registry v2 loader and schema, startup check, hard-coded literal replacement (28 places tabled), onboarding checklist with a test per step | Joint attribution (D-PG1), rights vocabulary (D-PG2), graph retirement (D-05) | Guru review; rights holder | `11`, `14c`, `17` ADR-005/013 |
| 6.6 | AI harness, prompts and context | `specifications/AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` (448) | Partial | GraphState declarations, untrusted-content fence helper, scorer model required, price table test, prompt registry v1, injection screens, model-change and embedding-change procedures | Judge consolidation and task-based routing (D-17, D-04); registry storage (D-PG11) | Model-change runs need the provider | `09`, `17` ADR-009/011 |
| 6.7 | Spiritual answer quality and response contract | `specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` (646) | Partial | Honest grounding and outcome composition, abstain cause, wire parity, static copy keys, release invariants suite, statistical gate tooling | `clip_ref` on the wire (D-PQ7); reflection catalogue authorship (D-PQ8); failure copy (D-PQ9); explanation layer (D-03); distress (D-06) | Native review (D-22); clinician (T4-04) | `10`, `14b`, `17` ADR-001/002 |
| 6.8 | Personal mentor, memory and personalisation | `specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` (694) | Partial | Consent scopes, proposals, settings, export, erasure registry, saved wisdom as pointers | Learning journeys and reminders (D-PM6, D-PM9); legacy plane retirement (D-PM1); review model (D-PM3); retention values (D-PM4) | Real-Postgres RLS fixture needs a test database | `12`, `12b`, `14`, `14d` |
| 6.9 | Complete FR / NFR and acceptance matrix | `specifications/COMPLETE_FR_NFR_AND_ACCEPTANCE_MATRIX.md` (305) | Complete as a matrix; requirements themselves mostly partial | 44 FRs and 82 NFRs with test, criterion and gate; 12 broken links; testing method per component | — | 18 NFRs are aspirational and unmeasured | `03`, `04`, `traceability-matrix.md` |
| 6.10 | Production reliability, security and cost | `specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md` (1,017) | Partial | SLOs (proposed), alert repair, 10 runbooks, backup contract, adversarial suite (compliant variant) | Answer trace storage (D-PE2); feedback text handling (D-PE5); final SLO values (D-PE7) | Restore drill, alert drill, load test | `15`, `14`, `16` §5/§7, `26` |
| 6.11 | Railway deployment and operations runbook | `specifications/RAILWAY_DEPLOYMENT_AND_PRODUCTION_OPERATIONS_RUNBOOK.md` (667) | Specification; nothing run on Railway | Full proposed `.railway/railway.ts`, variable matrix, per-service settings, smoke set, rollback, Railway incident playbooks | D-26, D-14, D-07, staging project shape | Everything in Gate A A1-A21 | `22b` (with corrections listed in the runbook §1) |
| — | Historical architecture decisions | `specifications/ARCHITECTURE_DECISION_RECORDS_HISTORICAL.md` (325) | Complete for its purpose | 16 historical ADRs, 25 "do not reintroduce" items with sources, ADR template and trigger rule | — | — | `17`, `19` §6, `lessons.md`, CLAUDE.md |

## 3. Direct answers for the five specs the owner named

| Spec | Sufficient to implement? | Evidence |
|---|---|---|
| Ingestion | **Partly.** The offline build path is specified stage by stage, and the first two tasks fix real defects (DATA-20: the v10 builder never stamps `domain_rights_status`, while retrieval filters on "licensed", `first_person_context_store.py:464`; DATA-23: per-video replace deletes before it upserts). Governance (registration, withdrawal, correction propagation) is specified but waits on D-08, D-PI1 to D-PI3. | Ingestion spec §2.2, §6, §8 |
| Retrieval | **Mostly.** The live first-person path is traced end to end with every LLM call and budget. Shadow-mode planning and containment dedup are ready. Floors need a baseline first. The retrieval bank has only 8 rows with placeholder IDs, so it cannot run live until it is labelled. | Retrieval spec §2, §3.5, §8; data-quality agent report |
| Data quality | **Yes for static checks; no for live proof.** Every datastore has the 15 required fields. Live checks are written as an owner-run checklist. | Data-quality spec §3; `FINAL_QDRANT_LIVE_VALIDATION_CHECKLIST.md` |
| Multi-video synthesis | **Variant A yes, in shadow mode. Serving needs D-PQ2. Variant B no (D-03).** The live wire today has nine citation fields and no `guru_id`, `video_id`, end time or clip id, so multi-clip answers need the new `answer_blocks` field first (NEW-ANS-3). | Synthesis spec §0, §3; answer contract spec §2 |
| Personalisation | **Partly.** Consent, proposals, export, erasure registry and saved wisdom are ready. Journeys and reminders need decisions. The spec found five new defects (MEM-007 to MEM-012), including memory export that omits memory and an unfenced extractor. | Memory spec §1, §9 |

## 4. Cross-spec conflicts found

| Conflict | Specs | Resolution path |
|---|---|---|
| A clip id is needed on the client (saved clips, reports, multi-clip), but `backend/tests/test_citation_contract.py:169-205` forbids `point_id` on the wire | Memory spec, answer contract spec | D-PQ7 before NEW-ANS-3 or NEW-MEM saved-wisdom tasks |
| Three scorer timeout values (25.0 s `config.py:478`, 15.0 s `docker-compose.yml:325`, 12 s CLAUDE.md) | Harness spec (D-PG13), retrieval spec (D-PQ4) | Decide once |
| `PersonalizeStage` runs the generating graph, which conflicts with CLAUDE.md invariants 1, 15 and 21 | Memory spec | D-03 |
| Gate A numbering (first draft A1-A12 versus A1-A21) | All FINAL files | Remapped by the lead on 2026-11-05; A1-A21 in `FINAL_RAILWAY_STAGING_READINESS.md` is authoritative |

## 5. Implementation-readiness checklist per task (brief Part 10)

| Element | Where each spec provides it | Gap |
|---|---|---|
| Exact file paths | §8 task tables | None found in the lead's sample |
| Current behaviour | §2 (verified, `path:line`) | — |
| Required change | §3 contracts, §4 behaviour | — |
| Root cause | Finding records in `16` and the owning audit doc; not repeated in task rows | The agent must open the finding ID; the task row names it |
| Constraints | Spec §0 dependencies; CLAUDE.md invariants | — |
| API or data contracts | §3 | — |
| Tests | §7 (file and case) | Some tests are named but marked MISSING; the task creates them |
| Acceptance criteria | §7 pass conditions | Live and human criteria are marked and cannot be met in CI |
| Non-goals | §8 task tables | — |
| Dependencies | §8 and §9 | — |
| Rollback | §8 task tables | — |

## 6. Verified, assumptions, unknowns

- Verified: file sizes and status lines read on 2026-11-05; task tables in §8 of each spec listed by the lead; the scorer timeout values and the default collection logic re-read in `config.py`.
- Assumptions: the lead did not re-verify every `path:line` inside every spec. The independent review (`FINAL_USAGE_AND_VERIFICATION_LOG.md` §4) samples them.
- Unknown: whether the owner's decisions will keep the recommended options; several specs change shape if D-03 or D-05 go the other way.
