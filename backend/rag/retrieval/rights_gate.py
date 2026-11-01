import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContentRightsGate:
    """
    Enforces Invariant X40 & Gate B: rights status originates strictly from
    curated rights register (docs/rights/CONTENT-RIGHTS.md / source_releases).
    Filter on domain_rights_status == 'licensed', gate strictly enforces
    exclusion of unverified or revoked materials. Never default missing rights to 'licensed'.
    """

    #: Metadata keys any stored corpus point carries. A document that carries one
    #: of these came from a corpus collection and must prove its rights; a
    #: document that carries none of them did not (an OKF entry, a web result, a
    #: graph node, an in-flight test fixture) and is out of scope for X40.
    #: Without this split the gate also deletes every non-corpus lane, which is
    #: how it turned 7 unrelated retrieval tests red on 2026-11-01.
    CORPUS_PROVENANCE_KEYS = (
        "corpus_id",
        "corpus_version",
        "domain_rights_status",
        "rights_status",
        "provenance_kind",
        "record_type",
    )

    @classmethod
    def is_corpus_document(cls, chunk: dict[str, Any]) -> bool:
        """True when the document claims to come from a corpus collection."""
        return any(k in chunk for k in cls.CORPUS_PROVENANCE_KEYS)

    # Curated licensed sources verified from docs/rights/CONTENT-RIGHTS.md
    LICENSED_SOURCES = {
        "the four sacred secrets",
        "ekam",
        "o&o academy",
        "sri preethaji & sri krishnaji",
        "times now",
        "tedx",
        "marietv",
        "marie forleo",
    }

    @classmethod
    def validate_rights(cls, chunk: dict[str, Any]) -> bool:
        """
        Validates if a candidate chunk has verified licensed rights.
        Fails closed if rights status is missing, unverified, or revoked.
        Also checks admin video serving governance decisions (blocked videos).
        """
        # 0. Check admin video serving governance
        # `video_is_blocked` fails closed on an invalid decisions file; no blanket
        # except here, so an unexpected error cannot silently serve an excluded video.
        from services.first_person_video_decisions import video_is_blocked
        from services.qdrant.source_policy import VIDEO_ID_IN_SOURCE

        video_id = chunk.get("video_id")
        if not video_id:
            source = str(chunk.get("source_url") or chunk.get("source") or "")
            m = VIDEO_ID_IN_SOURCE.search(source)
            if m:
                video_id = m.group(1)
        if video_id and video_is_blocked(video_id):
            logger.warning(
                f"Rejecting chunk {chunk.get('id', 'unknown')} from admin-blocked video: {video_id}"
            )
            return False

        # 1. Explicit domain_rights_status check
        rights_status = chunk.get("domain_rights_status")
        if rights_status != "licensed":
            # Check source metadata against curated list if status not explicitly set
            source = str(chunk.get("source", chunk.get("source_url", ""))).lower()
            publisher = str(chunk.get("publisher", chunk.get("channel", ""))).lower()

            matched = any(ls in source or ls in publisher for ls in cls.LICENSED_SOURCES)
            if matched and rights_status is None:
                # If source is in curated registry and status is unassigned, enforce fail-closed or assign licensed based on register
                # Per Invariant X40: "Missing or unverified rights status must fail closed (never default to 'licensed')"
                # Unless explicitly 'licensed', we log and reject unverified assets.
                logger.warning(
                    f"Rejecting chunk {chunk.get('id', 'unknown')} due to missing explicit 'licensed' status (source matched: {source})"
                )
                cls._persist_rejection(chunk, "MISSING_EXPLICIT_LICENSED_STATUS")
                return False
            else:
                logger.warning(
                    f"Rejecting chunk {chunk.get('id', 'unknown')} with rights_status='{rights_status}'"
                )
                cls._persist_rejection(chunk, f"INVALID_RIGHTS_STATUS_{rights_status}")
                return False

        return True

    @classmethod
    def filter_candidates(cls, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Filters a list of candidate chunks, retaining only those meeting Invariant X40.
        """
        valid_candidates = []
        for c in candidates:
            if cls.validate_rights(c):
                valid_candidates.append(c)
        return valid_candidates

    @classmethod
    def _persist_rejection(cls, chunk: dict[str, Any], reason: str):
        """
        Persists rejections to public.corpus_gate_rejections format if rejection occurs.
        """
        rejection_record = {
            "chunk_id": chunk.get("id", "unknown"),
            "source": chunk.get("source", "unknown"),
            "reason": reason,
            "timestamp_epoch": chunk.get("timestamp", 0),
        }
        logger.info(f"CORPUS_GATE_REJECTION: {rejection_record}")
