"""Canonical Evidence Registry, Data Quality Gate, Outbox Sync, Takedowns & Replay.

Implements Parts 3, 4, and 11:
- Immutable original source records (never silently overwritten).
- Versioned corrections tracked in ``EvidenceCorrection`` preserving history.
- Ingestion quality gate (duplicate content hash, timestamp monotonicity,
  transcription confidence, speaker attribution, missing segment gaps, DLQ).
- Event-driven synchronization outbox with idempotent consumer checkpoints,
  retry/DLQ recovery, stale-index detection, and source withdrawal propagation.
- Deterministic replay snapshot construction from provenance coordinates.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.evidence_contract import (
    CanonicalEvidenceRecord,
    EvidenceCandidate,
    SourceType,
    VerificationStatus,
    content_sha256,
    make_evidence_id,
    make_source_id,
)
from services.guru_registry import founder_ids

logger = logging.getLogger(__name__)


class CorpusSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: SourceType
    canonical_uri: str
    title: str
    description: str = ""
    default_teacher_id: str | None = None
    rights_status: Literal["unverified", "licensed", "quarantined", "revoked"] = "unverified"
    rights_basis_ref: str = ""
    publication_date: str | None = None
    content_hash: str
    active_version: str = "1"
    processing_status: Literal[
        "pending", "processing", "completed", "partial", "failed", "withdrawn"
    ] = "pending"
    provenance: dict[str, Any] = Field(default_factory=dict)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correction_id: str
    evidence_id: str
    prior_text: str
    corrected_text: str
    reason: str
    corrected_by: str
    approved_by: str | None = None
    version_seq: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QualityRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rejection_id: str
    source_id: str
    reason_code: str
    detail: str
    severity: Literal["warning", "error"] = "error"
    segment_locator: str = ""
    payload_ref: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OutboxEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    target_store: Literal["qdrant", "memgraph", "okf"]
    operation: Literal["upsert", "correct", "revoke"]
    source_id: str
    evidence_id: str | None = None
    target_version: str = "1"
    payload: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "dispatched", "failed", "dead_letter"] = "pending"
    retry_count: int = 0
    max_retries: int = 3
    last_error: str = ""
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    accepted_records: list[CanonicalEvidenceRecord]
    rejections: list[QualityRejection] = field(default_factory=list)
    coverage_status: Literal["complete", "partial", "failed"] = "complete"
    detected_gaps: list[str] = field(default_factory=list)


class IngestionQualityValidator:
    """Validates multi-format source segments before insertion into canonical_evidence."""

    def __init__(
        self,
        *,
        min_text_chars: int = 12,
        min_transcription_confidence: float = 0.35,
        max_timestamp_gap_ms: int = 120_000,
    ) -> None:
        self._min_text_chars = min_text_chars
        self._min_conf = min_transcription_confidence
        self._max_gap_ms = max_timestamp_gap_ms

    def validate_batch(
        self,
        *,
        source: CorpusSourceRecord,
        segments: Iterable[dict[str, Any]],
        existing_hashes: set[str] | None = None,
    ) -> QualityReport:
        seen_hashes: set[str] = set(existing_hashes or set())
        accepted: list[CanonicalEvidenceRecord] = []
        rejections: list[QualityRejection] = []
        gaps: list[str] = []

        last_end_ms: int | None = None
        total = 0

        for idx, seg in enumerate(segments):
            total += 1
            raw_text = str(seg.get("original_text") or seg.get("text") or "").strip()
            start_ms = seg.get("start_time_ms")
            end_ms = seg.get("end_time_ms")
            page_num = seg.get("page_number")
            locator = (
                f"t:{start_ms}-{end_ms}"
                if start_ms is not None
                else (f"p:{page_num}:i:{idx}" if page_num is not None else f"i:{idx}")
            )

            if len(raw_text) < self._min_text_chars:
                rejections.append(
                    QualityRejection(
                        rejection_id=str(uuid.uuid4()),
                        source_id=source.source_id,
                        reason_code="empty_or_too_short",
                        detail=f"Segment text length {len(raw_text)} < {self._min_text_chars}",
                        segment_locator=locator,
                    )
                )
                continue

            if start_ms is not None and end_ms is not None and int(end_ms) < int(start_ms):
                rejections.append(
                    QualityRejection(
                        rejection_id=str(uuid.uuid4()),
                        source_id=source.source_id,
                        reason_code="timestamp_inversion",
                        detail=f"end_time_ms ({end_ms}) < start_time_ms ({start_ms})",
                        segment_locator=locator,
                    )
                )
                continue

            if start_ms is not None and last_end_ms is not None:
                gap = int(start_ms) - last_end_ms
                if gap > self._max_gap_ms:
                    gaps.append(
                        f"Missing/unindexed audio window {last_end_ms}..{start_ms}ms ({gap}ms)"
                    )
            if end_ms is not None:
                last_end_ms = max(last_end_ms or 0, int(end_ms))

            conf = seg.get("transcription_confidence")
            if conf is not None and float(conf) < self._min_conf:
                rejections.append(
                    QualityRejection(
                        rejection_id=str(uuid.uuid4()),
                        source_id=source.source_id,
                        reason_code="low_transcription_confidence",
                        detail=f"transcription_confidence {conf} < {self._min_conf}",
                        segment_locator=locator,
                    )
                )
                continue

            speaker_role = str(seg.get("speaker_role") or "").strip().lower()
            teacher_id = seg.get("teacher_id") or source.default_teacher_id
            speaker_verified = bool(seg.get("speaker_verified", False))
            founders = founder_ids()
            # Fail closed: if the registry is unavailable (no founders), a non-teacher
            # role must still be rejected rather than attributed to any teacher id.
            if speaker_role in {"audience", "host", "interviewer", "moderator"} and (
                not founders or teacher_id in founders
            ):
                rejections.append(
                    QualityRejection(
                        rejection_id=str(uuid.uuid4()),
                        source_id=source.source_id,
                        reason_code="speaker_role_attribution_conflict",
                        detail=f"Non-teacher role '{speaker_role}' cannot be attributed to '{teacher_id}'",
                        segment_locator=locator,
                    )
                )
                continue

            thash = content_sha256(raw_text)
            dedup_key = f"{source.source_id}:{source.active_version}:{thash}"
            if dedup_key in seen_hashes:
                rejections.append(
                    QualityRejection(
                        rejection_id=str(uuid.uuid4()),
                        source_id=source.source_id,
                        reason_code="duplicate_content_hash",
                        detail=f"Duplicate segment content hash {thash[:16]}",
                        segment_locator=locator,
                    )
                )
                continue
            seen_hashes.add(dedup_key)

            rights_status = str(seg.get("rights_status") or source.rights_status or "unverified")
            if rights_status not in {"licensed", "unverified", "quarantined", "revoked"}:
                rights_status = "unverified"

            eid = make_evidence_id(
                source_id=source.source_id,
                source_version=source.active_version,
                segment_version=str(seg.get("segment_version") or "1"),
                locator=locator,
                text_hash=thash,
            )
            accepted.append(
                CanonicalEvidenceRecord(
                    evidence_id=eid,
                    source_id=source.source_id,
                    teacher_id=str(teacher_id) if teacher_id else None,
                    source_type=source.source_type,
                    source_title=source.title,
                    canonical_uri=source.canonical_uri,
                    original_text=raw_text,
                    start_time_ms=int(start_ms) if start_ms is not None else None,
                    end_time_ms=int(end_ms) if end_ms is not None else None,
                    page_number=int(page_num) if page_num is not None else None,
                    chapter=str(seg.get("chapter")) if seg.get("chapter") else None,
                    language=str(seg.get("language") or "en"),
                    concepts=[str(c) for c in (seg.get("concepts") or []) if c],
                    relationships=list(seg.get("relationships") or []),
                    transcription_confidence=float(conf) if conf is not None else None,
                    verification_status=VerificationStatus(
                        str(seg.get("verification_status") or "automated_candidate")
                    )
                    if rights_status == "licensed"
                    else VerificationStatus.UNVERIFIED,
                    rights_status=rights_status,
                    speaker_verified=speaker_verified,
                    source_version=source.active_version,
                    transcript_version=str(seg.get("transcript_version") or "1"),
                    segment_version=str(seg.get("segment_version") or "1"),
                    chunker_version=str(seg.get("chunker_version") or "boundary_v1:semantic"),
                    content_hash=thash,
                    ingestion_model_version=str(seg.get("ingestion_model_version") or "unknown"),
                    provenance={
                        "locator": locator,
                        "source_uri": source.canonical_uri,
                        "rights_basis_ref": source.rights_basis_ref,
                    },
                )
            )

        if total == 0 or (accepted == [] and rejections):
            cov = "failed"
        elif rejections or gaps:
            cov = "partial"
        else:
            cov = "complete"
        return QualityReport(
            passed=bool(accepted)
            and not any(r.reason_code == "timestamp_inversion" for r in rejections),
            accepted_records=accepted,
            rejections=rejections,
            coverage_status=cov,
            detected_gaps=gaps,
        )


class CanonicalEvidenceRegistry:
    """Authoritative canonical evidence ledger, correction history, outbox & replay."""

    def __init__(self, *, validator: IngestionQualityValidator | None = None) -> None:
        self._validator = validator or IngestionQualityValidator()
        self._sources: dict[str, CorpusSourceRecord] = {}
        self._records: dict[str, CanonicalEvidenceRecord] = {}
        self._corrections: dict[str, list[EvidenceCorrection]] = {}
        self._rejections: list[QualityRejection] = []
        self._outbox: list[OutboxEvent] = []
        self._applied_idempotency_keys: set[str] = set()
        self._content_hashes: set[str] = set()

    def register_and_ingest(
        self,
        *,
        canonical_uri: str,
        source_type: SourceType,
        title: str,
        teacher_id: str | None,
        rights_status: Literal["unverified", "licensed", "quarantined", "revoked"],
        segments: list[dict[str, Any]],
        source_version: str = "1",
        rights_basis_ref: str = "",
        description: str = "",
    ) -> tuple[CorpusSourceRecord, QualityReport]:
        """Idempotently register a multi-format source, validate quality, store records, and queue sync events."""
        sid = make_source_id(canonical_uri)
        combined_hash = content_sha256(
            "|".join(str(s.get("original_text") or s.get("text") or "") for s in segments)
        )
        source = CorpusSourceRecord(
            source_id=sid,
            source_type=source_type,
            canonical_uri=canonical_uri,
            title=title,
            description=description,
            default_teacher_id=teacher_id,
            rights_status=rights_status,
            rights_basis_ref=rights_basis_ref,
            content_hash=combined_hash,
            active_version=source_version,
            processing_status="processing",
        )
        self._sources[sid] = source

        report = self._validator.validate_batch(
            source=source,
            segments=segments,
            existing_hashes=self._content_hashes,
        )
        self._rejections.extend(report.rejections)

        for rec in report.accepted_records:
            self._records[rec.evidence_id] = rec
            self._content_hashes.add(f"{sid}:{source_version}:{rec.content_hash}")
            for store in ("qdrant", "memgraph", "okf"):
                self._enqueue_outbox(
                    target_store=store,
                    operation="upsert",
                    source_id=sid,
                    evidence_id=rec.evidence_id,
                    target_version=rec.source_version,
                    payload={"content_hash": rec.content_hash, "rights_status": rec.rights_status},
                )

        final_status = (
            "completed"
            if report.coverage_status == "complete"
            else ("partial" if report.accepted_records else "failed")
        )
        source = source.model_copy(update={"processing_status": final_status})
        self._sources[sid] = source
        return source, report

    def apply_correction(
        self,
        evidence_id: str,
        *,
        corrected_text: str,
        reason: str,
        corrected_by: str,
        approved_by: str | None = None,
    ) -> tuple[CanonicalEvidenceRecord, EvidenceCorrection]:
        """Append a versioned correction without altering ``original_text``."""
        rec = self._records.get(evidence_id)
        if rec is None:
            raise KeyError(f"Canonical evidence record not found: {evidence_id}")

        history = self._corrections.setdefault(evidence_id, [])
        seq = len(history) + 1
        prior = rec.corrected_text or rec.original_text
        corr = EvidenceCorrection(
            correction_id=str(uuid.uuid4()),
            evidence_id=evidence_id,
            prior_text=prior,
            corrected_text=corrected_text.strip(),
            reason=reason.strip(),
            corrected_by=corrected_by.strip(),
            approved_by=approved_by.strip() if approved_by else None,
            version_seq=seq,
        )
        history.append(corr)

        next_version = (
            str(int(rec.transcript_version) + 1)
            if rec.transcript_version.isdigit()
            else f"{rec.transcript_version}.{seq}"
        )
        updated = rec.model_copy(
            update={
                "corrected_text": corr.corrected_text,
                "transcript_version": next_version,
                "verification_status": (
                    VerificationStatus.HUMAN_VERIFIED if approved_by else rec.verification_status
                ),
            }
        )
        self._records[evidence_id] = updated
        for store in ("qdrant", "memgraph", "okf"):
            self._enqueue_outbox(
                target_store=store,
                operation="correct",
                source_id=rec.source_id,
                evidence_id=evidence_id,
                target_version=next_version,
                payload={"correction_id": corr.correction_id, "version_seq": seq},
            )
        return updated, corr

    def withdraw_source(self, source_id: str, *, reason: str) -> int:
        """Mark a source withdrawn/revoked and queue store revocations across all dependent indexes."""
        src = self._sources.get(source_id)
        if src is None:
            raise KeyError(f"Source not found: {source_id}")
        self._sources[source_id] = src.model_copy(
            update={"rights_status": "revoked", "processing_status": "withdrawn"}
        )
        affected = 0
        for eid, rec in list(self._records.items()):
            if rec.source_id == source_id:
                self._records[eid] = rec.model_copy(
                    update={
                        "rights_status": "revoked",
                        "verification_status": VerificationStatus.REVOKED,
                        "provenance": {**rec.provenance, "withdrawal_reason": reason},
                    }
                )
                affected += 1
                for store in ("qdrant", "memgraph", "okf"):
                    self._enqueue_outbox(
                        target_store=store,
                        operation="revoke",
                        source_id=source_id,
                        evidence_id=eid,
                        target_version=rec.source_version,
                        payload={"reason": reason},
                    )
        return affected

    def is_candidate_active(self, cand: EvidenceCandidate) -> tuple[bool, str]:
        """Verify an index candidate against the canonical ledger (detects revocations & stale versions)."""
        rec = self._records.get(cand.evidence_id)
        if rec is None:
            return (
                cand.rights_status == "licensed",
                "external_index_unregistered"
                if cand.rights_status == "licensed"
                else "unregistered_unverified",
            )
        if rec.rights_status == "revoked" or rec.verification_status == VerificationStatus.REVOKED:
            return False, "source_revoked"
        if rec.rights_status != "licensed":
            return False, f"rights_{rec.rights_status}"
        if str(cand.source_version) != str(rec.source_version):
            return False, f"stale_source_version:{cand.source_version}!={rec.source_version}"
        return True, "ok"

    def dispatch_outbox(
        self,
        handlers: dict[str, Callable[[OutboxEvent], None]],
        *,
        include_failed: bool = True,
    ) -> dict[str, int]:
        """Synchronize pending/failed outbox events idempotently with retry and DLQ isolation."""
        stats = {"dispatched": 0, "skipped_idempotent": 0, "retried": 0, "dead_letter": 0}
        for idx, ev in enumerate(self._outbox):
            if ev.status == "dispatched" or ev.status == "dead_letter":
                continue
            if ev.status == "failed" and not include_failed:
                continue
            if ev.idempotency_key in self._applied_idempotency_keys:
                self._outbox[idx] = ev.model_copy(
                    update={"status": "dispatched", "updated_at": datetime.now(UTC)}
                )
                stats["skipped_idempotent"] += 1
                continue

            handler = handlers.get(ev.target_store)
            if handler is None:
                continue
            try:
                handler(ev)
                self._applied_idempotency_keys.add(ev.idempotency_key)
                self._outbox[idx] = ev.model_copy(
                    update={"status": "dispatched", "updated_at": datetime.now(UTC)}
                )
                stats["dispatched"] += 1
            except Exception as exc:
                retries = ev.retry_count + 1
                next_status = "dead_letter" if retries >= ev.max_retries else "failed"
                self._outbox[idx] = ev.model_copy(
                    update={
                        "retry_count": retries,
                        "status": next_status,
                        "last_error": str(exc),
                        "updated_at": datetime.now(UTC),
                    }
                )
                if next_status == "dead_letter":
                    stats["dead_letter"] += 1
                else:
                    stats["retried"] += 1
        return stats

    def requeue_dead_letter(self) -> int:
        """Reset dead-lettered events back to pending for operational recovery."""
        count = 0
        for idx, ev in enumerate(self._outbox):
            if ev.status == "dead_letter":
                self._outbox[idx] = ev.model_copy(
                    update={"status": "pending", "retry_count": 0, "updated_at": datetime.now(UTC)}
                )
                count += 1
        return count

    def detect_stale_index_records(
        self, index_snapshots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Compare external store index entries against canonical registry to detect drift."""
        drift: list[dict[str, Any]] = []
        for snap in index_snapshots:
            eid = str(snap.get("evidence_id") or "")
            rec = self._records.get(eid)
            if rec is None:
                drift.append({"evidence_id": eid, "issue": "orphan_index_record"})
                continue
            if rec.rights_status != "licensed":
                drift.append(
                    {
                        "evidence_id": eid,
                        "issue": f"should_be_revoked_or_hidden:{rec.rights_status}",
                    }
                )
            elif str(snap.get("source_version") or "") != str(rec.source_version):
                drift.append(
                    {
                        "evidence_id": eid,
                        "issue": f"stale_version:{snap.get('source_version')}!={rec.source_version}",
                    }
                )
        return drift

    def build_replay_snapshot(self, evidence_ids: list[str]) -> dict[str, Any]:
        """Produce deterministic replay coordinates preserving immutable originals & correction seqs."""
        items: list[dict[str, Any]] = []
        for eid in evidence_ids:
            rec = self._records.get(eid)
            if rec is None:
                continue
            corrs = self._corrections.get(eid, [])
            items.append(
                {
                    "evidence_id": eid,
                    "source_id": rec.source_id,
                    "source_version": rec.source_version,
                    "transcript_version": rec.transcript_version,
                    "content_hash": rec.content_hash,
                    "original_text": rec.original_text,
                    "effective_text": rec.corrected_text or rec.original_text,
                    "correction_count": len(corrs),
                }
            )
        return {"replay_timestamp": datetime.now(UTC).isoformat(), "items": items}

    def get_record(self, evidence_id: str) -> CanonicalEvidenceRecord | None:
        return self._records.get(evidence_id)

    def get_corrections(self, evidence_id: str) -> list[EvidenceCorrection]:
        return list(self._corrections.get(evidence_id, []))

    def get_rejections(self, source_id: str | None = None) -> list[QualityRejection]:
        if source_id is None:
            return list(self._rejections)
        return [r for r in self._rejections if r.source_id == source_id]

    def get_outbox(self, *, status: str | None = None) -> list[OutboxEvent]:
        if status is None:
            return list(self._outbox)
        return [e for e in self._outbox if e.status == status]

    def _enqueue_outbox(
        self,
        *,
        target_store: Literal["qdrant", "memgraph", "okf"],
        operation: Literal["upsert", "correct", "revoke"],
        source_id: str,
        evidence_id: str | None,
        target_version: str,
        payload: dict[str, Any],
    ) -> None:
        ikey = content_sha256(
            f"{target_store}:{operation}:{source_id}:{evidence_id}:{target_version}:{sorted(payload.items())}"
        )
        self._outbox.append(
            OutboxEvent(
                event_id=str(uuid.uuid4()),
                target_store=target_store,
                operation=operation,
                source_id=source_id,
                evidence_id=evidence_id,
                target_version=target_version,
                payload=payload,
                idempotency_key=ikey,
            )
        )
