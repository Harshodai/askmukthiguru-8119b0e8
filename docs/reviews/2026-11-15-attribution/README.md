# Attribution packet — one passage, two videos, two speaker labels (2026-11-15)

> **Nothing in this directory is evidence that the conflict is resolved.** Every decision column below is
> empty; an unsigned row means **unreviewed**, not approved. This packet carries ids, video ids,
> timestamps, labels and counts only — at most the first eight words of any passage, so it can live in a
> public repository.

Derived read-only from collection `first_person_v10` at HEAD `dff2b792` (Qdrant scroll, no writes), and
from `backend/services/first_person_video_decisions.py` at the same commit.

## 1. What was found

- Grouping the 2,758 `retrieval_child` points by their payload `source_text_hash` yields **16 duplicate
  groups / 32 points** — the same 16 groups as `v10_duplicates_dryrun.json` (head `c70d831e`).
- **15 of the 16 groups agree** on `speaker_id` / `guru_id` within the group.
- **Exactly 1 group disagrees**, and both copies carry identical machine verification.

| `source_text_hash` | words | video_id | `source_span_id` | `point_id` | `parent_unit_id` | start–end (ms) | `speaker_id` | `guru_id` |
|---|---|---|---|---|---|---|---|---|
| `31d63736fb2af26b…` | 24 | `bSfYcWPgkpI` | `a197634c043a0b7a3e118c8027ed67ef20f7718de9190a16e9966730227d4a37` | `2c7d8ebd-bdbb-5ca5-8ae2-26116f92a74d` | `fe408b132c5dcabafe50af2428f1da07858deab499bbee7773069114aba8666a` | 143,499 – 162,015 | `krishnaji` | `krishnaji` |
| `31d63736fb2af26b…` | 24 | `-u6ZDfHdB54` | `2456683ce203c5065f618b3e4d06a2d2349af0c369c76db33d62369f33a53595` | `ac25d9b5-37a7-542f-81a7-fd38f26bb2d0` | `22c40007c09a8d6e0803d9cd4dc4fecd48908edd3824bb93ffc18f5e99cd3c47` | 69,200 – 92,800 | `preethaji` | `preethaji` |

Machine fields that are **identical** on both copies, so none of them can decide this:

`speaker_verified=true`, `voice_verification_method=ecapa_voxceleb_centroid_v1`, `rights_cleared=true`,
`domain_rights_status=licensed`, `corpus_version=fp-context-transcript-v1`, `boundary_status=verified`,
`completeness_status=complete`, `quarantine_reason=null`, `quality_status=verified_verbatim`,
`is_verbatim=true`, `speaker_role=guru`.

First eight words of the passage (nothing further is reproduced here): `Her soil are flesh and bones. Her`

**Second variant, same passage family, different `source_text_hash`** — so it is *not* one of the 16 exact
duplicate groups, but it carries the same label conflict. First eight words: `The spirit of our great Earth goes`

| video_id | `source_span_id` | start–end (ms) | `speaker_id` |
|---|---|---|---|
| `-u6ZDfHdB54` | `b123ce9406bcdcac84b1a00eb93e0e0e9e7a12bb1bb2d528466f7b88236d6ef1` | 46,080 – 66,880 | `preethaji` |
| `bSfYcWPgkpI` | `7382a62dc83413aa3793d052c64a7a339d10d5288530fdddb0ed871187e32ed7` | 123,440 – 143,499 | `krishnaji` |

Both variants sit in the *same two parent units* (`fe408b132c…` at span indices 5 and 6; `22c40007c0…` at
span indices 2 and 3), so the disputed material is 4 spans across 2 videos, not 2 spans.

## 2. The two recordings

- `bSfYcWPgkpI` — https://www.youtube.com/watch?v=bSfYcWPgkpI&t=143s (passage at 2:23; second variant at 2:03)
- `-u6ZDfHdB54` — https://www.youtube.com/watch?v=-u6ZDfHdB54&t=69s (passage at 1:09; second variant at 0:46)

## 3. The single question for the reviewer

> **Who is speaking in each of the two recordings of this passage — the same person, or two different people?**

Nothing else is being asked here. Which copy should be canonical, whether to deduplicate, and whether the
rights basis covers the reuse are separate decisions and are **not** part of this table.

## 4. Decision table (empty)

| video_id | timestamp | machine label | decision (`same person` / `two people` / `cannot tell`) | reviewer | date | notes |
|---|---|---|---|---|---|---|
| `bSfYcWPgkpI` | 2:23 | `krishnaji` |  |  |  |  |
| `-u6ZDfHdB54` | 1:09 | `preethaji` |  |  |  |  |
| `-u6ZDfHdB54` | 0:46 | `preethaji` |  |  |  |  |
| `bSfYcWPgkpI` | 2:03 | `krishnaji` |  |  |  |  |

## 5. Hold entry — **NOT APPLIED: needs owner approval**

The narrowest existing serve-time exclusion is a **video-level human decision**, not a payload edit.
`backend/services/first_person_video_decisions.py` reads `data/fp_video_decisions/decisions.json`
(schema `fp-video-decisions-v1`); a video is blocked when `admin_approved` is `false` **or**
`human_speaker_check` is `"rejected"` (`VideoDecision.blocks_serving`, line 82). The block is applied at
retrieval (`backend/services/first_person_context_store.py:559-590`, `blocked_video_ids_or_none()` → `must_not`
on `video_id`) and at
the integrity gate (`backend/services/first_person_pipeline.py:414`), and it fails closed on an invalid file.

The entry that **would** hold the disputed material, if the owner approves it:

```json
{
  "schema": "fp-video-decisions-v1",
  "videos": {
    "bSfYcWPgkpI": {"admin_approved": null, "human_speaker_check": "rejected",
                    "reason": "pending 2026-11-15 attribution review"},
    "-u6ZDfHdB54": {"admin_approved": null, "human_speaker_check": "rejected",
                    "reason": "pending 2026-11-15 attribution review"}
  }
}
```

**Status: NOT APPLIED.** No decisions file exists in the container (`/app/data/fp_video_decisions` absent at
the time of this packet), and no file was written by this investigation.

Collateral, measured from the collection dump: `bSfYcWPgkpI` has **9** child spans in **1** parent;
`-u6ZDfHdB54` has **6** child spans in **1** parent. Blocking both videos removes **15 of 2,758** children
(0.54%) and **2 of 1,466** parents. Blocking either video removes material beyond the disputed passage,
because the decision is per video, not per span.

## 6. Serving state at the time of this packet

Neither copy was served in `20261112-graded-6`, `20261114-graded-7` or `20261114-graded-8`: neither
`video_id` appears in any `rows.jsonl` or `backend.log`, and neither passage variant appears in any served
`answer` or collapsed `citation`. This is the current state, not a guarantee — the passage is eligible
(retrieval filters require only `rights_cleared`, `domain_rights_status=licensed`, `speaker_verified`, and
not blocked), so a future query can serve it.

## 7. AI-agent note

- An agent may **read** this packet, may re-run the read-only grouping, and may add counts.
- An agent may **not** fill a decision column, may not write the hold entry, may not edit a Qdrant payload,
  and may not treat "no decision" as approval. The hold above is a proposal awaiting owner approval.
- An agent must not paste more of the passage into this directory than the eight-word prefix above, and must
  not add transcript text to any file under `docs/`.
- A machine speaker score cannot close this row. Both copies already carry `speaker_verified=true` from the
  same method (`ecapa_voxceleb_centroid_v1`), and that method is what produced the disagreement.
