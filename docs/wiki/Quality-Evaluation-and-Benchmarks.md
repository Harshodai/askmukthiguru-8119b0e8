# Quality Evaluation, Benchmarks & Safety Guards

AskMukthiGuru implements an exhaustive, multi-tiered evaluation harness and mechanical safety guard framework. Because AskMukthiGuru serves sacred spiritual wisdom and interacts with seekers who may experience acute distress, quality and attribution are not treated as subjective sentiments—they are enforced through automated verification gates, probabilistic boundaries, and pre-commit AST guards.

---

## 1. Quality Evaluation Architecture

The quality evaluation framework operates at three distinct checkpoints: pre-commit (working tree and claims), continuous integration (deterministic tests and contract audits), and release verification (RAGAS and live benchmarks).

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             QUALITY & BENCHMARK EVALUATION HARNESS                               │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│      1. PRE-COMMIT GUARDS      │      2. RETRIEVAL & AUDIT      │      3. RELEASE BENCHMARKS     │
├────────────────────────────────┼────────────────────────────────┼────────────────────────────────┤
│ • guard-publication            │ • Golden-25 Attribution Gate   │ • RAGAS Faithfulness (≥0.60)   │
│   (PII / clip-text / dumps)    │   (Speaker ECAPA-TDNN audit)   │ • Context Recall & Precision   │
│ • guard-claims                 │ • 86-Item Unanswerable Draft   │ • CitationFaithfulness Ledger  │
│   (Bans unqualified claims)    │   (Abstain ≥95% on 60+ core)   │ • Router Margin Calibration    │
│ • check-no-pii-dumps           │ • Relevance Minimum Thresholds │   (0.66 → 0.74 boundary sweep) │
│   (INV-6 working tree check)   │   (Cosine floor: 0.72)         │ • C-SSRS Safety Traps (153/153)│
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

## 2. RAGAS Faithfulness & Context Recall Benchmarks

The RAGAS evaluation runner (`scripts/eval/run_ragas_eval.py` and `backend/scripts/eval/run_ragas_eval.py`) measures end-to-end generation fidelity against retrieved spiritual passages.

### 2.1 Metric Definitions & Production Thresholds

| Metric | Threshold | Method & Engine | Description |
|---|---|---|---|
| **Faithfulness** | $\ge 0.60$ (CI hard gate)<br/>$\ge 0.85$ (Production target) | RAGAS / `gpt-4o-mini` | Verifies that every factual claim in the response is strictly inferable from the retrieved context. |
| **Answer Relevancy** | $\ge 0.75$ | Embedding cosine similarity | Compares generated reverse-queries against the original seeker prompt. |
| **Context Precision** | $\ge 0.70$ | RAGAS ranking evaluator | Measures whether relevant chunks appear at the highest retrieval ranks. |
| **Context Recall** | $\ge 0.80$ | Reference ground truth | Evaluates whether all necessary theological concepts from the gold set are retrieved. |

### 2.2 Citation Faithfulness Claim Ledger (`tests/test_ragas_claim_ledger.py`)

To prevent hallucinations without relying entirely on third-party cloud LLMs during local testing, `run_ragas_eval.py` includes a pure-standard-library `citation_faithfulness_audit` engine.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               CITATION FAITHFULNESS AUDIT ENGINE                                 │
├───────────────────────────────┬──────────────────────────────────┬───────────────────────────────┤
│         Input Text            │        Context Spans             │         Ledger Output         │
├───────────────────────────────┼──────────────────────────────────┼───────────────────────────────┤
│ "A Beautiful State is free   │ [0] "Sri Preethaji teaches that  │ Claim: "free from suffering"  │
│ from suffering and marked by  │     a Beautiful State is free    │ Context Match: Span [0]       │
│ stillness [1]."               │     from suffering..."           │ Grounded: TRUE (Citable: YES) │
├───────────────────────────────┼──────────────────────────────────┼───────────────────────────────┤
│ "A Beautiful State requires   │ [1] "Sri Krishnaji teaches the   │ Claim: "strict fasting"       │
│ strict fasting every new      │     Serene Mind practice..."     │ Context Match: None           │
│ moon [2]."                    │                                  │ Grounded: FALSE (Flagged: NO) │
└───────────────────────────────┴──────────────────────────────────┴───────────────────────────────┘
```

#### Key Invariants:
1. **Target Boundary Validation**: If a bracketed citation points to an out-of-range index (e.g., `[5]` when only 2 contexts exist), it is immediately flagged with `reason="target_out_of_range"`.
2. **Context Support Check**: If a citation index is within range but the referenced chunk does not contain supporting semantic tokens, it is flagged with `reason="cited_span_does_not_support_claim"`.
3. **Context-Only First-Person Invariant**: First-person teacher voice clips (`first_person_v10`) must strictly serve as direct quotation evidence. Zero generated synthetic claims may cite first-person spans as authoritative background context (`fp_spans_are_context_only_zero_citations`).

### 2.3 Running RAGAS Evaluations

```bash
# Standalone evaluation against local backend
cd backend && python ../scripts/eval/run_ragas_eval.py

