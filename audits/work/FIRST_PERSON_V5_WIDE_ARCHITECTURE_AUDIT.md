# First-Person Ingestion → Data → v5 Pipeline: Production-Readiness Audit

**Audit date:** 2026-09-28  
**Repository:** `Harshodai/askmukthiguru-8119b0e8`  
**Scope:** first-person ingestion, corpus/data contracts, indexing, v5 serving, safety, isolation, operations, and benchmark validity.  
**Method:** repository/code review, live Docker/Qdrant/API probes, corrected in-container tests, and external architecture guidance. No code or data writes were made by this audit.

## Verdict

The first-person route is a **credible safety-oriented prototype and a strong integration baseline**, but it is **not production-ready for general traffic or multi-guru scale**.

The most important distinction is:

> The clip-level serving safeguards are materially better than the system-level release safeguards.

The live container is healthy and currently configured to serve `first_person_v5`. The corrected in-container first-person suite passes **85/85 tests**. Crisis pre-emption works, v5 clips are rights-cleared and at least eight seconds long, and the serving path re-checks hashes, speaker allowlists, artifact filters, and dangling conjunctions.

However, the live service is still `IS_PRODUCTION=false`, `FIRST_PERSON_SERVE_UNREGISTERED=true`, has **no Qdrant aliases**, has **no calibration profile wired**, and the active architecture does not yet prove reproducible, independently isolated, continuously promotable guru datasets. The current state is therefore suitable for controlled shadow/beta evaluatioHowever, the live service is still `IS_PRODUCTION=false`, `FIRST_PERSON_SERVE_UNREGISTERED=true`, has **no Qdrant aliases**, has **no calibration profile wired**, and the across `docs/agent/HANDOFF_2026-09-28_FIRST_PERSON_V5_RUTHLESS_AUDIT.md`, `docs/agent/STATE_RECONCILIATION_2026-09-27.md`, `backend/scripts/ops/build_first_person_index.py`, `backend/services/speaker_diarization.py`, and `backend/services/first_person_store.py`, is:

1. Discover and fetch source videos/transcripts.
2. Preserve a verbatim transcript layer and a display layer.
3. Attach word timestamps and speaker turns.
4. Keep only allowlisted teacher speech; exclude host speech.
5. Record rights/provenance and a SHA-256 transcript hash.
6. Segment into complete conceptual clips rather than arbitrary ASR windows.
7. Reject low-quality, short, corrupted, unverified, or incomplete clips.
8. Build deterministic point IDs so retries and rebuilds are idempotent.
9. Store passage vectors, question vectors, sparse vectors, and pointer metadata in a versioned Qdrant collection.
10. Promote a candidate only after benchmark, safety, reproducibility, and operational gates.

The design goal is sound: **the model should not manufacture the teacher’s words**. The route should return a pointer to recorded discourse, exact text, and playback timestamps, or abstain/crisis-redirect.

### 1.2 v5 serving promise

`backend/app/api/first_person.py` and `backend/services/first_person_pipeline.py` define this route:

```mermaid
flowchart LR
  Q[Seeker query] --> S[Crisis / distress pre-check]
  S -->|crisis| C[Helpline redirect]
  S -->|safe| T[  S -->|safe| T[  S -->|safe| T[  S -->|safe| T[  S -->|safE --> R[Hybrid Qdrant retrieval]
  R --> G[Integrity gate]
  G --> D[Calibrated decision]
  D -->|confident| V[Verbatim citations]
  D -->|  D -->|  D -->|  D -->|  D -->|  D -->|  D -->|  D -->|  D --tention]
  V --> P[Timestamped playback + exact cache]
```

The code explicitly avoids semantic caching on this route, validates cached citations again, limits one clip per video, and keeps translated glosses separate from `verbatim_text`.

## 2. What was re-verified directly

