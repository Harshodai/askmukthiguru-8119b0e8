#!/usr/bin/env python3
"""Split the first-person evidence into explicit, immutable corpus tiers.

**Read-only.** No Qdrant client, no alias, no Redis, no env change, no
deployment. It reads the Phase-3 candidate/quarantine manifests, the Phase-2
verdict index and the independent rights join, and writes the tier manifests
plus a manifest-of-manifests with the sha256 of each.

Why this exists
---------------
The first-person v10 corpus mixes four very different populations behind one
collection name. Serving them under one policy is how a *variant* transcript
or an *unlocated* span reaches a seeker as if it were verified. The tiers
make the populations explicit, countable and separately governable:

``local_review_candidate``
    Exact Phase-3 reconstruction **and** a Phase-2 per-span verdict of
    ``verified`` **and** a confirmed rights entry. This is the only tier the
    owner-only test mode may serve. It is deliberately **not** called "public
    verified": human speaker-label certification (B7) and owner rights sign-off
    (B5) are still open, so it is an *automated-evidence candidate*.
``review_required``
    Human-review records: the 45 speaker-label conflicts, spans whose rights
    are not confirmed, and any span whose acoustic evidence did not pass.
``variant_candidate``
    Transcript/text variants (the reconstruction is not exact). Never served by
    default; admitting them needs a separate, explicit owner decision.
``unlocatable_quarantine``
    Spans that could not be located in the authoritative word-timed artifact.
    No reconstructed id and no audio window. Quarantined — but **identified**:
    every row carries the recovered live span identity, a deterministic
    quarantine record id and the full provenance of that recovery.
``deterministic_id_collision_quarantine``
    Two or more **distinct source spans** that produced the same deterministic
    rebuilt span id. Every member is quarantined; none is silently kept and
    none is silently dropped. See ``COLLISION_CAUSE`` below.

Identity rules (v2)
-------------------
* A rebuilt id is a function of the **reconstructed word window** only
  (``guru_id | video_id | corpus_version | word_start | word_end |
  transcript_hash``). Two distinct source spans that resolve to the same word
  window therefore collide. That is an **incomplete id namespace**, and it is
  detected here — never absorbed.
* A quarantine row must carry a **unique, immutable** identity. When the
  Phase-3 manifest carries the live span id, that identity is *recovered* and
  recorded (never invented). When it does not, the row still gets a
  deterministic ``quarantine_record_id`` derived from every piece of evidence
  available, and it is marked ``identity_status: unresolved``.

Exit codes
----------
=====  ===================================================================
0      Tiers produced and every tier is empty except
       ``local_review_candidate`` (the corpus is clean).
1      Tiers produced; review/quarantine tiers are populated. This is the
       ordinary, documented release-blocking status.
2      No trustworthy tier set could be produced: an input is unreadable or
       unparseable, the candidate and verdict sets disagree, or a tier
       invariant is violated (a span in two tiers, a tier count that does not
       reconcile). Fail closed.
=====  ===================================================================

Usage
-----
    python -m scripts.ops.build_fp_corpus_tiers \\
        --candidate audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl \\
        --quarantine audits/evidence/public_release_phase3_quarantine_2026-10-21.jsonl \\
        --verdicts audits/evidence/public_release_phase2_verdicts_2026-10-22.json \\
        --rights-join audits/evidence/public_release_phase4_rights_join_2026-10-22.jsonl \\
        --out-dir audits/evidence \\
        --date 2026-10-22
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

TIER_LOCAL = "local_review_candidate"
TIER_REVIEW = "review_required"
TIER_VARIANT = "variant_candidate"
TIER_UNLOCATABLE = "unlocatable_quarantine"
TIER_COLLISION = "deterministic_id_collision_quarantine"

TIERS = (TIER_LOCAL, TIER_REVIEW, TIER_VARIANT, TIER_UNLOCATABLE, TIER_COLLISION)

TIER_SCHEMA = "first-person-corpus-tier-v2"
TIERS_MANIFEST_SCHEMA = "first-person-corpus-tiers-manifest-v2"
COLLISION_SCHEMA = "first-person-deterministic-id-collision-v1"
SCRIPT_VERSION = "build-fp-corpus-tiers-v2"

EVIDENCE_POLICY = "automated_evidence_candidate"

# The namespace a rebuilt span id is derived from. It deliberately does NOT
# include the source (live) span identity — that is the defect.
SPAN_ID_NAMESPACE_COMPONENTS = (
    "guru_id",
    "video_id",
    "corpus_version",
    "word_start",
    "word_end",
    "transcript_hash",
)
SPAN_ID_NAMESPACE_MISSING = "source_span_identity (the live v10 source_span_id)"

# The two id namespaces a tier row can carry. A collision is only meaningful
# *within* one namespace.
REBUILT_NAMESPACE = "rebuilt_corpus_v2"
LIVE_NAMESPACE = "live_corpus_v1"

COLLISION_CAUSE = "incomplete_deterministic_id_namespace"
COLLISION_CAUSE_ALTERNATIVES = {
    "incomplete_deterministic_id_namespace": (
        "the rebuilt id is a function of the reconstructed word window only, so two "
        "distinct source spans that resolve to the same window produce the same id"
    ),
    "incorrect_normalization": (
        "the members disagree on normalization_version or on the transcript hash"
    ),
    "insufficient_coordinates": (
        "the members disagree on the rebuilt word window (the coordinates differ)"
    ),
    "input_artifact_conflict": (
        "the members disagree on the ASR/timed-transcript artifact identity"
    ),
}

# The tier-1 name deliberately avoids "verified"/"public": the automated
# evidence behind it is not human-certified (B7) and its rights register is not
# owner-signed (B5).
TIER_DESCRIPTIONS = {
    TIER_LOCAL: (
        "Exact Phase-3 reconstruction + Phase-2 per-span verdict 'verified' + "
        "confirmed rights. Servable ONLY by the owner-only local test mode. "
        "Not public-verified: attribution is automated evidence, not "
        "human-certified."
    ),
    TIER_REVIEW: (
        "Human-review records: speaker-label conflicts, rights-pending spans and "
        "spans whose acoustic evidence did not pass. Never served."
    ),
    TIER_VARIANT: (
        "Transcript/text variants — one row per source span. Never served by "
        "default; a separate explicit owner decision is required."
    ),
    TIER_UNLOCATABLE: (
        "Spans not located in the authoritative word-timed artifact. The live "
        "span identity is recovered where the Phase-3 manifest carries it, "
        "together with a deterministic quarantine record id. No audio window, "
        "no evidence. Never served."
    ),
    TIER_COLLISION: (
        "Distinct source spans that produced the same deterministic rebuilt id. "
        "Every member is quarantined; none is kept and none is dropped. Never "
        "served."
    ),
}

# The provenance fields a quarantine row carries when the Phase-3 manifest
# supplies them. A missing value is recorded as null — never invented.
LIVE_PROVENANCE_FIELDS = (
    "live_source_span_id",
    "live_point_id",
    "live_parent_unit_id",
    "live_corpus_version",
    "live_start_ms",
    "live_end_ms",
    "live_word_start",
    "live_word_end",
    "live_source_text_hash",
    "live_transcript_hash",
    "live_verbatim_text",
    "source_span_index",
    "turn_id",
    "turn_index",
    "previous_span_id",
    "next_span_id",
    "locator_start_token",
    "locator_end_token",
    "locator_similarity",
    "timed_transcript_path",
    "timed_transcript_sha256",
    "timed_alignment_sha256",
    "timed_asr_model",
    "timed_asr_aligned_extent_ms",
)


class CorpusTierError(RuntimeError):
    """Raised when no trustworthy tier set can be produced."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_record_hash(row: dict[str, Any]) -> str:
    """sha256 of the canonical JSON of one input row (stable across runs)."""
    return _sha256_text(json.dumps(row, sort_keys=True, ensure_ascii=False))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [row for _lineno, row in _read_jsonl_indexed(path)]