# Against staging or production over HTTPS
RAGAS_LLM_API_KEY=sk-... \
BACKEND_URL=https://api.askmukthiguru.com \
SUPABASE_JWT=<service-or-admin-jwt> \
python scripts/eval/run_ragas_eval.py --output reports/eval_$(date +%Y%m%d).json

# Continuous Integration mode (hard exit code 1 if mean faithfulness < 0.6)
python scripts/eval/run_ragas_eval.py --ci --threshold 0.6
```

---

## 3. Golden-25 First-Person Attribution Gate

The **Golden-25 First-Person Attribution Benchmark** (`audits/reports/quality_probe_ooc_golden25_2026-10-11.json` and `audits/evidence/first_person_v10_strict_audit_...`) verifies voice attribution integrity for the spoken teachings of Sri Preethaji and Sri Krishnaji.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             GOLDEN-25 ATTRIBUTION VALIDATION GATE                                │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   [Query Bank (25 Golden Prompts)] ───► [FirstPersonBridge]                                      │
│                                                │                                                 │
│                                         [ECAPA-TDNN Gate]                                        │
│                                                ├──────────────────┬─────────────────┐            │
│                                                ▼                  ▼                 ▼            │
│                                            Verified           Conflict         Impostor          │
│                                        (Margin ≥ +0.15)    (Both Claims)     (Margin < 0)        │
│                                                │                  │                 │            │
│                                                ▼                  ▼                 ▼            │
│                                            [SERVE]           [QUARANTINE]       [REJECT]         │
│                                         (Review Candidate)  (Tier: Conflict)  (Fail-Closed)      │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Attribution Methodology & Constants:
* **Audio Anchor Reference**: Derived from two human-confirmed anchor moments in `backend/scripts/ops/speaker_attribution.py::ANCHORS` widened across training splits.
* **ECAPA-TDNN Model**: Loads pinned Hugging Face model checkpoint `speechbrain/spkrec-ecapa-voxceleb` (invariant X18/X20).
* **Thresholds**:
  * `ENROLL_MIN = 0.75`: Minimum cosine similarity to widen reference embeddings.
  * `ANCHOR_LABEL_MIN = 0.55`: Minimum score to associate a candidate slice with a teacher.
  * `ANCHOR_MARGIN = 0.15`: Delta between the primary teacher score and competing impostor score.
  * `CLUSTER_DISTANCE = 0.60`: Agglomerative clustering distance limit across ASR seams.

### Gate Verdicts:
1. **Verified Candidate**: Teacher voice matches claimed guru ID with margin $\ge 0.15$.
2. **Refused Guru Mismatch**: Acoustic model identifies Sri Preethaji while metadata asserts Sri Krishnaji (or vice-versa). Instantly excluded from serving.
3. **Quarantine Tier**: 45 historical spans exhibiting speaker boundary conflicts are quarantined in `audits/evidence/public_release_phase4_speaker_conflict_review_2026-10-22.md` pending physical owner sign-off.

---

## 4. 86-Item Unanswerable Draft Evaluation Benchmark

To prevent hallucination when seekers ask questions outside the spiritual domain, AskMukthiGuru executes an 86-item unanswerable benchmark (`evals/first_person/unanswerable60_draft.jsonl` and `unanswerable38_draft.jsonl`).

### 4.1 Benchmark Composition

The suite spans 86 total test items across 4 operational categories:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            86-ITEM UNANSWERABLE BENCHMARK SUITE                                  │
├───────────────────────────────┬───────┬────────────────────────────┬─────────────────────────────┤
│ Category                      │ Count │ Typical Inquiries          │ Target System Behavior      │
├───────────────────────────────┼───────┼────────────────────────────┼─────────────────────────────┤
│ 1. Secular Trivia & Science   │  22   │ Penicillin discovery,      │ Abstain: No teacher clip    │
│                               │       │ Jupiter moons, square root │ found.                      │
├───────────────────────────────┼───────┼────────────────────────────┼─────────────────────────────┤
│ 2. Other Teachers / Traditions│  24   │ Isha Kriya, Advaita text,  │ Abstain: Clarify focus on   │
│                               │       │ Pali canon, Eckhart Tolle  │ Sri Preethaji & Krishnaji.  │
├───────────────────────────────┼───────┼────────────────────────────┼─────────────────────────────┤
│ 3. Professional / Medical /   │  20   │ Stock tips, divorce law,   │ Fail-closed: Explicitly     │
│    Legal Advice               │       │ paracetamol dosage, tenant │ decline professional advice.│
├───────────────────────────────┼───────┼────────────────────────────┼─────────────────────────────┤
│ 4. Logistics & Current Events │  20   │ Gold price today, flight   │ Abstain: Real-time external │
│                               │       │ schedules, temple hours    │ facts unavailable.          │
└───────────────────────────────┴───────┴────────────────────────────┴─────────────────────────────┘
```

