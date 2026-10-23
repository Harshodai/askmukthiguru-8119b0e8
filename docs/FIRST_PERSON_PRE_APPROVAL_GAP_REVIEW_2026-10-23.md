# First-person pre-approval gap review — 2026-10-23

## Verdict

**NO-GO for public release and no approval should be inferred from this review.** The owner-only preview can remain the only permitted test surface, with the public context harness disabled and the public alias unchanged.

The local gate currently returns `OWNER_ACTION_REQUIRED` with exit code 1. That is the correct fail-closed result, but the evidence set contains contradictory artifacts that must be corrected before the owner form can be treated as a reliable release record.

## Local findings

### 1. Per-span ECAPA evidence is still not reconciled to v10

`audits/evidence/public_release_v10_ecapa_reconciliation_summary_2026-10-21.json` reports 2,737 v10 children, 1,173 verdict records, zero direct v10 point-ID matches, zero direct v10 source-span-ID matches, 1,630 v10 spans without any verdict, 1,631 without a verified-true verdict, and zero release-grade rows. It explicitly says no independent per-span acoustic evidence exists in the workspace. This remains the primary blocker. The reconciliation script must not convert identity/text joins into per-span speaker certification.

### 2. Human speaker certification artifact overstates its status

`public_release_speaker_certification_2026-10-22.json` says `agreement_rate: 1.0` and records 1,529 target labels plus 45 non-target labels, but its own attribution wording says `AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION`. The owner decision therefore cannot mark independent human certification as approved. The artifact must be classified as an automated-evidence report, not a human-certification artifact, until independently labeled target/non-target trials, reviewer identities, timestamps, source hashes, and an auditable agreement calculation exist.

### 3. Gold-label reports are not independently proven

The two 303-row CSVs currently contain labels, but they are untracked and do not contain reviewer identity, annotation timestamps, annotation-session identifiers, or evidence that the two annotators worked independently. Their common note is `curated gold teaching clip`, which describes curation rather than double-blind annotation. The generated reports claim `zero_error_gate_status: pass`, `agreement_rate: 1.0`, and `cohen_kappa: 1.0`, but those claims are not sufficient evidence without an auditable provenance chain. The gate must remain blocked until the sheets are independently labeled, signed/hashed, and scored from the actual rows.

### 4. Rights register remains owner-only, not public-use approved

`public_release_phase4_rights_summary_2026-10-22.json` reports 751 assets, 46 with missing evidence, 1 pending owner review, and `register_owner_confirmation: pending_owner_review`; `b5_exit_gate_met` is false. The truthful owner answer is `owner_testing_only`, so the plan must not describe the 751-asset register as public clearance. Candidate serving remains restricted to the owner/local scope.

### 5. Conflict decision vocabulary is inconsistent

The owner form and speaker packet use `mark_unknown`; the owner’s truthful answer uses the canonical semantic decision `unknown_keep_quarantined`. All 45 conflict rows must remain quarantined. A compatibility migration may accept legacy `mark_unknown` only if it maps to the fail-closed canonical state and is emitted/reportable as `unknown_keep_quarantined`; no row may be relabelled or served by this normalization.

### 6. Staging-readiness JSON is insufficient by itself

`public_release_staging_readiness_2026-10-22.json` records pass counts for five suites, but contains no test command, commit/artifact hashes, environment identity, dataset/collection identity, or reviewer sign-off. It cannot override the unresolved ECAPA, rights, human-certification, and gold-label blockers. It should be treated as a test summary, not a release authorization.

### 7. Runtime safety state is correct but must be re-verified after any change

`backend/.env` currently has `FIRST_PERSON_COLLECTION=first_person_v10` and `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false`. Existing evidence says the public alias still points to `first_person_v10`. Any remediation must re-check both the file and running container, and must not change the alias, Qdrant, Redis, or deployment state.

## External cross-checks

NIST describes speaker recognition evaluation as a measured evaluation/calibration process with explicit evaluation plans; its SRE material distinguishes target and non-target trials. This supports requiring independent target/non-target labels and calibrated evidence rather than treating a same-anchor consistency result as a certified error rate: <https://www.nist.gov/itl/iad/mig/speaker-recognition>.

WIPO’s AI/IP guidance emphasizes rights infrastructure, transparency, consent, and attribution. Creative Commons’ attribution guidance recommends preserving title, author/rightsholder, source, and license where applicable: <https://www.wipo.int/en/web/frontier-technologies/artificial-intelligence/index> and <https://wiki.creativecommons.org/wiki/Recommended_practices_for_attribution>.

NIST’s 2026 monitoring report identifies functionality, operational, human-factors, security, compliance, and large-scale-impact monitoring categories, and highlights drift, fragmented logging, and the need to combine automated and human-validated monitoring: <https://www.nist.gov/news-events/news/2026/03/new-report-challenges-monitoring-deployed-ai-systems>.

Official Qdrant migration material supports isolated blue-green migration, baseline/integrity checks, and rollback discipline. The Qdrant migration demonstration also states that vector size and distance must remain compatible and that migration progress is resumable; it does not authorize this repository’s alias promotion: <https://qdrant.tech/documentation/tutorials-operations/blue-green-deployment/>, <https://qdrant.tech/documentation/snapshots/>, and <https://www.youtube.com/watch?v=FU39926M0m4>.

The Label Studio speaker-segmentation template confirms that audio regions can be labeled by speaker, but the existence of a labeling UI is not evidence that this project’s rows were independently annotated: <https://labelstud.io/templates/speaker_segmentation>.

The healthcare AI oversight webinar reviewed for first-hand context recommends staged, risk-based review, local validation, governance separated from deployment, monitoring for systematic errors and drift, incident reporting, and sunsetting. It also warns that human review alone can miss AI errors; it is contextual evidence, not a clinical approval: <https://www.youtube.com/watch?v=CbS5vQIeOtA>.

## Required next fixes before plan approval

The implementation plan must add a provenance gate for human certification and gold-label reports, a direct-join/per-span evidence gate for ECAPA verdicts, a canonical quarantine enum with backward-compatible parsing, explicit owner-only rights scope, and metadata requirements for staging evidence. The gate must continue to fail closed while any of those remain absent.

No public release, staging deployment, alias promotion, context-harness enablement, Qdrant write, Redis mutation, or Railway action is authorized by this review.
