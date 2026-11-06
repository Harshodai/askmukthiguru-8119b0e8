# Requirement traceability matrix

Owner: lead. Chain: business objective → user need → FR → architectural component → data dependency → API contract → acceptance test → metric.

- FR definitions and current status: `03` §4.
- Components: `17` §4. Tasks: `20`. NFRs: `04`.
- Status codes: L = live, LD = live with defect, P = partial, F = flagged, A = absent, U = unknown.
- Objectives: O1 trustworthy teaching answers (P2, P4); O2 safe care for vulnerable seekers (P4); O3 a returning mentor relationship (P5); O4 a stable, low-cost platform (P1); O5 extensible to future teachers (P4); O6 respect for rights and privacy (P4, P6).

| FR | Status | Obj | User need | Component (target) | Data dependency | API contract | Acceptance test | Metric (NFR) | Task |
|---|---|---|---|---|---|---|---|---|---|
| FR-ONB-01 | P | O3 | Know what the product is and is not | Onboarding UI; AI disclosure | — | static | e2e onboarding spec; disclosure visible | A11Y-01 | T6-04 |
| FR-AUTH-01 | L | O6 | Sign in safely (18+, MFA for admins) | Supabase Auth; `get_current_user_from_supabase` | `auth.users`, `user_roles` | Supabase JWT | existing auth tests | SEC-02 | — |
| FR-AUTH-02 | L | O4 | Try without an account | Anon session HMAC; anon quota | Redis `anon:*` | `POST /api/auth/anon-session` | quota 429 test | SEC-01, REL-03 | T1-08 |
| FR-PROF-01 | L | O3 | Manage profile and settings | Profile pages | `profiles` | Supabase RLS | profile e2e | PRIV-03 | — |
| FR-CONV-01 | L | O1 | Ask and receive in a conversation | Stage chain → route → lane | conversations, messages | `POST /api/chat`, `/api/chat/stream` | chat e2e; outcome event emitted | OBS-01, REL-01 | T2-03 |
| FR-CONV-02 | LD | O4, O3 | My history is mine, correct, and available on any device | Backend writes assistant turns; server is the history source of truth for signed-in users | `chat_messages` RLS | RLS: client inserts `role='user'`; list/read/delete conversations API | RLS test; cross-device e2e (UX-006) | SEC-06 | T6-05, T6-09 |
| FR-INT-01 | P | O1 | The system understands what I ask | Route-decision service; AnswerPlan | `teaching_scope.yaml` (new file, proposed in `21`) | internal | routing set recall ≥95% | AIQ-03 | T4-03, T5-01 |
| FR-INT-02 | A | O1 | Ask me when my question is unclear | AnswerPlan `clarify` mode | — | `layers[type=follow_up]` | held-out ambiguous stratum | AIQ-01 | T5-01 |
| FR-SRC-01 | P | O5 | Choose a teacher or source | Teacher registry filter | `gurus.yaml`, span `teacher_id` | request `teacher_ids[]` | filter test; no cross-teacher leakage | DI-03 | T8-01, T1-04 |
| FR-RET-01 | L | O1 | Find the right teaching | Hybrid retrieval, gates, evidence judge | Qdrant vNext | internal | frozen bank Recall@10 | AIQ-06, PERF-05 | T4-01, T4-02, T4-06 |
| FR-MV-01 | P | O1 | Combine teachings across videos | Facet retrieval + set selector + composer | span tags, concept vocab | `layers[]` with multiple `span_ids` | multi-facet stratum coverage | AIQ-01 | T5-02, T5-03 |
| FR-ATTR-01 | L | O1 | Know who said it, where, when | Citation rendering; speaker label rules | `message_citations`, span `speaker_verified` + method | `citations[{span_id, video_id, start_ms, end_ms, speaker, verification_state}]` | attribution test; label rules (`03`) | DI-04 | T3-06 |
| FR-ATTR-02 | A | O1 | Never see an invented quote | Lint + registry-sourced quotes | span store | — | lint passes; 0 unsourced | CI-03 | T1-03 |
| FR-SRCX-01 | P | O1 | Watch or read the original | CitationCard playback | playback window ±0.25 s | `start_ms`, `end_ms` | playback e2e; absolute URLs | A11Y-02 | T1-16 |
| FR-ANS-01 | L | O1 | Receive the teacher's own words | Bridge exact-quote assembly | `span_text_sha256` | `layers[type=verbatim, voice=teacher]` | quote-integrity suite | DI-01, AIQ-08 | T3-03 |
| FR-ANS-02 | P | O1 | Know how strong the match is | Labels "Related, not a direct answer" / calibrated "direct" | calibration profile | `verification.direct` | calibration only with ≥299 items | AIQ-05 | T2-04 |
| FR-DEPTH-01 | P | O1 | Short or deep, as I need | AnswerPlan depth | user preference (memory) | request `depth` | depth stratum rubric | AIQ-01 | T5-01 |
| FR-REFL-01 | P | O3 | Reflect on what it means for me | Composer L5 (assistant voice) | — | `layers[type=reflection, voice=assistant]` | voice lint; rubric | AIQ-08 | T5-03 |
| FR-FUP-01 | P | O3 | Continue the thread | `answer_trace` | `message_citations` | `follow_up_of: message_id` | follow-up resolves to prior spans | SCAL-03 | T5-05 |
| FR-MEM-01 | L | O3 | Be remembered only as I allow | Canonical memory; consent receipts | memory tables | `/api/memory/*` (23 routes) | consent tests; erasure tests | PRIV-02, PRIV-03 | T6-01 |
| FR-PERS-01 | F | O3 | Teaching connected to my situation | Composer L4 from consented memory | canonical memory | `layers[type=personal]` | no read without consent | PRIV-03 | T6-02 |
| FR-LANG-01 | P | O1 | Use my language | Locales; labelled translation | span `language` | `Accept-Language`; `layers[].lang` | native review sign-off | I18N-01..04 | T5-06 |
| FR-SAVE-01 | A | O3 | Keep what helped me | Saved answers + collections | `saved_answers` → `message_citations` | `POST /api/saved` | save/revisit e2e; takedown propagates | CI-02 | T6-04 |
| FR-JRN-01 | P | O3 | Learn progressively | Journeys v1 (curated sequences of spans) | registry + spans | `/api/journeys` | sourced content only | CI-03 | T6-04 |
| FR-PRAC-01 | LD | O2 | Be guided in a practice | Templated practices | licensed audio only | static | rights row per asset | CI-04 | T0-02 |
| FR-FB-01 | L | O1 | Tell you it helped or not | Feedback → outcome events | feedback table | `/api/feedback` | joined into `useful_answer` | OBS-01, COST-03 | T2-03 |
| FR-CORR-01 | P | O6 | Report a wrong clip | Clip report control → review queue → takedown | `clip_reports`, registry | `/api/feedback/clip-report` | e2e report; admin sees it | CI-02 | T6-04, T3-06 |
| FR-SAFE-01 | LD | O2 | Get real help in a crisis | Crisis pre-check; verified helplines | `helplines.yaml` (verified) | `safety_notices[]` | crisis core set 100%; benign ≤5% | SAFE-01..05 | T4-04, T4-07 |
| FR-DATA-01 | LD | O6 | Export and delete my data | Direct deletion flow (replaces the CancelFlow funnel, the only UI path today) + durable erasure job + scheduled-deletion purge | all user stores | `delete-my-account`, export | e2e direct deletion; erasure completes with backend down (queued); no win-back email | PRIV-02 | T1-12, T6-06 |
| FR-ADM-01 | L | O4 | Operate safely as admin | Admin app (AAL2 + role) | `user_roles` | `/api/admin/*` | auth tests | SEC-02 | — |
| FR-ADM-02 | U | O4 | No demo data in production | Seed RPC disabled in production | — | admin RPC | prod config test | — | T9-01 |
| FR-TCH-01 | A | O5 | Add a new teacher safely | Registry-driven onboarding | `gurus.yaml`, source registry | admin workflow | `11` §6 checklist dry run | MAINT-05 | T8-01, T8-02 |