### 4.2 Scoring Invariant:
* **Core Subset**: 69 items are designated `scoring_group: "core"`.
* **Abstention Gate**: The pipeline must achieve **$\ge 95\%$ abstention** across the core evaluation set.
* **Failure Modes**: An unanswerable query that returns an AI-generated answer or forces a low-similarity clip into a direct answer is flagged as a catastrophic failure.

---

## 5. Relevance Minimum Gates & Distress Boundary Calibration

### 5.1 Retrieval Relevance Minimum

To prevent low-confidence or irrelevant clips from polluting seeker responses, the retrieval node enforces strict cosine cutoffs:

* **General RAG Vector Cutoff**: Dense similarity score $\ge 0.72$ against `spiritual_wisdom_contextual`.
* **First-Person Verbatim Cutoff**: Hybrid score $\ge 0.78$ against `first_person_v10`.
* **Sub-Threshold Handling**: Queries scoring below the cutoff trigger graceful fallback (`handle_fallback`), prompting the user for clarification or offering related curated topics rather than guessing.

### 5.2 Distress Router Margin Calibration (0.66 to 0.74 Boundary)

The Intent Router (`backend/rag/nodes/routing.py`) uses semantic vector embeddings to distinguish between philosophical inquiries about suffering and acute seeker distress.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                          DISTRESS ROUTER THRESHOLD CALIBRATION CURVE                             │
├───────────────┬───────────────────────────┬───────────────────────────┬──────────────────────────┤
│ Threshold     │ On-Topic Hijack Rate      │ Acute Crisis Sensitivity  │ Safety Verdict           │
├───────────────┼───────────────────────────┼───────────────────────────┼──────────────────────────┤
│ 0.66          │ HIGH (32/150 hijacked)    │ 100% caught               │ UNACCEPTABLE (False Pos) │
│ 0.70          │ MODERATE (18/150 hijacked)│ 100% caught               │ SUB-OPTIMAL              │
│ 0.72          │ LOW (10/150 hijacked)     │ 100% caught               │ BALANCED                 │
│ 0.74+         │ ZERO (0/150 hijacked)     │ DEGRADED ("suicidal" miss)│ DANGEROUS (False Neg)    │
└───────────────┴───────────────────────────┴───────────────────────────┴──────────────────────────┘
```

#### Calibration Invariant (Repository Invariant X27):
> [!CAUTION]
> **Boundary Freezing**: At thresholds $\ge 0.74$, explicit self-harm utterances like *"I am suicidal"* stop matching the router node. While downstream input guardrails (`InputGuardrailStage`) provide defense-in-depth, **this router boundary must never be adjusted above 0.72 without an audited clinician-review pass**.

---

## 6. Mechanical Pre-Commit Lesson Guards

To guarantee that critical lessons from previous production incidents are not accidentally regressed by human engineers or AI agents, AskMukthiGuru enforces mechanical AST and regex guards in `scripts/guards/lesson_guards.py` via `.pre-commit-config.yaml`.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                MECHANICAL PRE-COMMIT HOOK GATES                                  │
├───────────────────────────────┬──────────────────────────────────┬───────────────────────────────┤
│ Hook Identifier               │ Enforcement Target               │ Blocking Condition            │
├───────────────────────────────┼──────────────────────────────────┼───────────────────────────────┤
│ `guard-publication`           │ Repository disclosure prevention │ Blocks audio/video, DB dumps, │
│                               │ (L-PUBLIC-REPO-1)                │ raw clip text, user home paths│
├───────────────────────────────┼──────────────────────────────────┼───────────────────────────────┤
│ `guard-claims`                │ Verification discipline          │ Blocks unproven readiness or  │
│                               │ (L-GO-NEEDS-COMMAND-1)           │ unverified pass status in docs│
├───────────────────────────────┼──────────────────────────────────┼───────────────────────────────┤
│ `check-no-pii-dumps`          │ Working tree privacy clean       │ Blocks neo4j.dump, cookies,   │
│                               │ (INV-6 Working Tree Integrity)   │ redis_dump, supabase_dump.    │
└───────────────────────────────┴──────────────────────────────────┴───────────────────────────────┘
```

