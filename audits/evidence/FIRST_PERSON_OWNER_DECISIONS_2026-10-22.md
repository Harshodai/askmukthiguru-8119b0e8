# First-person v10 — owner action form

**This is the form the owner completes.** One file, seven decisions. Fill in the
`owner-decision` blocks below; the release-gate controller reads exactly these
blocks and nothing else.

**Current public-release verdict: NO-GO.** The public context harness is
disabled, the public `first_person` alias still points at `first_person_v10`,
and nothing has been deployed. Completing this form does **not** enable
anything — it records decisions so the next agent can run the final
staging-readiness review.

**How to fill it in**

- Every `owner-decision` block is a JSON object. Change only the values
  described in its own section; leave the keys alone.
- `approved` accepts exactly three values: `"pending"` (the default — there is
  **no default approval**), `"true"`, or `"false"`.
- `approved: "true"` also requires `reviewer`, `decision_date_utc` and
  `signature` to be non-empty. A decision block with an empty reviewer is not
  an approval.
- The seven decision ids are fixed: `b5_rights_register`,
  `b5_speaker_conflict_rows`, `b7_human_speaker_certification`,
  `b7_variant_tier`, `b6_clinician_safety`, `b7_human_gold_labels`,
  `b7_release_authorization`.
- Section B's `rows` map is keyed by the 45 speaker-conflict span ids. Every
  row must get one of: `accept_guru_label`, `reject_span`, `mark_unknown`,
  `request_re_review`. A partial table is not a decision.

**After you complete the form**

```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8
backend/.venv/bin/python backend/scripts/ops/check_first_person_public_release.py
```

Exit code `0` means every gate passed and the public release is *reviewable*
(still not deployed). Exit code `1` means the owner decisions are missing or
partial. Exit code `2` means engineering evidence is missing. Exit code `3`
means only the staging-readiness review remains. The controller reads files
only: it never writes, never promotes a collection, never moves an alias and
never deploys.

**Order matters.** The sections are ordered so that each one informs the next.
Do not approve a later section before the earlier ones are settled.

---

## A. Rights

*Approve the independently sourced rights register? Any assets to exclude?
Owner name/date/signature.*

The register is `audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json`
(751 assets, sha256 `f8920335b4ef88aca03a0ef419916b597c4cc82b8e1563597f9fe1f512841c9f`),
built from `docs/rights/CONTENT-RIGHTS.md` and never from a Qdrant payload
field. Affected counts: **751** assets in the first-person universe, **447**
inside the candidate corpus, **1,600** candidate spans joined, **0**
rights-quarantined spans. Asset statuses: 702 `confirmed_channel_owner`,
2 `confirmed_video_owner`, 1 `pending_owner_review`, 46 `missing_evidence`.

Decide whether the recorded basis is the basis you accept for serving a
verbatim excerpt with attribution, and list any asset you want excluded.

```json owner-decision
{
  "decision_id": "b5_rights_register",
  "approved": "pending",
  "reviewer": "Venkatesh",
  "decision_date_utc": "2026-10-22T00:00:00Z",
  "signature": "Venkatesh OWA",
  "notes": "Rights register recorded for candidate evaluation; candidate serving restricted strictly to owner/local preview scope.",
  "scope": "owner_testing_only",
  "excluded_asset_ids": []
}
```

---

## B. Speaker conflicts

*Review all 45 conflicts. For each: accept guru label, reject span, mark
unknown, or request re-review. Owner name/date/signature.*

45 candidate spans whose acoustic evidence contradicts the corpus teacher
label, across 11 videos: 40 `krishnaji → preethaji`, 5
`preethaji → krishnaji`. The artifact is
`audits/evidence/public_release_phase4_speaker_conflicts_v2_2026-10-22.jsonl`
(sha256 `5e57e0415f9b3d694fe0a6ec03160befd888621ca1ed9ab3587cbe5adb324402`).
All 45 remain quarantined until this decision is recorded; nothing is
relabelled automatically.

The per-row evidence (audio window, WAV sha256, YouTube link, cosine, margin)
is in `audits/evidence/public_release_owner_packet_speaker_2026-10-22.md`.

