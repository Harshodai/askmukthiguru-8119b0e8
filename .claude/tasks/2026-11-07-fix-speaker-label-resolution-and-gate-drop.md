# Implementation Plan: Fix Speaker Label Resolution & Serve-Time Gate Drop

## 1. Problem & Root Cause Analysis

### Symptoms
In `20261107-graded-clean-v2`:
- `served_share = 0.0562` (5 / 89 answerable served, failing the 30% bar).
- `showable_rate = 0.8000` (4 / 5 showable, failing the 85% bar).
- 81 parent contexts were chosen for serving by the Context Harness (`decision=serve_single_span` / `serve_parent_context`), but **dropped at serve-time** with:
  `[FirstPersonPipeline] Context harness span failed a serve-time gate for parent ...; falling back to legacy`

### Root Cause
1. **`label_for` Mismatch:**
   In `backend/services/first_person_pipeline.py:2896`:
   ```python
   speaker_name = (
       label_for(span.speaker_id) if span.speaker_verified is True else "unverified clip"
   ) or "unverified clip"
   ```
   In Qdrant collection `first_person_v10`, `span.speaker_id` is stored as `"Sri Preethaji"` (the title case string), while `span.guru_id` is `"preethaji"`.
   In `backend/services/guru_registry.py:102`:
   ```python
   def label_for(guru_id: str | None) -> str | None:
       gid = (guru_id or "").strip().lower()
       return next((g.label for g in get_gurus() if g.id == gid), None)
   ```
   `label_for` compares `g.id == gid`. Since `"preethaji" != "sri preethaji"`, `label_for("Sri Preethaji")` returns `None`!
2. **Integrity Gate Rejection:**
   Because `label_for(span.speaker_id)` returned `None`, `speaker_name` defaulted to `"unverified clip"`.
   Then, in `_passes_integrity_gate(cit_dict)`:
   ```python
   if speaker not in _ALLOWED_SPEAKERS:
       return False
   ```
   Because `"unverified clip"` is not in `{"Sri Krishnaji", "Sri Preethaji"}`, `_passes_integrity_gate` returned `False`!
   This caused all 81 candidate contexts with `speaker_id="Sri Preethaji"` to be discarded at serve-time.

## 2. Proposed Fix

### Change 1: Enhance `label_for` in `backend/services/guru_registry.py`
Allow `label_for` to resolve either by teacher ID (`g.id == gid`) OR by teacher label (`g.label.lower() == gid`):
```python
def label_for(guru_id: str | None) -> str | None:
    gid = (guru_id or "").strip().lower()
    return next((g.label for g in get_gurus() if g.id == gid or g.label.lower() == gid), None)
```

### Change 2: Robust Resolution in `backend/services/first_person_pipeline.py`
In `_build_context_citation`, resolve via `span.guru_id` first, falling back to `span.speaker_id`:
```python
speaker_name = (
    (label_for(span.guru_id) or label_for(span.speaker_id))
    if span.speaker_verified is True
    else "unverified clip"
) or "unverified clip"
```

## 3. Evidence Artifacts
Generate and maintain [`audits/evidence/GRADED_RUN_ANSWERS_2026-11-07.md`](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/audits/evidence/GRADED_RUN_ANSWERS_2026-11-07.md) capturing all 202 questions, routes, latency, and dual-judge verdicts.

## 4. Verification & Testing Steps
1. Unit tests:
   - `backend/tests/test_guru_registry_and_modes.py`
   - `backend/tests/test_first_person_pipeline.py`
   - Verify `label_for("Sri Preethaji")` returns `"Sri Preethaji"`.
   - Verify `cit_dict` has `speaker in _ALLOWED_SPEAKERS`.
2. Commit clean git state.
3. Rebuild Docker container with `docker-compose.graded.yml`.
4. Flush caches and verify empty.
5. Run preflight (`7/7 PASS`).
6. Execute graded capture `20261107-graded-clean-v3` and pass-bar dual judge evaluation.