### 6.1 `guard-publication` (L-PUBLIC-REPO-1)
* **Audio & Binary Blocks**: Rejects commits containing `.wav`, `.mp3`, `.m4a`, `.flac`, `.mp4`, `.dump`, or `.rdb` files.
* **Teacher Speech Columns**: Scans CSV headers for banned text columns (`text`, `verbatim`, `clip_text`, `transcript`, `passage`).
* **Unredacted JSON Records**: Scans JSON/JSONL trees to ensure keys containing verbatim speech are omitted unless matching `scripts/guards/publication_allowlist.txt`.
* **Local Home Path Sanitization**: Greps for local developer home directories (such as user home or root directories) across JSON/JSONL records and documentation to ensure private system architecture details are never leaked to the public repository.

### 6.2 `guard-claims` (L-GO-NEEDS-COMMAND-1 & L-PRELAUNCH-SKIP-1)
* **Unqualified Assertions Blocked**: Matches regex `\b(PROD(UCTION)?[- ]READY|FACULTY[- ]READY|ALL GREEN|VERDICT:?\s*\**GO\b)`. <!-- claim-ok -->
* **Mandatory Substantiation**: An engineer or agent cannot claim a feature is "production-ready" without providing the verifiable testing command or qualification in the same line (e.g., `cmd: pytest backend/tests/...`, `claim-ok`, or explicitly stating `NO-GO`).

### 6.3 `check-no-pii-dumps` (INV-6 Integrity Gate)
* **Local Pre-Commit Script**: Executes `bash scripts/security/check_no_pii_dumps.sh`.
* **File Targets**: Confirms that accidental local database exports (`neo4j.dump`, `supabase_dump.sql`, `redis_dump.rdb`, `cookies.txt`) never exist in the working tree, even if listed in `.gitignore`.
* **Size Backstop**: Blocks any staged file exceeding 500 KB (`check-added-large-files`).

---

## 7. Cross-Reference Navigation

* [Architecture: RAG Execution Pipeline](Architecture-RAG-Pipeline)
* [First-Person Serving & Attribution](Architecture-First-Person-Serving)
* [Serene Mind Distress Triage & Helplines](Domain-Serene-Mind-Safety)
* [Operations, Deployment & CI Gates](Operations-Deployment-and-CI)
* [Troubleshooting Runbooks & Diagnostics](Troubleshooting-and-Runbooks)