## Findings → requirements (high-impact links)

| Finding | FRs affected |
|---|---|
| ANS-001, ANS-002, SAFE-002, SAFE-003 | FR-SAFE-01, FR-INT-01, FR-ANS-01 |
| ANS-003, AI-001, SYS-002 | FR-INT-01, FR-ANS-01 |
| ANS-004, RET-03, RET-04 | FR-MV-01, FR-DEPTH-01, FR-REFL-01 |
| GURU-012 | FR-ATTR-02 |
| PRD-006 | FR-CORR-01 |
| DATA-07, DATA-12 | FR-CORR-01, FR-SAVE-01, FR-ATTR-01 |
| MEM-003 | FR-MEM-01, FR-PERS-01 |
| PRD-003 | FR-CONV-02 |
| IP-002 | FR-PRAC-01 |
| UX-001, ADV-01 | FR-DATA-01 |
| UX-006 | FR-CONV-02, FR-MEM-01 |
| UX-005, UX-007 | FR-ANS-01, FR-SAFE-01, FR-ATTR-01 |
| UX-008 | FR-LANG-01, FR-SAFE-01 |
| PRD-009, PRD-010, UX-009, UX-011 | FR-CONV-01, FR-ONB-01, FR-PERS-01, FR-AUTH-02 |
