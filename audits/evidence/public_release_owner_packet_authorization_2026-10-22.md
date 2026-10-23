# Owner decision packet — final staging / public-release authorization

**This is a question, not an approval.** Nothing here authorizes anything by being written down. Each scope below is approved on its own, and **no later approval implies an earlier one**.

## 1. What is being decided

Six independent authorization scopes, in dependency order. Each one is a separate act with its own evidence:

| # | Scope | What it authorizes | What it does **not** authorize |
|---|---|---|---|
| 1 | `owner_only_testing` | The owner-only, local, file-backed preview of the `local_review_candidate` tier (already available; no public surface). | Any public traffic. |
| 2 | `isolated_local_candidate_collection` | Building an **isolated local** candidate collection from the approved tier, with a snapshot and a rollback path. | Promoting it, aliasing it, or serving it publicly. |
| 3 | `staging` | Running the staging-readiness review: staging smoke, safety, citation, cache and fault suites against the candidate. | Public production. |
| 4 | `public_production` | Serving the approved corpus to the public surface. | Alias promotion or harness enablement on their own. |
| 5 | `alias_promotion` | Moving the public `first_person` alias to the approved candidate collection. | Enabling the context harness. |
| 6 | `harness_enablement` | Turning on `FIRST_PERSON_CONTEXT_HARNESS_ENABLED`. | Any of the five scopes above. |

**Dependency rule.** A scope may only be approved when every earlier scope in the list is also approved. Approving `public_production` without `staging` is not a partial approval — it is an invalid authorization record, and the release-gate controller fails closed on it.

## 2. Evidence identity

| Artifact | File | sha256 |
|---|---|---|
| B4 serving contract | `first_person_serving_contract.json` | `5cfbcf1a4b4c27090714f434609e706d70ef73b50d6b6ee154cc204faef26080` |
| owner-only preview pin set | `first_person_local_review.json` | `cfe80cdef9d90da3380e0746da8724d1e0d8349fa826bdef7b9baf951fa80185` |
| Phase-4 tiers manifest | `public_release_phase4_tiers_manifest_2026-10-22.json` | `894024e77767341983c9a6da12220b9bb16df4ad1b55df522dd7fa2a2a0a2267` |
| served tier | `public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl` | `078ac11c2884488dd2803bc0263e6c7a95e943cf324d46292cc7ca1fa7eb5784` |
| rights register | `public_release_phase4_rights_manifest_2026-10-22.json` | `f8920335b4ef88aca03a0ef419916b597c4cc82b8e1563597f9fe1f512841c9f` |
| Phase-2 verdicts | `public_release_phase2_verdicts_2026-10-22.json` | `cef4c80eeca217c5a908848774a047b2a6f185a0403e9b505094593f409d0f73` |
| 45 speaker conflicts | `public_release_phase4_speaker_conflicts_v2_2026-10-22.jsonl` | `5e57e0415f9b3d694fe0a6ec03160befd888621ca1ed9ab3587cbe5adb324402` |

## 3. Affected counts

| Metric | Value |
|---|---:|
| Public `first_person` alias points at | `first_person_v10` |
| Spans in the served tier | 1529 |
| Spans with a contradictory speaker label (quarantined) | 45 |
| Owner decisions still required before this packet can be completed | 6 |
| Staging suites required | 5 (smoke, safety, citation, cache, fault) |
| Authorization scopes | 6 |

## 4. Preconditions for each scope

| Scope | Preconditions that must already hold |
|---|---|
| `owner_only_testing` | The owner-only preview works and refuses to run in production. It already does. |
| `isolated_local_candidate_collection` | Rights signed off; speaker certification decided; variant tier decided; clinician decision recorded; gold labels and agreement reports filed; snapshot and rollback evidence filed. |
| `staging` | The isolated candidate collection exists with a verified snapshot, and the staging smoke / safety / citation / cache / fault suites have been run and recorded in `audits/evidence/public_release_staging_readiness_2026-10-22.json`. |
| `public_production` | `staging` approved **and** the staging-readiness review recorded every suite as `pass`. |
| `alias_promotion` | `public_production` approved **and** `audits/evidence/public_release_promotion_2026-10-22.json` carries both a snapshot and a rollback evidence path. |
| `harness_enablement` | `alias_promotion` approved **and** every other gate in the release-gate controller passing. |

## 5. Choices

| Value | Meaning |
|---|---|
| `pending` | Not decided. **This is the default and there is no default approval.** |
| `true` | Approved, with reviewer, date and signature recorded at the packet level. |
| `false` | Explicitly declined. This is a decision too. |

## 6. Decision


## Owner decision record

Each scope is approved on its own. No later scope implies an earlier one; the controller fails closed if a later scope is approved while an earlier one is not.

This block is a **copy** of the owner action form's block for this topic (`audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md`). The form is the source of truth; the release-gate controller fails closed if the two disagree. `approved` accepts `"pending"`, `"true"` or `"false"` — there is no default approval.

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

- Decision of record: `final staging / public-release authorization`

## 7. What this packet does NOT decide

- It does not approve any content decision. Those are the other packets.
- It does not enable anything by itself. Each scope still needs its preconditions and its own recorded approval.
- It does not authorize a deployment to Railway. The public route, the alias and the harness each remain under their own gate.