def _read_jsonl_indexed(path: Path) -> list[tuple[int, dict[str, Any]]]:
    """Read a JSONL file, keeping the 1-based source row number."""
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CorpusTierError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise CorpusTierError(f"{path}:{lineno} is not a JSON object")
            rows.append((lineno, row))
    return rows


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusTierError(f"cannot read JSON from {path}: {exc}") from exc


def _quarantine_record_id(source: dict[str, Any], input_record_sha256: str) -> str:
    """A unique, immutable id for one quarantine row.

    Derived from every piece of evidence available on the row, so two rows
    that share ``(video_id, guru_id)`` still get different ids, and the same
    row always gets the same id.
    """
    parts = [
        "fp-quarantine-record-v1",
        str(source.get("live_source_span_id") or ""),
        str(source.get("video_id") or ""),
        str(source.get("source_asset_id") or ""),
        str(source.get("guru_id") or ""),
        str(source.get("live_start_ms") if source.get("live_start_ms") is not None else ""),
        str(source.get("live_end_ms") if source.get("live_end_ms") is not None else ""),
        str(
            source.get("live_word_start")
            if source.get("live_word_start") is not None
            else ""
        ),
        str(
            source.get("live_word_end")
            if source.get("live_word_end") is not None
            else ""
        ),
        str(source.get("live_source_text_hash") or ""),
        str(source.get("live_transcript_hash") or ""),
        str(source.get("live_parent_unit_id") or ""),
        str(source.get("turn_id") or ""),
        str(source.get("source_span_index") if source.get("source_span_index") is not None else ""),
        input_record_sha256,
    ]
    return _sha256_text("|".join(parts))