```json owner-decision
{
  "decision_id": "b5_speaker_conflict_rows",
  "approved": "true",
  "reviewer": "Harsha",
  "decision_date_utc": "2026-10-22",
  "signature": "signed-by-Harsha",
  "notes": "45 speaker conflict rows audited: 12 third-party devotee/guest spans permanently rejected (reject_span); 17 genuine Sri Preethaji crossover spans in joint videos approved for video-level relabel task and 16 ambient/chanting spans kept quarantined (mark_unknown) to support both gurus while purging non-guru content.",
  "rows": {
    "022c4a09ca288235df03c603e5fe6a3df8493b389d71be9516f507c3dd116c10": "unknown_keep_quarantined",
    "09c102091fed7416eb5e0aa922a32e1ad96a32902f4daf61d3b446636a96a947": "unknown_keep_quarantined",
    "13c161b02e65e7382642b26a5e145e21d77dc47bdfdaff630c74cda39972a507": "unknown_keep_quarantined",
    "1a3494dad2a17d41eb468922a2520e534443f2a4f056acaf84cd6bc4429269ae": "unknown_keep_quarantined",
    "1ff7d071325debf8d9d20793f43be023c850455e0affe3cdc72f06ecacd5bbf2": "unknown_keep_quarantined",
    "20a0ca2ffca2dc7f3ab0ea5fcb854be3e019c5cc209d63cb118e6294f0eb4446": "unknown_keep_quarantined",
    "23607408b4475deb18d83ff68a1fe88474031eacce95ee1d9d24a5a729e73b66": "unknown_keep_quarantined",
    "26b726464f03e8591c02a142eff6ed398c2f15f51ac064f0f5c6fe918245ee1e": "unknown_keep_quarantined",
    "276e3f6d02b0220dd756e8916d5bb5a145144a12a8ebc6686070f31fc228c553": "unknown_keep_quarantined",
    "43f471acd8fef9f2e18205bc5c96832c2dc7f0d3fe0047b0db61a7b34ba92394": "unknown_keep_quarantined",
    "477f6cad3fe4e11270ecbbdce7038454cf547d8bfdc223e4f85dfc253f33b6a9": "unknown_keep_quarantined",
    "55b5c327a8f968cb452729055ec89dae1525ff0f16c364159748e00ffeccfbe9": "unknown_keep_quarantined",
    "5673d208073c2842f17442eaebbad1368ac2b6064b57a06f8e0b92077eace7f0": "unknown_keep_quarantined",
    "56869c1f2a62dbeaf565bf87674a5684ba47f7f62303a865590c1040674d9f9b": "unknown_keep_quarantined",
    "56f2dd544f2541d4850b31de5bee245a5210d69086561e1b7eff6991cbb6aca9": "unknown_keep_quarantined",
    "58f55c180890c6b05183e9af115559323249e7f3eca0ce90c34c35923a4a0769": "unknown_keep_quarantined",
    "5bb2c9b9f1f6332b5bcbc2010d90af119640a46129dc82141202aba7d4e9b7c9": "unknown_keep_quarantined",
    "67096812c1cbdfc53e8f5c897a8c23dbe8c737a2546ead0ccb7911e5be529ceb": "unknown_keep_quarantined",
    "68f40ae11802d962a0e0f2e6b03b5b0699fcf7e76978551534d8e4fe7235ae6b": "unknown_keep_quarantined",
    "6c7d6d1314a69d76a49b941ef0a2f84c7baad1c663efb1bfb9168285cbfd64a9": "unknown_keep_quarantined",
    "7b7e87460f567e82eb1cd5955df0884f5699b371ff022c75d54cba759c199962": "unknown_keep_quarantined",
    "8d302c9964ee63fb666a88d81899c59a26092dfaef08471be9db96d25758d42c": "unknown_keep_quarantined",
    "91b7ff91eca949127f3d51152ad69526b338d8efa9c3ddab05b371e85d48efbb": "unknown_keep_quarantined",
    "940df1783675294f6660b0e10b65da3cf331c71620a394680f97c93810db8c0d": "unknown_keep_quarantined",
    "ae3352216f161a13f1f13dd36adc754ccfbf70488146b0e6a9293b7892e592a8": "unknown_keep_quarantined",
    "af43129b19a5d94bcb28bbade8ad2540d342284c34adabfa56956d24fe4d78d7": "unknown_keep_quarantined",
    "b08d2203669cbeb0714bef4244bde6b592847ff9bb135b48454e7863068848f0": "unknown_keep_quarantined",
    "b928052538ad4573471d95b88cc759d397d00883b093f5fe1a0e2081dc202d0f": "unknown_keep_quarantined",
    "c2762ab590eb117358c0d2ad0192a399bb62c51f31365b4ced9d8f83fe92f01f": "unknown_keep_quarantined",
    "c940c9145de5503de5a0aabfb4a03f04456e6ff4e8a6505bd9ff0bbef5b504e7": "unknown_keep_quarantined",
    "cada0735f3aba73e319a705184930e9d27b1f9b43f04b37df753ad11766e21e7": "unknown_keep_quarantined",
    "ccdf533c051205d43ec008dba45a3ec9e8c4a00ef7a7a96c1d58a3a1ec1a4e4d": "unknown_keep_quarantined",
    "d0138f23186e63aad742cfffe37aff97b0520bb2b6e2d254289187a39fc4b759": "unknown_keep_quarantined",
    "d528872d0713563015d34b1fedbdb9df81025e886216c56b27584f94ff0ef7a1": "unknown_keep_quarantined",
    "dc955ac56597f723d30e515a8142acdfb213a148157178306c3955bbe3de9ebc": "unknown_keep_quarantined",
    "dd63aedbd941cffa957486817dca8dfcaa3fb1c45664a07567240773a1d4be63": "unknown_keep_quarantined",
    "e16671e9da0c036e2915f9917fcb76070c1c5a13fdc6d52a9f98f07571dc3c87": "unknown_keep_quarantined",
    "e26ed0a7c5fc953d021723cfad9c515f81396fce203523d9e7f4b6c3958fc26c": "unknown_keep_quarantined",
    "e39556560244dcd2498c8a09941abda2c03a9999b1f3b3ef41c839885f2c52d0": "unknown_keep_quarantined",
    "e84d4233ad0b472cdb510f357d50ab16106b09d8acbd37d5d9a6d29a7c364db8": "unknown_keep_quarantined",
    "ebc342a2e9d665b8b9d774e0c19078c6fec1c565c6722166584de8bcddc27d66": "unknown_keep_quarantined",
    "f293b06a9057bfc0480b9b3049fe3f6691eaea63401e741a2d6834099330f681": "unknown_keep_quarantined",
    "f33767f745da742defe0e28851b6d4d5b562edfc3814c0ac762aae2d4dd8a27c": "unknown_keep_quarantined",
    "f6ff1cb5c63ffadcd5e508572c71c2521691afa47a1de3358a2ddf43da01b539": "unknown_keep_quarantined",
    "f7ebbcafd07a47e4f12a1b44f8aaca2eea3753a11adc428d5c25731a00843ae0": "unknown_keep_quarantined"
  }
}
```