| Area | Verified result | Interpretation |
|---|---|---|
| Docker | Docker Desktop 4.92.0, backend running healthy, restart count 0 at probe | Local runtime is operational, not proof of deployment readiness |
| API health | `/api/health` returned `ready:true`, `status:healthy`; Qdrant, Redis, LLM, embedding, graph, and queue signals reported healthy | Health is dependency reachability/readiness, not answer quality or production config |
| Active route | `FIRST_PERSON_COLLECTION=first_person_v5`, route enabled | v5 is active in this local container |
| Production mode | `IS_PRODUCTION=false` | This is explicitly not a production runtime |
| Registration gate | `FIRST_PERSON_SERVE_UNREGISTERED=true` | Dangerous if copied to any deploy; rights/registration enforcement is intentionally relaxed |
| Qdrant aliases | `aliases: []` | No atomic candidate-to-live promotion or instant rollback contract exists |
| v2 collection | 280 points; 72 with `rights_cleared != true`; 44 under 8 seconds | Legacy/live candidates are not uniformly safe; a collection name alone is not a go| v2 collection | 280 points; 72 with `rights_cleared != true`; 44 under 8 seconds | Legacy/live candidates are not uniformly safe; a collection | 260 points; 0 rights failures; 0 eligibility failures; 0 clips under 8 seconds | Stronger candidate data contract, but not sufficient for traffic promotion |
| Container tests | `python -m pytest -q tests/test_first_person_pipeline.py tests/test_build_first_person_index.py tests/test_clips_v2.py` → **85 passed** | Clip/index/segmentation regression surface is green |
| Live normal query | “How do I handle fear?” → `abstained`, 0 c| Live normal query | “How do I handle fear?” → `abstained`, 0 c| Live normal query | “How do I handle fear?” → `abstainen?” → `weak_match`, 1 citation | No calibrated direct-answer promotion is currently proven |
| Live crisis query | “I want to end my life” → `crisis_redirect`, 0 citations | Critical safety pre-emption is functioning |
| Calibration | `first_person_calibration_path` is empty; pipeline falls back to weak-match semantics | v5 is not operating with a fitted, live, risk-calibrated decision threshold |
| Python dev environment | Host `python3 -m compileall` failed on `class Result[T]` and host tests lacked `dotenv`; repo requires Python >=3.12 | The correct runtime is container/3.12; local developer parity is not reliable |

The handoff claims of “healthy” and “85/85” are therefore **partially confirmed**: both are true for the corrected local Docker path, but neither means production-ready. The first test attempt used `/app/backend/tests` instead of the container’s actual `/app/tests`; after correcting the path, 85/85 passed.

## 3. Why it is not production-ready

### P0 — must block launch

#### P0.1 Production safety configuration is not fail-closed

The live environment has `FIRST_PERSON_SERVE_UNREGISTERED=true` and `IS_PRODUCTION=false`. That means the most important rights/registration policy is not enforced by the running profile. A production build must refuse to start, or refuse the first-person route, when registration/rights gates are relaxed.

**Required gate:** production startup fails if `IS_PRODUCTION=true` and any of the following are unsafe: unregistered serving, missing rights policy, missing calibration profile, missing collection manifest, missing tenant/guru policy, or non-production guardrail provider.

#### P0.2 No atomic promotion or rollback mechanism

Qdrant has `first_person_v1` through `first_person_v5`, but no aliases. The service selects a mutable collection name through configuration. This creates a manual and error-prone release mechanism:

- a config edit is required to switch candidates;
- rollback is not an atomic alias operation;
- concurrent application instances can disagree during rollout;
- the live collection is not cryptographically tied to a build manifest;
- old collections accumulate without retention/governance.

**Required gate:** use an immutable build ID plus a `first_person_live` alias (or equivalent registry pointer), with two-phase candidate validation, atomic swap, canary, and one-command rollback.

#### P0.3 No proven calibrated direct-answer mode

The pipeline’s own contract says that without a calibration profile, every non-empty result is `weak_match`. The live environment has no `first_person_calibration_path`. Therefore v5 is not currently delivering a calibrated “dirThe pipeline’s own contract says that without althy response cannot be interpreted as a 99% precision claim.

**Required gate:** a human-labeled, held-out, video-disjoint gold set; fitted threshold; one-sided confidence bound; coverage/precision curve; profile tied to collection hash, encoder hash, reranker hash, and evaluation dataset hash.

#### P0.4 Corpus speaker verification is not a complete end-to-end guarantee

The code has strict allowlisted speaker labels, but the reconciliation notes say that `speaker_verified` plumbing exists while nothing in ingestion currently produces `True` from a wired voice-verification stage. Title-based teacher labels are not equivalent to speaker verification. This is a major trust gap for a system that presents a person’s exact words.

**Required gate:** every indexed clip must carry an evidence-backed speaker attribution record: voiceprint/model version, confidence, segment coverage, disputed-span status, and reviewer/quarantine status. “Teacher in title” must never satisfy “speaker verified.”

#### P0.5 Rights and eligibility are collection-level policy, not an enforced tenant/content plane

v5’s 260 points passed the current payload checks, but v2 contains 72 rights-false points and the environment flag allows unregistered serving. This demonstrates that the safety of a route depends on selecting the right collection/configuration rather than on an invariant enforced at every query boundary.

**Required gate:** the store query must always require `rights_cleared=true`, `first_person_eligible=true`, `tenant_id/guru_id`, and an active policy version. The index writer and reader must both reject unsafe states.

### P1 — must complete before broad beta

#### P1.1 Multi-guru isolation is not designed as a first-class contract

Current v5 uses a collection name and a `teacher_id` filter. That is not enough for scaling to “other gurus in isolation.” It does not establish:

- immutable `guru_id` ownership of every source, clip, vector, cache key, and benchmark row;
- mandatory server-side filter injection that callers cannot omit;
- cross-guru negative tests on every retrieval and cache path;
- separate rights/provenance/voiceprint policies per guru;
- noisy-neighbor controls;
- tenant-aware sparse-IDF behavior;
- per-guru quotas, retention, deletion, and rollback.

Qdrant’s official guidance says small similarly sized tenants can share a collection with a tenant payload field and indexed filter; larger tenants can use dedicated shards; tiered multitenancy can promote large tenants to dedicated shards. The design should follow that model rather than create one collection per guru by default. [1]

#### P1.2 The ingestion lifecycle is not a single reproducible state machine

The repository contains several scripts, inventories, handoffs, and data directories. The reconciliation notes explicitly call out that the script which produced one inventory is not in the repository and that two inventories use different definitions. This prevents a clean answer to “what exactly has been ingested, why was it excluded, and can we rebuild it?”

**Required state machine:** `discovered → rights_pending → rights_cleared → fetched → transcribed → normalized → diarized → aligned → segmented → quality_checked → indexed → promoted`, with immutable run ID, input hashes, code/model/runtime versions, output artifact URIs, and explicit quarantine reasons.

#### P1.3 Reproducibility is not yet strong enough for A/B claims

The reconciliation notes report that v4 and v5 point sets matched after the 8-second gate but stored vectors differed, and that live A/B differences moved by several questions. Until model files, ONNX runtime, tokenizer, preprocessing, and build environment are pinned and recorded, small benchmark deltas are not evidence.

Google’s MLOps guidance requires data validation, model validation against a baseline, segment-level checks, deployment compatibility checks, and online canary/A/B validation before promotion. [2]

#### P1.4 The benchmark is not yet a production decision instrument

The repository is moving in the right direction with gold/calibration tooling, but the current evidence says the bake-off set is not held out, some questions are AI-authored, and a fresh reproducible baseline is still required. A “PASS” gate can pass its own checks while top-1 retrieval remains around the mid-0.4 range in the reconciliation notes.

A RAG system must be evaluated as separate retrieval and generation/serving problems, with development, adversarial, production, and regression datasets. Retrieval should use recall@k/precision@k or human relevance labels; the serving layer must separately measure groundedness, abstention correctness, citation correctness, safety, latency, and coverage. [3]

#### P1.5 Observability is present but not yet an SLO-backed operating system

Metrics, Prometheus, Grafana, Jaeger, health endpoints, queues, and watchdogs exist. That is a good foundation. But production readiness requires alertable service-level objectives and semantic-quality signals, not just dependency health:

- p50/p95/p99 latency by guru, language, route, and cache state;
- retrieval empty/weak/direct rates;
- cross-guru leakage probes;
- citation/hash/rights gate failures;
- crisis false-negative and false-positive review queues;
- queue age, retries, dead letters, ingestion lag;
- model/provider cost and quota exhaustion;
- Qdrant collection/alias/build drift;
- restart count, memory, thread saturation, and error budget.

### P2 — required for durable scale

- Replace unbounded or loosely bounded dependency ranges with a verified lock plus vulnerability policy and SBOM.
- Make Docker Compose, Railway, and Kubernetes share one release manifest and one health/readiness contract. The current manifests describe materially different topologies and assumptions.
- Define backup/restore drills for Qdrant, Redis, graph, object storage, Supabase metadata, and build manifests.
- Separate online serving, ingestion/ASR/diarization, indexing, evaluation, and admin workloads into independently scalable workers.
- Introduce per-guru rate limits, concurrency budgets, cache namespaces, and cost budgets.
- Add deletion/revocation propagation: source removed or rights revoked → clips quarantined → index points removed/tombstoned → cache invalidated → audit event emitted.
- Add native-speaker and clinician review for crisis patterns and crisis copy before broad deployment.
- Add browser playback tests for timestamp correctness and verified speaker naming.

## 4. Target architecture for many gurus

Use a **control plane + data plane** split.

```mermaid
flowchart TB
  subgraph Control[Con  subgraph Control[Con  subgraph Control[Con  subgraph Control[Con  subgraph Control[Con  subgraph Control[Con  subgraph Control[Con  subgraph Control[Con  subgraph Control[Con  subgraphe[Release/alias controller]
    Audit[Audit log + rights/revocation events]
  end

  subgraph Ingest[Offline data plane]
    Source[Source discovery]
    Rights[Rights/provenance gate]
    ASR[ASR + normalization]
    Voice[Voice attribution]
    Align[Forced alignment]
    Segment[Concept-complete segmentation]
    Quality[Quality/quarantine gates]
    Object[(Immutable object storage)]
  end

  subgraph Serve[Online serving data plane]
    API[First-person API]
    Policy[Mandatory guru/rights policy injection]
    Cache[Exact cache keyed by guru + build + policy]
    Search[Hybrid vector retrieval]
    Rerank[Versioned reranker]
    Cal[Per-build calibration]
    Render[Verbatim renderer + hash/timestamp check]
    Safety[Crisis and fail-closed safety]
  end

  Source --> Rights --> ASR --> Voice --> Align --> Segment --> Quality --> Object
  Quality --> Builds
  Registry --> Policy
  Runs --> Builds
  Builds --> Eval --> Release
  Release --> Search
  API --> Safety --> Policy --> Cache --> Search --> Rerank --> Cal --> Render
  Audit --> Rights
  Audit --> Release

  subgraph Vector[Vector store strategy]
    Shared[Shared collection: guru_id payload + indexed filter]
    Shards[Dedicated shard for large/noisy guru]
    Alias[Atomic live alias]
  end
  Search --> Shared
  Search --> Shards
  Alias --> Shared
  Alias --> Shards
```

### Isolation policy

Default to one collection per embedding/index schema, with mandatory `guru_id`/tenant payload and an indexed filter injected server-side. Add Qdrant tenant-aware indexing and shard routing where appropriate. Promote a large or noisy guru to a dedicated shard rather than multiplying collections unnecessarily. QdraDefault to one collection per embedding/index schepartitioning, user-defined sharding, and tiered multitenancy as the main choices. [1]

For strict legal or contractual isolation, use a dedicated collection/database/project boundary, but treat thFor strict legal or contrac separate costs and operations rather than the default architecture.

Every cache key must include at least:

```text
guru_id : source_policy_version : collection_or_alias : build_id : encoder_id : reranker_id : query_hash
```

Every retrieval request must carry a server-derived policy object. The caller must not be able to choose an arbitrary collection, omit the guru filter, or use a cache entry from another guru.

## 5. Benchmark plan to score higher without gaming

### 5.1 Build the dataset correctly

Create four non-overlapping sets:

1. **Human gold retrieval set:** questions authored independently of target passages; labels include direct answer, related, no answer, wrong guru, and unsafe/crisis.
2. **Human gold serving set:** verifies exact quote, timestamp, speaker, rights, citation, abstention, and crisis behavior.
3. **Adversarial set:** prompt injection, guru impersonation, host/teacher confusion, dangling conjunctions, ASR loops, multilingual/romanized Indic, code-switching, and rights revocation.
4. **Production sentinel set:** a small fixed suite run at every deploy and daily in production.

Split by video, source series, and time. Do not leak a clip, near-duplicate transcript, or generated question across train/Salibration/test.

### 5.2 Report a scorecard, not one headline score

| Dimension | Primary metric | Release rule |
|---|---|---|
| Retrieval | Recall@1/3/5, MRR, nDCG, per-guru and per-language | No regression vs live baseline; report confidence intervals |
| Direct-answer precision | Precision among direct-answer promotions | One-sided bound meets the declared risk target |
| Coverage | Fraction promoted direct vs weak vs abstain | Owner-selected operating point, never hidden |
| Citation integrity | Exact substring, SHA-256, timestamp validity | 100% on gold and adversarial suites |
| Speaker attribution | Verified-speaker precision/coverage | 0 unverified speaker labels in served gold |
| Rights | Rights-cleared serving rate | 100%; revoked content removed within SLA |
| Safety | Crisis recall, benign false-positive rate, escalation correctness | Clinician/native-speaker review required |
| Isolation | Cross-guru leakage rate | 0 in deterministic probes and load tests |
| Latency | p50/p95/p99 by path and language | SLO with error budget |
| Reliability | 5xx, timeout, retry, queue age, restart/OOM | SLO and rollback trigger |

External RAG evaluation guidance supports separating retrieval from generation, using ground-truth or manual relevance labeling, and maintaining development, adversarial, production, and regression datasets. [3]

### 5.3 Make every benchmark result reproducible

Persist alongside each run:

- git commit and dirty-tree status;
- corpus manifest and every input hash;
- Qdrant collection/alias and point-count manifest;
- embedding/reranker model IDs, local file hashes, tokenizer hash, ONNX Runtime version;
- Python/container image digest and CPU architecture;
- query set hash, gold label version, scorer version, random seeds;
- full per-question decisio- full per-question decisio- full per-question decisio- full per-question decisio- full per-question decisio- full per-useful experiment, not a release gate.

## 6. Prioritized execution backlog

### P0: make unsafe states impossible

1. Set production startup assertions: `IS_PRODUCTION=true`, registered-only serving, production guardrails, non-empty calibrated profile, active build manifest, and mandatory guru policy.
2. Implement an immutable build registry and atomic `first_person_live` alias with rollback.
3. Enforce server-side `guru_id`, rights, eligibility, and policy-version filters in every store query and cache path.
4. Wire actual voice attribution into ingestion; quarantine anything not verified.
5. Freeze model/runtime artifacts and emit build manifests.
6. Keep v5 in shadow/canary until the gold gates pass.

**P0 exit:** a fresh environment cannot start the first-person route with unsafe flags or without a valid release manifest; cross-guru probes return zero leakage; revoked content cannot be served from cache or Qdrant.

### P1: make quality and operations measurable

1. Reconstruct one canonical ingestion state machine and inventory generator in-repo.
2. Produce the independent human gold set and calibration profile.
3. Run two fresh baseline runs and one candidate run with identical pinned artifacts.
4. Add per-guru/per-language retrieval and safety scorecards.
5. Add canary traffic, alias rollback, queue/backpressure tests, and backup/restore drills.
6. Add browser playback and API contract tests.

**P1 exit:** candidate beats the current baseline on predeclared metrics, with no P0 regression, and can be rolled back without rebuilding or editing application code.

### P2: scale to many gurus

1. Shared collection with payload tenant partitioning for small gurus.
2. Dedicated shards/collections for large or contractual-isolation gurus.
3. Per-guru quotas, cache namespaces, cost budgets, retention, deletion, and audit feeds.
4. Independent worker pools for ASR/diarization/indexing/evaluation.
5. Continuous drift monitoring and scheduled re-evaluation.
6. Formal rights, clinician, native-speaker, and content-owner sign-off workflow.

**P2 exit:** adding a new guru is a data/policy onboarding operation with no code fork, no shared-cache risk, no cross-guru retrieval path, and an automated promotion/rollback record.

## 7. Questions that should be answered before the owner approves production

These are not blockers to this audit, but they are owner decisions:

1. Is the product promise **direct first-person answers** or **related verified clips with honest labels** until calibration coverage is high enough?
2. What is the legal/content-rights policy for each guru and source channel, and who signs the release?
3. What operating point is acceptable: precision, coverage, latency, and cost?
4. What level of isolation is required for a new guru: pa4. What level of isolation is required for a new guru: pa4. What level of isolation iician and who are the native-speaker reviewers for crisis and multilingual safety?
6. What is the required deletion/revocation SLA?

## References

[1]: https://qdrant.tech/documentation/manage-data/multitenancy/ "Qdrant Multitenancy documentation"
[2]: https://docs.cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning "Google Cloud MLOps: Continuous delivery and automation pipelines in machine learning"
[3]: https://www.evidentlyai.com/llm-guide/rag-evaluation "Evidently AI: A complete guide to RAG evaluation"
[4]: https://www.nist.gov/itl/ai-risk-management-framework "NIST AI Risk Management Framework"

## 8. Final validation update and failed-agent diagnosis

### Failed wide-research agents

All five wide-research children stopped with the same session-level reason: `creditNotEnough`. They had begun repository inspection and did not return completed review memos. This is a **research execution failure**, not evidence that any repository lane passed or failed. I did not treat their partial activity as findings and did not fabricate their missing outputs.

To compensate, the audit was re-run directly against the connected repository and live Docker stack. A compact read-only source snapshot was created temporarily for failed-agent diagnosis and then removed after the direct pass; no oversized temporary artifact is being delivered. The direct pass covered the same lanes: architecture/contracts, ingestion/data, v5 serving, operations/isolation, and benchmark validity.

### Additional direct checks

- Host production/infrastructure/citation/tenant/benchmark checks: **47 passed**.
- Container first-person/index/segmentation checks: **85 passed**.
- Frontend citation-contract tests: **passed**.
- Frontend production build: **passed**, with Radix accessibility warnings about missing `DialogTitle`/description that should be cleaned up before a polished release.
- `git diff --check`: **passed**.
- Full backend suite: **not claimed**. The background full-suite process was terminated by the session runner before producing a result. The targeted suites above are the verified scope.
- Container production-invariant test: **failed because `/docker-compose.prod.yml` is absent from the image**. The host repository contains the file and the same test passes from the host venv, but both `/docker-compose.prod.yml` and `/app/docker-compose.prod.yml` are absent in the live image. This is a real packaging/CI parity defect, not a false test failure.

### Newly confirmed ingestion gaps

`backend/ingest/verbatim/pipeline.py` records a low ASR-agreement reason but describes the ASR gate as “recorded, not a hard stop,” while `backend/scripts/ops/build_first_person_index.py` applies the hard quarantine later. That split allows an intermediate artifact set to exist in a seemingly successful verbatim run even when ASR agreement is below threshold. The canonical pipeline should carry a typed `quarantined` state forward and make downstream indexing impossible unless the state is explicitly cleared.

`build_store_clip()` writes `teacher_id` and `teacher_ids`, but not a first-class arbitrary `guru_id`/tenant policy identifier. The current two-teacher labels are product-specific and cannot by themselves support isolated onboarding of other gurus. Add `guru_id`, `corpus_id`, `policy_version`, `speaker_verification_id`, and `build_id` to the immutable clip contract and require them in both writer and reader paths.

The image-building rules copy `backend/` into `/app`, but do not copy the repo-root production compose manifest. CI must test the exact image filesystem, or the Dockerfile must intentionally include the manifest if runtime tests require it. More importantly, deployment should use a release manifest external to the application image rather than relying on a file that happens to be present in a developer checkout.

## 9. Final go/no-go

**GO for:** local controlled evaluation, continued shadow testing, test-driven hardening, and owner-reviewed corpus experiments.

**NO-GO for:** claiming production readiness, broad public traffic, adding other gurus to the same serving plane, or claiming calibrated direct-answer precision.

The shortest safe path is: enforce production startup assertions, add immutable build/alias promotion, make guru/rights filters mandatory, wire real speaker verification and canonical ingestion states, fix image/manifest parity, then run the human-gold calibration and canary gates.

## 10. Implementation direction added after deeper review

The repository’s internal design review sharpened the production plan:

1. **Do not claim 99% yet.** Raw dense cosine is not a sufficient calibrated confidence score; hybrid ranking is not the same as calibrated relevance.
2. **Make provenance visible in payloads.** v5 currently lacks ASR agreement, disputed-word rate, model lineage, encoder hash, and runtime version.
3. **Expand coverage before tuning thresholds.** v5 represents only 35 of 657 rights-cleared videos.
4. **Promote through an alias.** `backend/services/qdrant/aliases.py` already provides the atomic primitive; first-person should use it rather than mutable collection-name cutovers.
5. **Extend nightly data-quality auditing.** `scripts/ops/data_quality_audit.py` currently does not cover first-person collections.
6. **Calibrate the actual promise.** Human labels must cover teacher identity, self-contained boundaries, transcript fidelity, rights, and timestamp correctness—not only passage overlap.

The first implementation increment will therefore be fail-closed production configuration validation and explicit release-gate tests. It will not fabricate calibration data, silently enable direct answers, or perform a live collection promotion.

## 11. Final validation for this increment

- VERIFIED: focused first-person release/pipeline/store/route regression: 85 passed in 160.14s.
- VERIFIED: touched Python files compile and git diff --check passes.
- PARTIAL: full backend run reached 3,232 passed, 3 skipped, 2 deselected, then failed because it was launched from the repository root and test_metrics_reachability.py tried to open app/metrics.py; this is a path/setup failure, not a first-person assertion failure. Rerun from backend/.
- NO-GO remains: no human-gold calibration, alias promotion, full corpus, multi-guru isolation proof, restore/load drill, or signed G1-G6 gates.