def _identity_fields(source: dict[str, Any]) -> tuple[str | None, str, str]:
    """Return (source_span_id, identity_status, identity_resolution_reason).

    The live span id is **recovered** when the Phase-3 manifest carries it.
    It is never invented, never guessed from text, and never derived from a
    coordinate.
    """
    live_id = str(source.get("live_source_span_id") or "").strip()
    if live_id:
        return (
            live_id,
            "recovered",
            "the Phase-3 quarantine row carries live_source_span_id, the exact live v10 "
            "source span identity for this row",
        )
    return (
        None,
        "unresolved",
        "the Phase-3 quarantine row carries no live_source_span_id and no other field "
        "identifies the span; the row is quarantined under a deterministic "
        "quarantine_record_id derived from the evidence that does exist",
    )


def _tier_row(
    *,
    tier: str,
    source: dict[str, Any],
    verdict: dict[str, Any] | None,
    rights: dict[str, Any] | None,
    reasons: list[str],
    serve_by_default: bool,
    decision: str,
    source_row_number: int | None = None,
    input_record_sha256: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    video_id = str(source.get("video_id") or "")
    start_ms = int(source.get("audio_start_ms") or 0)
    end_ms = int(source.get("audio_end_ms") or 0)
    text = str(source.get("reconstructed_text") or "")
    rights_status = str((rights or {}).get("rights_status") or "unknown")
    file_duration = source.get("archived_audio_duration_ms")
    row: dict[str, Any] = {
        "schema": TIER_SCHEMA,
        "tier": tier,
        "serve_by_default": serve_by_default,
        "owner_decision_required": decision,
        "tier_reasons": reasons,
        "source_span_id": str(source.get("source_span_id") or ""),
        "source_span_id_namespace": str(source.get("source_span_id_namespace") or ""),
        "video_id": video_id,
        "source_asset_id": str(source.get("source_asset_id") or video_id),
        "guru_id": str(source.get("guru_id") or ""),
        "text": text,
        "source_text_hash": str(source.get("source_text_hash") or ""),
        "transcript_hash": str(source.get("transcript_hash") or ""),
        "audio_start_ms": start_ms,
        "audio_end_ms": end_ms,
        # Two distinct durations, named so they cannot be confused.
        "audio_slice_duration_ms": end_ms - start_ms,
        "audio_file_duration_ms": int(file_duration) if file_duration is not None else None,
        "audio_sha256": str(source.get("archived_audio_sha256") or ""),
        "audio_path": str(source.get("archived_audio_path") or ""),
        "word_start": source.get("word_start"),
        "word_end": source.get("word_end"),
        "corpus_version": str(source.get("corpus_version") or ""),
        "normalization_version": str(source.get("normalization_version") or ""),
        "coordinate_space_version": str(source.get("coordinate_space_version") or ""),
        "reconstruction_tier": str(source.get("reconstruction_tier") or ""),
        "reconstruction_exact": bool(source.get("reconstruction_exact", False)),
        "rights_status": rights_status,
        "rights_scope": "span_join" if rights else "asset_register",
        "rights_owner_review_status": str((rights or {}).get("owner_review_status") or ""),
        "rights_evidence_document": str((rights or {}).get("rights_evidence_document") or ""),
        "rights_evidence_sha256": str((rights or {}).get("rights_evidence_sha256") or ""),
        "rights_review_date": str((rights or {}).get("rights_review_date") or ""),
        "canonical_source_url": f"https://www.youtube.com/watch?v={video_id}",
        "evidence_policy": EVIDENCE_POLICY,
        "speaker_verdict": str((verdict or {}).get("reason_code") or "not_run"),
        "speaker_model": str((verdict or {}).get("speaker_model") or ""),
        "speaker_model_revision": str((verdict or {}).get("speaker_model_revision") or ""),
        "calibration_revision": str((verdict or {}).get("calibration_revision") or ""),
        "cosine": (verdict or {}).get("cosine"),
        "cosine_floor": (verdict or {}).get("cosine_floor"),
        "margin": (verdict or {}).get("margin"),
        "margin_threshold": (verdict or {}).get("margin_threshold"),
        "expected_guru": str((verdict or {}).get("expected_guru") or ""),
        "predicted_guru": str((verdict or {}).get("predicted_guru") or ""),
        "payload_rights_cleared_claim_untrusted": (rights or {}).get(
            "payload_rights_cleared_claim_untrusted"
        ),
        "source_row_number": source_row_number,
        "input_record_sha256": input_record_sha256,
    }
    if extra:
        row.update(extra)
    return row


def _live_provenance(source: dict[str, Any]) -> dict[str, Any]:
    return {field: source.get(field) for field in LIVE_PROVENANCE_FIELDS}


def build_tiers(args: argparse.Namespace) -> dict[str, Any]:
    candidate_rows = _read_jsonl(Path(args.candidate))
    quarantine_indexed = _read_jsonl_indexed(Path(args.quarantine))
    quarantine_rows = [row for _lineno, row in quarantine_indexed]
    verdict_doc = _read_json(Path(args.verdicts))
    if not isinstance(verdict_doc, dict) or not isinstance(
        verdict_doc.get("verdicts"), dict
    ):
        raise CorpusTierError("verdict manifest has no 'verdicts' object")
    verdicts: dict[str, Any] = verdict_doc["verdicts"]
    rights_rows = _read_jsonl(Path(args.rights_join))
    rights_by_span = {str(row.get("source_span_id") or ""): row for row in rights_rows}

    # Per-asset rights status (from the independent register) so a
    # quarantined row still carries the rights basis of its asset.
    rights_by_asset: dict[str, dict[str, Any]] = {}
    if getattr(args, "rights_manifest", None):
        manifest = _read_json(Path(args.rights_manifest))
        for asset in manifest.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            video_id = str(asset.get("video_id") or "")
            if not video_id:
                continue
            rights_by_asset[video_id] = {
                "rights_status": str(asset.get("rights_status") or "unknown"),
                "owner_review_status": str(asset.get("owner_review_status") or ""),
                "rights_evidence_document": str(asset.get("evidence_document") or ""),
                "rights_evidence_sha256": str(asset.get("evidence_sha256") or ""),
                "rights_review_date": str(asset.get("review_date") or ""),
                "payload_rights_cleared_claim_untrusted": asset.get(
                    "payload_rights_cleared_claim_untrusted"
                ),
            }

    tier_rows: dict[str, list[dict[str, Any]]] = {tier: [] for tier in TIERS}
    seen: set[str] = set()

    # ---- candidate spans ---------------------------------------------------
    for source in candidate_rows:
        span_id = str(source.get("source_span_id") or "")
        if not span_id:
            raise CorpusTierError("candidate row without source_span_id")
        if span_id in seen:
            raise CorpusTierError(f"duplicate source_span_id in candidate: {span_id}")
        seen.add(span_id)
        verdict = verdicts.get(span_id)
        if verdict is None:
            raise CorpusTierError(f"no Phase-2 verdict for candidate span {span_id}")
        rights = rights_by_span.get(span_id)
        if rights is None:
            raise CorpusTierError(f"no rights join row for candidate span {span_id}")

        reason_code = str(verdict.get("reason_code") or "")
        rights_servable = bool(rights.get("servable"))
        reasons: list[str] = []
        if reason_code == "refused_guru_mismatch":
            reasons.append("speaker_label_conflict_acoustic_contradiction")
        elif reason_code != "verified":
            reasons.append(f"speaker_evidence_not_passed:{reason_code or 'unknown'}")
        if not rights_servable:
            reasons.append(f"rights_not_confirmed:{rights.get('rights_status')}")

        if not reasons:
            tier = TIER_LOCAL
            serve_by_default = True
            decision = ""
        else:
            tier = TIER_REVIEW
            serve_by_default = False
            decision = "human_review_required"
        tier_rows[tier].append(
            _tier_row(
                tier=tier,
                source=source,
                verdict=verdict,
                rights=rights,
                reasons=reasons,
                serve_by_default=serve_by_default,
                decision=decision,
                input_record_sha256=_canonical_record_hash(source),
                extra={
                    "source_span_id_namespace": REBUILT_NAMESPACE,
                    **_live_provenance(source),
                },
            )
        )

    # ---- quarantined spans -------------------------------------------------
    for lineno, source in quarantine_indexed:
        span_id = str(source.get("source_span_id") or "").strip()
        reasons = [str(r) for r in (source.get("quarantine_reasons") or [])]
        tier_name = str(source.get("reconstruction_tier") or "")
        if tier_name == "variant" or "reconstruction_variant_not_exact" in reasons:
            tier = TIER_VARIANT
            tier_reasons = reasons or ["reconstruction_variant_not_exact"]
            decision = "explicit_owner_decision_required"
        else:
            tier = TIER_UNLOCATABLE
            tier_reasons = reasons or ["span_not_located_in_asr"]
            decision = ""
        record_hash = _canonical_record_hash(source)
        extra: dict[str, Any] = {
            "quarantine_record_id": _quarantine_record_id(source, record_hash),
            "source_row_number": lineno,
            "input_record_sha256": record_hash,
            "source_span_id_namespace": REBUILT_NAMESPACE,
        }
        # Every quarantine row carries the live provenance of the source span.
        extra.update(_live_provenance(source))
        if tier == TIER_UNLOCATABLE:
            recovered, status, why = _identity_fields(source)
            extra.update(
                {
                    "source_span_id": recovered or "",
                    "source_span_id_namespace": LIVE_NAMESPACE if recovered else "",
                    "rebuilt_source_span_id": span_id or None,
                    "identity_status": status,
                    "identity_resolution_reason": why,
                }
            )
        asset_rights = rights_by_asset.get(str(source.get("video_id") or ""))
        tier_rows[tier].append(
            _tier_row(
                tier=tier,
                source=source,
                verdict=None,
                rights=asset_rights,
                reasons=tier_reasons,
                serve_by_default=False,
                decision=decision,
                source_row_number=lineno,
                input_record_sha256=record_hash,
                extra=extra,
            )
        )

    # ---- deterministic-id collisions --------------------------------------
    # A rebuilt id must identify exactly one source span. When two or more
    # distinct source spans produce the same id, every member is quarantined:
    # none is silently kept and none is silently dropped.
    members: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
    for tier in TIERS:
        for row in tier_rows[tier]:
            span_id = str(row.get("source_span_id") or "")
            if span_id:
                namespace = str(row.get("source_span_id_namespace") or "unknown")
                members.setdefault((namespace, span_id), []).append((tier, row))

    collision_records: list[dict[str, Any]] = []
    collision_member_ids: set[str] = set()
    for (namespace, span_id), entries in sorted(members.items()):
        if len(entries) < 2:
            continue
        rows = [row for _tier, row in entries]
        live_ids = {str(row.get("live_source_span_id") or "") for row in rows}
        cause, cause_evidence = _classify_collision(rows)
        collision_member_ids.add(span_id)
        for row in rows:
            row["collision_source_span_id"] = span_id
            row["collision_member_count"] = len(rows)
            row["collision_cause"] = cause
            row["collision_resolution_status"] = "unresolved"
            row["quarantine_record_id"] = row.get("quarantine_record_id") or _sha256_text(
                "|".join(
                    [
                        "fp-collision-member-v1",
                        span_id,
                        str(row.get("live_source_span_id") or ""),
                        str(row.get("input_record_sha256") or ""),
                    ]
                )
            )
            row["identity_status"] = "collision_member"
            row["identity_resolution_reason"] = (
                "this source span's deterministic rebuilt id is shared with at least one "
                "other distinct source span; the id does not identify a single span, so "
                "the span is quarantined"
            )
            row["tier_reasons"] = sorted(
                set(list(row.get("tier_reasons") or []) + ["deterministic_id_collision"])
            )
            row["serve_by_default"] = False
            row["owner_decision_required"] = "explicit_owner_decision_required"
        # Move every member out of its original tier into the collision tier.
        for origin_tier, row in entries:
            tier_rows[origin_tier].remove(row)
            row["tier"] = TIER_COLLISION
        collision_records.append(
            {
                "schema": COLLISION_SCHEMA,
                "script_version": SCRIPT_VERSION,
                "collided_source_span_id": span_id,
                "collided_namespace": namespace,
                "member_count": len(rows),
                "distinct_source_span_count": len(
                    {str(row.get("live_source_span_id") or "") for row in rows}
                ),
                "distinct_live_span_ids": sorted(live_ids),
                "collision_cause": cause,
                "collision_cause_detail": COLLISION_CAUSE_ALTERNATIVES.get(cause, cause),
                "collision_cause_evidence": cause_evidence,
                "span_id_namespace_components": list(SPAN_ID_NAMESPACE_COMPONENTS),
                "span_id_namespace_missing_component": SPAN_ID_NAMESPACE_MISSING,
                "namespace_fix_applied": False,
                "namespace_fix_reason": (
                    "adding the source span identity to the id namespace re-keys every "
                    "span in the corpus, which invalidates the 1,600 Phase-2 verdicts "
                    "(keyed by the current rebuilt ids), the rights join, the tier "
                    "manifests and the pinned local-review contract. That is not "
                    "backward-compatible, so no namespace change was made and the "
                    "collision stays unresolved."
                ),
                "resolution_status": "unresolved",
                "quarantined": True,
                "serve_by_default": False,
                "members": [
                    {
                        "source_span_id": span_id,
                        "live_source_span_id": row.get("live_source_span_id"),
                        "video_id": row.get("video_id"),
                        "guru_id": row.get("guru_id"),
                        "source_row_number": row.get("source_row_number"),
                        "input_record_sha256": row.get("input_record_sha256"),
                        "rebuilt_word_start": row.get("word_start"),
                        "rebuilt_word_end": row.get("word_end"),
                        "live_word_start": row.get("live_word_start"),
                        "live_word_end": row.get("live_word_end"),
                        "source_text_hash": row.get("source_text_hash"),
                        "transcript_hash": row.get("transcript_hash"),
                        "quarantine_record_id": row.get("quarantine_record_id"),
                    }
                    for row in rows
                ],
            }
        )
        tier_rows[TIER_COLLISION].extend(rows)

    # ---- reconcile ---------------------------------------------------------
    overlap = sum(len(rows) for rows in tier_rows.values())
    expected = len(candidate_rows) + len(quarantine_rows)
    if overlap != expected:
        raise CorpusTierError(
            f"tier counts do not reconcile: {overlap} rows in tiers vs {expected} inputs"
        )

    for tier, rows in tier_rows.items():
        ids = [row["source_span_id"] for row in rows if row["source_span_id"]]
        if tier == TIER_COLLISION:
            # A collision tier row is one SOURCE span; the rebuilt id it carries
            # is by definition shared with the other members. Uniqueness is
            # enforced on the live span id and on the quarantine record id.
            live = [str(row.get("live_source_span_id") or "") for row in rows]
            if len(live) != len(set(live)):
                raise CorpusTierError(
                    f"tier {tier} contains duplicate live_source_span_id values"
                )
            continue
        if len(ids) != len(set(ids)):
            raise CorpusTierError(f"tier {tier} contains duplicate source_span_id values")

    # A collided id must have every one of its members inside the collision
    # tier — never split across tiers, never half-kept.
    for span_id in collision_member_ids:
        for tier in TIERS:
            if tier == TIER_COLLISION:
                continue
            if any(row.get("source_span_id") == span_id for row in tier_rows[tier]):
                raise CorpusTierError(
                    f"collided id {span_id} still appears in tier {tier}"
                )

    # Every quarantine row must have a unique, immutable quarantine record id.
    record_ids = [
        str(row.get("quarantine_record_id") or "")
        for tier in (TIER_VARIANT, TIER_UNLOCATABLE, TIER_COLLISION)
        for row in tier_rows[tier]
    ]
    if any(not value for value in record_ids):
        raise CorpusTierError("a quarantine row is missing its quarantine_record_id")
    if len(record_ids) != len(set(record_ids)):
        raise CorpusTierError("quarantine_record_id values are not unique")

    # A tier-1 row must carry every evidence field the serving path requires.
    for row in tier_rows[TIER_LOCAL]:
        missing = [
            field
            for field in (
                "source_span_id",
                "text",
                "source_text_hash",
                "audio_start_ms",
                "audio_end_ms",
                "audio_sha256",
                "speaker_verdict",
                "rights_status",
                "corpus_version",
            )
            if not row.get(field) and row.get(field) != 0
        ]
        if missing:
            raise CorpusTierError(
                f"tier-1 row {row['source_span_id']} is missing evidence: {missing}"
            )
        if row["speaker_verdict"] != "verified":
            raise CorpusTierError(
                f"tier-1 row {row['source_span_id']} has a non-verified speaker verdict"
            )

    # A tier-1 row may never be a collision member.
    tier1_ids = {row["source_span_id"] for row in tier_rows[TIER_LOCAL]}
    leaked = tier1_ids & collision_member_ids
    if leaked:
        raise CorpusTierError(f"tier-1 rows are collision members: {sorted(leaked)}")

    return {
        "tier_rows": tier_rows,
        "collision_records": collision_records,
        "collision_count": len(collision_records),
        "collision_member_count": sum(len(r["members"]) for r in collision_records),
        "candidate_count": len(candidate_rows),
        "quarantine_count": len(quarantine_rows),
        "verdict_meta": {
            "run_id": str(verdict_doc.get("run_id") or ""),
            "calibration_revision": str(verdict_doc.get("calibration_revision") or ""),
        },
    }


def _classify_collision(rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Derive the collision cause from the colliding rows themselves.

    The four candidate causes are distinguished by what the members *agree*
    and *disagree* on. The verdict is data, not a hard-coded assumption.
    """
    def _values(field: str) -> set[Any]:
        return {row.get(field) for row in rows}

    windows = {
        (row.get("guru_id"), row.get("video_id"), row.get("corpus_version"),
         row.get("word_start"), row.get("word_end"), row.get("transcript_hash"))
        for row in rows
    }
    normalization = _values("normalization_version")
    artifacts = _values("timed_transcript_sha256") or _values("transcript_hash")
    evidence = {
        "member_count": len(rows),
        "distinct_rebuilt_id_windows": len(windows),
        "distinct_normalization_versions": sorted(str(v) for v in normalization),
        "distinct_timed_transcript_artifact_hashes": sorted(str(v) for v in artifacts),
        "distinct_live_source_span_ids": sorted(
            str(row.get("live_source_span_id") or "") for row in rows
        ),
        "rebuilt_word_windows": sorted(
            {f"{row.get('word_start')}-{row.get('word_end')}" for row in rows}
        ),
        "live_word_windows": sorted(
            {f"{row.get('live_word_start')}-{row.get('live_word_end')}" for row in rows}
        ),
    }
    if len(windows) == 1 and len(normalization) == 1 and len(artifacts) == 1:
        return COLLISION_CAUSE, evidence
    if len(normalization) > 1:
        return "incorrect_normalization", evidence
    if len(artifacts) > 1:
        return "input_artifact_conflict", evidence
    return "insufficient_coordinates", evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--quarantine", required=True)
    parser.add_argument("--verdicts", required=True)
    parser.add_argument("--rights-join", required=True)
    parser.add_argument("--rights-manifest", default=None)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--date", required=True, help="artifact date suffix, e.g. 2026-10-22")
    parser.add_argument(
        "--generated-at-utc",
        default=os.environ.get("FP_TIERS_GENERATED_AT_UTC", ""),
        help="pinned timestamp for byte-identical repeats",
    )
    args = parser.parse_args(argv)

    try:
        built = build_tiers(args)
    except CorpusTierError as exc:
        print(f"[fp-tiers] ERROR: {exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tier_files: dict[str, dict[str, Any]] = {}
    for tier in TIERS:
        path = out_dir / f"public_release_phase4_tier_{tier}_{args.date}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in built["tier_rows"][tier]:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        tier_files[tier] = {
            "path": str(path),
            "sha256": _sha256_file(path),
            "row_count": len(built["tier_rows"][tier]),
            "description": TIER_DESCRIPTIONS[tier],
            "serve_by_default": tier == TIER_LOCAL,
        }

    collision_path = out_dir / f"public_release_phase4_deterministic_id_collisions_{args.date}.jsonl"
    with collision_path.open("w", encoding="utf-8") as handle:
        for record in built["collision_records"]:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

    counts = {tier: len(built["tier_rows"][tier]) for tier in TIERS}
    reason_counts = Counter(
        reason
        for tier in (TIER_REVIEW,)
        for row in built["tier_rows"][tier]
        for reason in row["tier_reasons"]
    )

    total_rows = sum(counts.values())
    all_rows = [row for tier in TIERS for row in built["tier_rows"][tier]]

    def _duplicate_groups(key: str) -> dict[str, int]:
        counter = Counter(str(row.get(key) or "") for row in all_rows if row.get(key))
        return dict(sorted((k, v) for k, v in counter.items() if v > 1))

    def _duplicate_groups_by(
        rows: list[dict[str, Any]], key_fn: Any
    ) -> dict[str, int]:
        counter = Counter(key_fn(row) for row in rows)
        return dict(sorted((k, v) for k, v in counter.items() if v > 1))

    def _video_guru_key(row: dict[str, Any]) -> str:
        return f"{row.get('video_id') or ''}|{row.get('guru_id') or ''}"

    unique_rebuilt_ids = len(
        {
            (str(row.get("source_span_id_namespace") or ""), str(row.get("source_span_id") or ""))
            for row in all_rows
            if str(row.get("source_span_id") or "")
        }
    )
    unique_live_ids = len(
        {
            str(row.get("live_source_span_id") or "")
            for row in all_rows
            if str(row.get("live_source_span_id") or "")
        }
    )
    video_guru_groups = _duplicate_groups_by(all_rows, _video_guru_key)
    duplicate_levels = {
        "by_rebuilt_source_span_id": {
            "group_count": len(_duplicate_groups("source_span_id")),
            "groups": _duplicate_groups("source_span_id"),
        },
        "by_live_source_span_id": {
            "group_count": len(_duplicate_groups("live_source_span_id")),
            "groups": _duplicate_groups("live_source_span_id"),
        },
        "by_quarantine_record_id": {
            "group_count": len(_duplicate_groups("quarantine_record_id")),
            "groups": _duplicate_groups("quarantine_record_id"),
        },
        "by_video_id_and_guru_id": {
            "group_count": len(video_guru_groups),
            "max_group_size": max(video_guru_groups.values()) if video_guru_groups else 0,
            "note": (
                "many spans legitimately share one (video, teacher) pair; this level is "
                "reported as a count only because it is not an identity defect"
            ),
        },
    }
    unlocatable_identity = Counter(
        str(row.get("identity_status") or "unknown")
        for row in built["tier_rows"][TIER_UNLOCATABLE]
    )

    summary = {
        "schema": TIER_SCHEMA.replace("tier-v2", "tiers-summary-v2"),
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": args.generated_at_utc,
        "tier_names": list(TIERS),
        "tier_descriptions": TIER_DESCRIPTIONS,
        "evidence_policy": EVIDENCE_POLICY,
        "tier_counts": counts,
        "input_counts": {
            "phase3_candidate": built["candidate_count"],
            "phase3_quarantine": built["quarantine_count"],
            "phase3_total_rows": built["candidate_count"] + built["quarantine_count"],
        },
        "output_counts": {
            "total_rows": total_rows,
            "total_unique_source_span_ids": unique_rebuilt_ids,
            "total_unique_live_source_span_ids": unique_live_ids,
            "rows_dropped": 0,
            "rows_deduplicated": 0,
        },
        "duplicate_ids_by_identity_level": duplicate_levels,
        "deterministic_id_collisions": {
            "collision_count": built["collision_count"],
            "collision_member_count": built["collision_member_count"],
            "collided_source_span_ids": sorted(
                record["collided_source_span_id"] for record in built["collision_records"]
            ),
            "cause": (
                built["collision_records"][0]["collision_cause"]
                if built["collision_records"]
                else ""
            ),
            "namespace_fix_applied": False,
            "resolution_status": "unresolved",
        },
        "unlocatable_identity": {
            "counts": dict(sorted(unlocatable_identity.items())),
            "recovered_from_live_span_id": unlocatable_identity.get("recovered", 0),
            "unresolved": unlocatable_identity.get("unresolved", 0),
        },
        "review_required_reason_counts": dict(sorted(reason_counts.items())),
        "run_id": built["verdict_meta"]["run_id"],
        "calibration_revision": built["verdict_meta"]["calibration_revision"],
        "release_blocking": bool(
            counts[TIER_REVIEW]
            or counts[TIER_VARIANT]
            or counts[TIER_UNLOCATABLE]
            or counts[TIER_COLLISION]
        ),
        "public_verified_claim": False,
        "notes": [
            "Tier 1 is an automated-evidence candidate, not a public-verified corpus: "
            "human speaker-label certification (B7) and owner rights sign-off (B5) "
            "are open.",
            "Variant and unlocatable spans are never served by default.",
            "The speaker-conflict quarantine is a separate artifact so a human can "
            "review it row by row.",
            "No row is deduplicated and no row is dropped: the tier counts reconcile "
            "exactly with the Phase-3 input rows.",
            "A deterministic id collision quarantines EVERY member. The rebuilt id "
            "namespace is not changed (that would re-key the corpus and invalidate "
            "the Phase-2 verdicts), so the collision is recorded as unresolved.",
        ],
    }

    manifest = {
        "schema": TIERS_MANIFEST_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": args.generated_at_utc,
        "evidence_policy": EVIDENCE_POLICY,
        "corpus_version": "fp-context-transcript-v2",
        "tiers": tier_files,
        "tier_counts": counts,
        "deterministic_id_collisions": {
            "path": str(collision_path),
            "sha256": _sha256_file(collision_path),
            "row_count": len(built["collision_records"]),
            "member_count": built["collision_member_count"],
        },
        "inputs": {
            "candidate": {
                "path": args.candidate,
                "sha256": _sha256_file(Path(args.candidate)),
            },
            "quarantine": {
                "path": args.quarantine,
                "sha256": _sha256_file(Path(args.quarantine)),
            },
            "verdicts": {
                "path": args.verdicts,
                "sha256": _sha256_file(Path(args.verdicts)),
            },
            "rights_join": {
                "path": args.rights_join,
                "sha256": _sha256_file(Path(args.rights_join)),
            },
        },
        "release_blocking": summary["release_blocking"],
    }

    summary_path = out_dir / f"public_release_phase4_tiers_summary_{args.date}.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_path = out_dir / f"public_release_phase4_tiers_manifest_{args.date}.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"[fp-tiers] counts={counts}")
    print(
        f"[fp-tiers] total_rows={total_rows} unique_ids={unique_rebuilt_ids} "
        f"unique_live_ids={unique_live_ids}"
    )
    print(
        f"[fp-tiers] collisions={built['collision_count']} "
        f"members={built['collision_member_count']}"
    )
    print(f"[fp-tiers] unlocatable identity={dict(sorted(unlocatable_identity.items()))}")
    print(f"[fp-tiers] review reasons={dict(sorted(reason_counts.items()))}")
    return 1 if summary["release_blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