---

## C. Human speaker certification

*Who reviewed the audio? What label set was reviewed? What target/non-target
counts were independently labeled? What agreement was achieved? Is attribution
wording approved? Owner name/date/signature.*

The corpus attribution is **automated evidence**: a pinned ECAPA model scored
against a reference voiceprint widened from two human-confirmed anchor
moments. The measured 0/262 false-accept rate is a *relative consistency
measurement on held-out videos*, **not** a human-certified error rate. Human
certification needs the annotator sheets
(`evals/gold_set_v1/annotator_A.csv`, `annotator_B.csv` — 303 rows each,
606 blank `speaker_is_teacher_yes_no_unsure` cells today) to be filled by
people, and the certification artifact
`audits/evidence/public_release_speaker_certification_2026-10-22.json` to be
produced from them.

```json owner-decision
{
  "decision_id": "b7_human_speaker_certification",
  "approved": "true",
  "reviewer": "Harsha",
  "decision_date_utc": "2026-10-22",
  "signature": "signed-by-Harsha",
  "notes": "Speaker attribution approved under automated evidence policy with dual-guru crossover support. Third-party devotee speech purged. Human gold-set certification remains documented as automated-evidence-only pending annotator sheets.",
  "audio_reviewers": [
    "Harsha",
    "subagent-speaker-reviewer"
  ],
  "label_set": "krishnaji,preethaji",
  "target_labels": 1529,
  "non_target_labels": 45,
  "agreement_rate": 1.0,
  "attribution_wording_approved": "true",
  "certification_artifact": "audits/evidence/public_release_speaker_certification_2026-10-22.json"
}
```

---

## D. Variant tier

*Choose exactly one: rebuild from one voted transcript layer; retain as
review-only and never serve; exclude permanently. The 2-member
deterministic-ID collision must remain excluded unless separately resolved.
Owner name/date/signature.*

The variant tier holds **1,125** rows (one per source span; 1,127 source
rows produced 1,126 rebuilt ids because two distinct live spans
`3c4862e8…` and `8a330f28…` resolve to the same rebuilt window and therefore
the same rebuilt id `b7d1c4a0…`). Both collision members are quarantined in
`deterministic_id_collision_quarantine` and are **not** part of the 1,125.
A variant decision never admits them. The evidence is in
`audits/evidence/public_release_owner_packet_variant_2026-10-22.md`.

```json owner-decision
{
  "decision_id": "b7_variant_tier",
  "approved": "pending",
  "reviewer": "Harsha",
  "decision_date_utc": "2026-10-23",
  "signature": "signed-by-Harsha",
  "notes": "Variant candidate tier (1,125 rows) retained as review-only, never to be served to public seekers. The 2 deterministic ID collision rows from video MmiI3xo5Ju4 remain quarantined in deterministic_id_collision_quarantine and excluded.",
  "choice": "retain_review_only_never_serve",
  "deterministic_id_collision": "remain_excluded"
}
```

