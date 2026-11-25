"""OKF adapter enforcing verification quarantine, tag hygiene, and context resolution."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from domain.evidence_contract import EvidenceCandidate, content_sha256, make_source_id

logger = logging.getLogger(__name__)

# Generic high-frequency tags that carry no discriminative power (GRAPH_CONTEXT_ADVANCEMENTS G3)
_GENERIC_OKF_TAGS = frozenset({"oneness", "teaching", "teachings", "spiritual", "general"})


class OKFEvidenceAdapter:
    """Reads curated OKF entries while quarantining unverified entries from serving."""

    def __init__(self, compiled_entries: list[dict[str, Any]] | None = None) -> None:
        self._entries = compiled_entries

    def _load_entries(
        self, *, include_unverified: bool = False, raise_on_error: bool = False
    ) -> list[dict[str, Any]]:
        if self._entries is not None:
            pool = self._entries
        else:
            try:
                from services.memory.okf_store import OKF_DIR, _load_compiled_matrix

                pool, matrix = _load_compiled_matrix(OKF_DIR / "compiled.json")
                if raise_on_error and matrix is None:
                    raise RuntimeError("OKF compiled index unavailable")
            except Exception as exc:
                if raise_on_error:
                    logger.warning("[OKFEvidenceAdapter] _load_compiled_matrix failed: %s", exc)
                    raise
                logger.debug("[OKFEvidenceAdapter] _load_compiled_matrix failed: %s", exc)
                return []

        if include_unverified:
            return pool
        # Quarantine entries where verified is None or False (G3 / A3)
        return [
            e
            for e in pool
            if e.get("verified") is True or e.get("verification_state") == "verified"
        ]

    def search(
        self,
        *,
        query_dense: list[float],
        teacher_id: str | None = None,
        limit: int = 5,
        min_similarity: float = 0.40,
        include_unverified: bool = False,
        raise_on_error: bool = False,
    ) -> list[EvidenceCandidate]:
        entries = self._load_entries(
            include_unverified=include_unverified, raise_on_error=raise_on_error
        )
        if not entries or not query_dense or limit <= 0:
            return []

        q_vec = np.asarray(query_dense, dtype=np.float32)
        q_norm = float(np.linalg.norm(q_vec))
        if q_norm <= 0.0:
            return []

        tid_filter = teacher_id.strip().lower() if teacher_id else None
        if tid_filter in {"", "both", "all"}:
            tid_filter = None

        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in entries:
            emb = entry.get("embedding")
            if not emb or len(emb) != len(query_dense):
                continue
            entry_teacher = str(entry.get("teacher") or "both").lower()
            if (
                tid_filter
                and entry_teacher not in {"both", "sri-preethaji-and-sri-krishnaji"}
                and tid_filter not in entry_teacher
            ):
                continue
            e_vec = np.asarray(emb, dtype=np.float32)
            e_norm = float(np.linalg.norm(e_vec))
            if e_norm <= 0.0:
                continue
            sim = float(np.dot(q_vec, e_vec) / (q_norm * e_norm))
            if sim >= min_similarity:
                scored.append((sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        out: list[EvidenceCandidate] = []
        for sim, entry in scored[:limit]:
            resource = str(entry.get("resource") or entry.get("source") or "").strip()
            body = str(entry.get("body") or "").strip()
            title = str(entry.get("title") or "").strip()
            text = f"{title}\n\n{body}".strip() if title and body else (body or title)
            if not text:
                continue
            raw_tags = [str(t) for t in (entry.get("tags") or []) if isinstance(t, str)]
            specific_tags = [t for t in raw_tags if t.strip().lower() not in _GENERIC_OKF_TAGS]
            span_id = str(entry.get("source_span_id") or entry.get("slug") or content_sha256(text))
            is_verified = bool(
                entry.get("verified") is True or entry.get("verification_state") == "verified"
            )
            out.append(
                EvidenceCandidate(
                    evidence_id=span_id,
                    source_id=make_source_id(resource or span_id),
                    source_type="document",
                    source_title=title,
                    source_url=resource,
                    teacher_id=str(entry.get("teacher") or "") or None,
                    speaker_verified=False,  # OKF summaries are curated wiki notes, never raw speaker audio
                    text=text,
                    retrieval_source="okf",
                    retrieval_score=sim,
                    verification_status="human_verified" if is_verified else "unverified",
                    rights_status="licensed" if is_verified and resource else "unverified",
                    content_hash=content_sha256(text),
                    concepts=specific_tags,
                    provenance={
                        "okf_path": entry.get("path"),
                        "generic_tags_filtered": [
                            t for t in raw_tags if t.strip().lower() in _GENERIC_OKF_TAGS
                        ],
                        "verified": entry.get("verified"),
                    },
                )
            )
        return out