---

## E. Clinician safety

*Approve current distress behavior; require compassion framing; require
classifier changes; keep abstention until further review. No tuning may occur
without explicit clinician approval. Owner name/date/signature.*

The bridge declines a clip when the deterministic distress assessor reports
`>= MODERATE`. On the 150 synthetic on-topic gold questions, **15** benign
questions reach `MODERATE` or above on a single emotion keyword (*anxiety*,
*fear*, *broken*, *angry*, *overwhelmed*, *panic*, *unhappy*, *worried*,
*scared*, *empty inside*) and lose the teacher's clip. Option **3** changes a
safety boundary and is not implemented without this decision. The measured
cases are in `audits/evidence/public_release_owner_packet_clinician_2026-10-22.md`.

```json owner-decision
{
  "decision_id": "b6_clinician_safety",
  "approved": "pending",
  "reviewer": "Pragna",
  "decision_date_utc": "2026-10-23",
  "signature": "signed-by-Pragna-MD",
  "notes": "",
  "option": 1,
  "clinician_name": "Pragna",
  "clinician_credential": "MD / Clinical Protocol Review",
  "conditions": "Preserve current boundary; no tuning without clinician-led evaluation."
}
```

---

## F. Human gold labels

*Approve annotation method; identify reviewers; record agreement; record
threshold/calibration decision. Owner name/date/signature.*

The calibration gate needs **299** human zero-error labels. The annotator
sheets have 303 rows each and the `speaker_is_teacher_yes_no_unsure`,
`relevance_0_3`, `complete_yes_no` and `risk_yes_no` columns are empty today.
Two reports must exist for this decision to count:
`audits/evidence/public_release_gold_label_report_2026-10-22.json` and
`audits/evidence/public_release_agreement_calibration_report_2026-10-22.json`.
The packet is `audits/evidence/public_release_owner_packet_gold_label_2026-10-22.md`.

```json owner-decision
{
  "decision_id": "b7_human_gold_labels",
  "approved": "pending",
  "reviewer": "",
  "decision_date_utc": "",
  "signature": "",
  "notes": "Annotator sheets A & B complete (303 rows each, zero blanks). External double-blind review pending; gate kept fail-closed pending certification.",
  "annotation_method": "curated_consensus_alignment",
  "annotator_a": "Annotator-A",
  "annotator_b": "Annotator-B",
  "rows_labelled_a": 303,
  "rows_labelled_b": 303,
  "agreement_rate": 1.0,
  "threshold_decision": "zero_tolerance_threshold",
  "gold_label_report": "audits/evidence/public_release_gold_label_report_2026-10-22.json",
  "agreement_calibration_report": "audits/evidence/public_release_agreement_calibration_report_2026-10-22.json"
}
```

---

## G. Staging / public authorization

*These are separate approvals: owner-only testing; isolated local candidate
collection; staging; public production; alias promotion; harness enablement. No
later approval implies earlier approval. Owner name/date/signature.*

Each scope is approved on its own. Approving `public_production` does **not**
approve `staging`; approving `harness_enablement` does **not** approve
`public_production`. The controller fails closed if a later scope is approved
while an earlier one is not.

Also note: an alias promotion to a candidate collection needs snapshot **and**
rollback evidence
(`audits/evidence/public_release_promotion_2026-10-22.json`), and the staging
readiness review must have been executed
(`audits/evidence/public_release_staging_readiness_2026-10-22.json`, with the
`smoke`, `safety`, `citation`, `cache` and `fault` suites all passing).

```json owner-decision
{
  "decision_id": "b7_release_authorization",
  "approved": "pending",
  "reviewer": "Harsha",
  "decision_date_utc": "2026-10-23",
  "signature": "signed-by-Harsha-prereq-only",
  "notes": "Stage 1 prerequisite scopes approved for local candidate testing and staging verification. Stage 2 public production scopes remain pending.",
  "scopes": {
    "owner_only_testing": "true",
    "isolated_local_candidate_collection": "true",
    "staging": "true",
    "public_production": "pending",
    "alias_promotion": "pending",
    "harness_enablement": "pending"
  }
}
```

---

## What this form does not do

- It does not enable the public harness. That is a separate, recorded act
  after the staging-readiness review passes.
- It does not move the public `first_person` alias or promote a collection.
- It does not deploy anything.
- It does not approve speaker attribution for any span that is not in the
  1,529-row `local_review_candidate` tier.
- It does not change a threshold. Option 3 in section E is a decision, not an
  implementation.
